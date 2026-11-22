import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { BellRing, CheckCircle2, ClipboardCheck, Lock, MessageCircle, Send, Tag } from "lucide-react";
import { money, nameOf, percent, signed } from "../lib";
import { t } from "../locale";
import { loadTurnstile, submit, SubmitError, useGrowthConfig } from "../growth";
import { track } from "../track";
import type { Level, Opportunity, Ref, UnitLaunch } from "../types";

/** WhatsApp country codes for Egypt and the Gulf, where Qayem's buyers are. */
const CODES = [
  { code: "+20", label: "Egypt" },
  { code: "+966", label: "Saudi Arabia" },
  { code: "+971", label: "UAE" },
  { code: "+965", label: "Kuwait" },
  { code: "+974", label: "Qatar" },
  { code: "+", label: "Other" },
];

export type Channel = "whatsapp" | "email";
type Role = "" | "buyer" | "investor" | "seller" | "broker";

/** The promise every form makes, before anyone types a number. */
export function Pledge() {
  return (
    <p className="pledge">
      <Lock size={13} /> {t("We never share your number with brokers without your permission.")}
    </p>
  );
}

function Turnstile({ siteKey, onToken }: { siteKey: string; onToken: (token: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let id: string | undefined;
    let live = true;
    loadTurnstile()
      .then(() => {
        if (!live || !box.current || !window.turnstile) return;
        id = window.turnstile.render(box.current, {
          sitekey: siteKey,
          size: "flexible",
          callback: onToken,
          "expired-callback": () => onToken(""),
        });
      })
      .catch(() => {});
    return () => {
      live = false;
      if (id) window.turnstile?.remove(id);
    };
  }, [siteKey, onToken]);
  return <div ref={box} className="turnstile" />;
}

/** WhatsApp (with its country code) or e-mail: one field, plus the hidden honeypot. */
function Contact({
  channel,
  setChannel,
  value,
  setValue,
  code,
  setCode,
  emailAllowed = true,
  emailOnly = false,
}: {
  channel: Channel;
  setChannel: (channel: Channel) => void;
  value: string;
  setValue: (value: string) => void;
  code: string;
  setCode: (code: string) => void;
  emailAllowed?: boolean;
  emailOnly?: boolean;
}) {
  return (
    <div className="contact">
      {emailAllowed && !emailOnly && (
        <div className="segmented" role="group" aria-label={t("How should we reach you?")}>
          <button type="button" aria-pressed={channel === "whatsapp"} onClick={() => setChannel("whatsapp")}>
            <MessageCircle size={14} /> {t("WhatsApp")}
          </button>
          <button type="button" aria-pressed={channel === "email"} onClick={() => setChannel("email")}>
            {t("E-mail")}
          </button>
        </div>
      )}
      {channel === "whatsapp" ? (
        <div className="contact-phone">
          <label className="field contact-code">
            <span className="field-label">{t("Country")}</span>
            <span className="select">
              <select value={code} onChange={(event) => setCode(event.target.value)}>
                {CODES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.code === "+" ? t(item.label) : `${t(item.label)} ${item.code}`}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label className="field">
            <span className="field-label">{t("WhatsApp number")}</span>
            <span className="input">
              <input
                type="tel"
                inputMode="tel"
                autoComplete="tel-national"
                dir="ltr"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder={code === "+20" ? "010 1234 5678" : code === "+" ? "+44 7700 900123" : "50 123 4567"}
                maxLength={24}
                required
              />
            </span>
          </label>
        </div>
      ) : (
        <label className="field">
          <span className="field-label">{t("E-mail")}</span>
          <span className="input">
            <input
              type="email"
              inputMode="email"
              autoComplete="email"
              dir="ltr"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="name@example.com"
              maxLength={254}
              required
            />
          </span>
        </label>
      )}
    </div>
  );
}

function fullNumber(code: string, value: string) {
  const digits = value.trim();
  if (code === "+" || digits.startsWith("+") || digits.startsWith("00")) return digits;
  return `${code}${digits.replace(/^0+/, "")}`;
}

export function Chips<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="choice" role="group" aria-label={t(label)}>
      <span className="field-label">{t(label)}</span>
      <div className="choice-chips">
        {options.map(([option, text]) => (
          <button key={option} type="button" aria-pressed={value === option} onClick={() => onChange(value === option ? ("" as T) : option)}>
            {t(text)}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The shared form body: contact, optional name and intent chips, verification, the pledge, and a done state. */
export function CaptureForm({
  cta,
  done,
  send,
  children,
  askName = false,
  emailAllowed = true,
  emailOnly = false,
  roles = true,
  validate,
}: {
  cta: string;
  done: ReactNode;
  send: (contact: { channel: Channel; destination: string; name: string; role: Role; turnstile: string; website: string }) => Promise<unknown>;
  children?: ReactNode;
  askName?: boolean;
  emailAllowed?: boolean;
  /** Only an e-mail address is asked (corrections and takedowns, which need a written reply). */
  emailOnly?: boolean;
  roles?: boolean;
  /** The form's own fields: a problem to show, or nothing when they are complete. */
  validate?: () => string | null;
}) {
  const config = useGrowthConfig();
  const [channel, setChannel] = useState<Channel>(emailOnly ? "email" : "whatsapp");
  const [value, setValue] = useState("");
  const [code, setCode] = useState("+20");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("");
  const [token, setToken] = useState("");
  const [website, setWebsite] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [problem, setProblem] = useState("");
  if (state === "done") return <div className="capture-done" role="status">{done}</div>;
  const needsToken = Boolean(config?.turnstile_site_key);
  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const destination = channel === "whatsapp" ? fullNumber(code, value) : value.trim();
    const invalid = validate?.();
    if (invalid) return setProblem(t(invalid));
    if (!value.trim()) return setProblem(t(channel === "whatsapp" ? "Enter your WhatsApp number." : "Enter your e-mail address."));
    if (needsToken && !token) return setProblem(t("Please wait a moment while we check this browser."));
    setState("busy");
    setProblem("");
    try {
      await send({ channel, destination, name: name.trim(), role, turnstile: token, website });
      setState("done");
    } catch (error) {
      setState("idle");
      setProblem(error instanceof SubmitError ? t(error.message) : t("We could not send it. Please try again."));
    }
  };
  return (
    <form className="capture-form" onSubmit={onSubmit} noValidate>
      {children}
      {roles && (
        <Chips
          label="I am"
          value={role}
          onChange={setRole}
          options={[
            ["buyer", "Buying to live"],
            ["investor", "Investing"],
            ["broker", "A broker"],
          ]}
        />
      )}
      {askName && (
        <label className="field">
          <span className="field-label">{t("Your name (optional)")}</span>
          <span className="input">
            <input value={name} onChange={(event) => setName(event.target.value)} autoComplete="given-name" maxLength={80} />
          </span>
        </label>
      )}
      <Contact
        channel={channel}
        setChannel={setChannel}
        value={value}
        setValue={setValue}
        code={code}
        setCode={setCode}
        emailAllowed={emailAllowed}
        emailOnly={emailOnly}
      />
      {/* People never see this field; form-filling scripts do. */}
      <label className="honeypot" aria-hidden="true">
        {t("Website")}
        <input tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
      </label>
      {config?.turnstile_site_key && <Turnstile siteKey={config.turnstile_site_key} onToken={setToken} />}
      {problem && (
        <p className="field-error" role="alert">
          {problem}
        </p>
      )}
      <button type="submit" className="btn btn-nile btn-block" disabled={state === "busy"}>
        <Send size={15} className="flip-rtl" /> {t(cta)}
      </button>
      <Pledge />
    </form>
  );
}

const CHECKLIST = [
  "Ask the seller for the original contract and every payment receipt, and match the unit number, area and price.",
  "Ask the developer, in writing, for its transfer (تنازل) fee and whether it allows the transfer now.",
  "Confirm with the developer that no installment is overdue and how much is still owed.",
  "Ask whether the maintenance deposit is paid, and who pays any club or utility fees.",
  "Check the delivery date in the contract against the developer's latest schedule.",
  "Pay through a bank transfer or certified cheque, never cash, and sign the transfer at the developer's office.",
];

export function Checklist({ price }: { price?: number }) {
  return (
    <div className="checklist">
      <h4>
        <ClipboardCheck size={17} /> {t("Before you pay a deposit")}
      </h4>
      <ol>
        {CHECKLIST.map((item) => (
          <li key={item}>{t(item)}</li>
        ))}
      </ol>
      {price != null && (
        <p className="fineprint">
          {t("A typical developer transfer fee of 2.5–5% of the price would be {low}–{high} here. Ask the developer for the exact figure.", {
            low: money(price * 0.025, true),
            high: money(price * 0.05, true),
          })}
        </p>
      )}
    </div>
  );
}

export const lead = (kind: string, extra: Record<string, unknown> | (() => Record<string, unknown>)) => async (contact: {
  channel: Channel;
  destination: string;
  name: string;
  role: Role;
  turnstile: string;
  website: string;
}) =>
  submit("/leads", {
    kind,
    role: contact.role,
    name: contact.name,
    [contact.channel === "whatsapp" ? "whatsapp" : "email"]: contact.destination,
    turnstile: contact.turnstile,
    website: contact.website,
    ...(typeof extra === "function" ? extra() : extra),
  });

/** A capture card that follows the verdict: a good deal gets a checklist before the deposit; a unit that is
 * not cheaper than buying new gets the developer's own current offer. Nothing on the page is hidden behind it. */
export function LeadCard({
  unit,
}: {
  unit: {
    id?: number | null;
    opportunity: Opportunity;
    launch: UnitLaunch | null;
    compound: Ref | null;
    developer: Ref | null;
    price: number;
    property_type: string;
    area_m2: number;
  };
}) {
  const config = useGrowthConfig();
  const [open, setOpen] = useState(false);
  const [timeline, setTimeline] = useState("");
  const [cash, setCash] = useState("");
  const level: Level = unit.opportunity.level;
  if (!config?.leads || !unit.compound) return null;
  const goodDeal = level === "strong" || level === "good" || level === "check";
  const kind = goodDeal ? "resale_check" : "developer_price";
  const compound = nameOf(unit.compound)!;
  const developer = nameOf(unit.developer) ?? t("the developer");
  const cheaperNew = unit.launch?.same_finishing && unit.launch.gap > 0;
  const title = goodDeal
    ? t("Before you pay a deposit")
    : cheaperNew
      ? t("Buying new from {developer} costs less today", { developer })
      : t("See what {developer} offers in {compound} today", { developer, compound });
  const text = goodDeal
    ? t("Get Qayem’s verification checklist and a transfer-fee estimate for {compound} on WhatsApp, free.", { compound })
    : cheaperNew
      ? t("A similar new unit costs {gap} less in today’s money. Get {developer}’s current units and cash-discount options on WhatsApp. No buyer commission.", {
          gap: percent(unit.launch!.gap / (1 + unit.launch!.gap)),
          developer,
        })
      : t("Get {developer}’s current units, prices and payment plans in {compound} on WhatsApp, to compare with this one.", { developer, compound });
  const cta = goodDeal ? "Send me the checklist" : "Send me the developer’s prices";
  const opener = () => {
    setOpen(true);
    track("lead_open", { unit_id: unit.id ?? undefined, entity: unit.compound?.key, meta: { cta: kind, level } });
  };
  return (
    <section className={`capture capture-${goodDeal ? "deal" : "new"}`} aria-label={title}>
      <div className="capture-head">
        <span className="capture-icon">{goodDeal ? <ClipboardCheck size={20} /> : <Tag size={20} />}</span>
        <div>
          <h3>{title}</h3>
          <p>{text}</p>
        </div>
      </div>
      {!open ? (
        <button type="button" className="btn btn-nile" onClick={opener}>
          <MessageCircle size={16} /> {t(cta)}
        </button>
      ) : (
        <CaptureForm
          cta={cta}
          send={lead(kind, {
            unit_id: unit.id ?? undefined,
            compound: unit.compound.key,
            intent: {
              level,
              price: unit.price,
              type: unit.property_type,
              area: unit.area_m2,
              ...(unit.launch?.same_finishing ? { vs_developer: signed(unit.launch.gap) } : {}),
              ...(timeline ? { timeline } : {}),
              ...(cash ? { payment: cash } : {}),
            },
          })}
          done={
            <>
              <p>
                <CheckCircle2 size={17} />{" "}
                {t(goodDeal ? "Done. The checklist is below, and we will message you within a day." : "Done. We will send the developer’s current prices within a day.")}
              </p>
              {goodDeal && <Checklist price={unit.price} />}
            </>
          }
        >
          <Chips
            label="When are you buying?"
            value={timeline}
            onChange={setTimeline}
            options={[
              ["3_months", "Within 3 months"],
              ["this_year", "This year"],
              ["looking", "Just looking"],
            ]}
          />
          {goodDeal && (
            <Chips
              label="Paying"
              value={cash}
              onChange={setCash}
              options={[
                ["cash", "Cash now"],
                ["financing", "Need to check financing"],
              ]}
            />
          )}
        </CaptureForm>
      )}
    </section>
  );
}

/** An alert for a saved search or a compound: new listings and price cuts, after each nightly update. */
export function AlertSignup({ query, label, onDone }: { query: string; label: string; onDone?: () => void }) {
  const config = useGrowthConfig();
  if (!config?.leads) return null;
  return (
    <div className="capture capture-alert">
      <div className="capture-head">
        <span className="capture-icon">
          <BellRing size={20} />
        </span>
        <div>
          <h3>{t("Get an alert for this search")}</h3>
          <p>
            {t("We message you when a unit matching «{label}» is listed or cut in price, after each nightly update. No broker calls.", {
              label,
            })}
          </p>
        </div>
      </div>
      <CaptureForm
        cta="Turn on the alert"
        emailAllowed={config.email_alerts}
        send={async (contact) => {
          const result = await submit("/alerts", {
            channel: contact.channel,
            destination: contact.destination,
            role: contact.role,
            query,
            label,
            turnstile: contact.turnstile,
            website: contact.website,
          });
          onDone?.();
          return result;
        }}
        done={
          <p>
            <CheckCircle2 size={17} /> {t("Alert on. Every message has a link to stop it.")}
          </p>
        }
      />
    </div>
  );
}

/** Seller mode: the owner's own contract and plans, after the comparison buyers will make. */
export function SellerForm({ compound, price }: { compound: Ref | null; price: number | null }) {
  const config = useGrowthConfig();
  const [timeline, setTimeline] = useState("");
  const [remaining, setRemaining] = useState("");
  const [asking, setAsking] = useState("");
  if (!config?.leads) return null;
  return (
    <section className="capture capture-seller" aria-label={t("Selling this unit?")}>
      <div className="capture-head">
        <span className="capture-icon">
          <Tag size={20} />
        </span>
        <div>
          <h3>{t("Selling this unit?")}</h3>
          <p>
            {compound
              ? t("Leave your WhatsApp: we tell you when buyers search {compound}, and how your price compares as the market moves.", {
                  compound: nameOf(compound),
                })
              : t("Leave your WhatsApp: we tell you when buyers search your compound, and how your price compares as the market moves.")}
          </p>
        </div>
      </div>
      <CaptureForm
        cta="Notify me about buyers"
        askName
        roles={false}
        send={lead("seller", {
          role: "seller",
          compound: compound?.key,
          intent: {
            ...(price ? { contract_price: price } : {}),
            ...(remaining ? { remaining: Number(remaining) || remaining } : {}),
            ...(asking ? { asking: Number(asking) || asking } : {}),
            ...(timeline ? { timeline } : {}),
          },
        })}
        done={
          <p>
            <CheckCircle2 size={17} /> {t("Done. We will message you on WhatsApp; nothing is published without your approval.")}
          </p>
        }
      >
        <div className="form-row">
          <label className="field">
            <span className="field-label">{t("Still owed to the developer (EGP)")}</span>
            <span className="input">
              <input inputMode="numeric" type="number" min={0} value={remaining} onChange={(event) => setRemaining(event.target.value)} />
            </span>
          </label>
          <label className="field">
            <span className="field-label">{t("The price you hope for (EGP)")}</span>
            <span className="input">
              <input inputMode="numeric" type="number" min={0} value={asking} onChange={(event) => setAsking(event.target.value)} />
            </span>
          </label>
        </div>
        <Chips
          label="When do you want to sell?"
          value={timeline}
          onChange={setTimeline}
          options={[
            ["now", "As soon as possible"],
            ["3_months", "Within 3 months"],
            ["checking", "Just checking the price"],
          ]}
        />
      </CaptureForm>
    </section>
  );
}

/** Send the deal sheet to yourself; the role tells a broker from a buyer. */
export function SendSheet({ unitId, compound }: { unitId: number; compound: Ref | null }) {
  const config = useGrowthConfig();
  const [role, setRole] = useState("");
  if (!config?.leads) return null;
  return (
    <section className="capture capture-alert no-print" aria-label={t("Send this sheet to yourself")}>
      <div className="capture-head">
        <span className="capture-icon">
          <Send size={20} className="flip-rtl" />
        </span>
        <div>
          <h3>{t("Send this sheet to yourself")}</h3>
          <p>{t("We send the link to your WhatsApp or e-mail, so it is there when you talk to the seller.")}</p>
        </div>
      </div>
      <CaptureForm
        cta="Send it"
        roles={false}
        send={lead("deal_sheet", {
          unit_id: unitId,
          compound: compound?.key,
          role: ({ buying: "buyer", selling: "seller", broker: "broker" } as Record<string, string>)[role] ?? "",
        })}
        done={
          <p>
            <CheckCircle2 size={17} /> {t("Sent. Check your messages shortly.")}
          </p>
        }
      >
        <Chips
          label="I am"
          value={role}
          onChange={setRole}
          options={[
            ["buying", "Buying"],
            ["selling", "Selling"],
            ["broker", "A broker"],
          ]}
        />
      </CaptureForm>
    </section>
  );
}

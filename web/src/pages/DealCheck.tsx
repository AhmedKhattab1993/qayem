import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, CheckCircle2, ClipboardCheck, Landmark, PhoneCall, Scale } from "lucide-react";
import { egp, sep, place, titleCase, useCatalog } from "../lib";
import { t } from "../locale";
import { useGrowthConfig } from "../growth";
import { CaptureForm, Checklist, Chips, lead } from "../components/Capture";

/** Where the buyer lives: buyers abroad are who the deal check is for first. */
const COUNTRIES: [string, string][] = [
  ["EG", "Egypt"],
  ["SA", "Saudi Arabia"],
  ["AE", "UAE"],
  ["KW", "Kuwait"],
  ["QA", "Qatar"],
  ["OM", "Oman"],
  ["BH", "Bahrain"],
  ["GB", "United Kingdom"],
  ["US", "United States"],
  ["CA", "Canada"],
  ["EU", "Europe"],
  ["XX", "Somewhere else"],
];

const STEPS: [typeof Scale, string, string][] = [
  [Scale, "A verdict", "How the price compares with the developer’s price today and with similar units listed now, in today’s money."],
  [Landmark, "The developer’s current offer", "What the developer sells today in the same compound, its price and payment plan, to weigh against this unit."],
  [ClipboardCheck, "The transfer checklist", "The papers to ask for, the developer’s transfer fee, what is still owed, and how to pay safely from abroad."],
  [PhoneCall, "A call", "A short call to go through it, in Arabic or English, at a time that suits your time zone. No broker commission."],
];

export default function DealCheck() {
  const [params] = useSearchParams();
  const catalog = useCatalog();
  const config = useGrowthConfig();
  const [link, setLink] = useState(params.get("link") ?? "");
  const [compound, setCompound] = useState(params.get("compound") ?? "");
  const [type, setType] = useState(params.get("type") ?? "apartment");
  const [area, setArea] = useState(params.get("area") ?? "");
  const [price, setPrice] = useState(params.get("price") ?? "");
  const [payment, setPayment] = useState<"" | "cash" | "plan">(
    params.get("terms") === "plan" ? "plan" : params.get("terms") === "cash" ? "cash" : "",
  );
  const [country, setCountry] = useState("");
  const unitId = Number(params.get("unit")) || undefined;
  const types = catalog?.property_types ?? [];
  const match = catalog?.compounds.find((c) =>
    [c.name, c.name_ar].some((name) => name && name.toLocaleLowerCase() === compound.trim().toLocaleLowerCase()),
  );

  return (
    <div className="page-enter deal-check">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Free deal check")}</span>
          <h1 className="display">{t("Buying in Egypt from abroad? Have the deal checked first.")}</h1>
          <p className="lede">
            {t("Send the unit you are offered. Qayem checks its price against the developer and the market, and tells you what to ask before you transfer any money. Free, with no broker commission.")}
          </p>
        </div>
      </header>
      <div className="page split section-tight">
        <div>
          <h2 className="display">{t("What you get")}</h2>
          <ol className="deal-steps">
            {STEPS.map(([Icon, title, text]) => (
              <li key={title}>
                <span className="capture-icon">
                  <Icon size={18} />
                </span>
                <div>
                  <h3>{t(title)}</h3>
                  <p>{t(text)}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="fineprint">
            {t("Qayem compares asking prices; it does not value property or give investment advice. Your details go only to Qayem.")}{" "}
            <Link to="/privacy">{t("Privacy")}</Link>
          </p>
          <p>
            <Link className="link-arrow" to="/evaluate">
              {t("Or compare a unit yourself now")}
            </Link>
          </p>
        </div>
        <section className="capture capture-deal" aria-labelledby="deal-form">
          <div className="capture-head">
            <span className="capture-icon">
              <ClipboardCheck size={20} />
            </span>
            <div>
              <h3 id="deal-form">{t("The unit you are offered")}</h3>
              <p>{t("A listing link is enough. Otherwise, the compound, type, area and price.")}</p>
            </div>
          </div>
          {!config ? null : config.leads ? (
            <CaptureForm
              cta="Check this deal for me"
              roles={false}
              validate={() =>
                link.trim() || (compound.trim() && Number(price) > 0) ? null : "Add the listing link, or the compound and the price."
              }
              send={lead("deal_check", () => ({
                role: "buyer",
                unit_id: unitId,
                compound: match?.key,
                intent: {
                  ...(link.trim() ? { link: link.trim().slice(0, 300) } : {}),
                  ...(compound.trim() ? { compound: compound.trim().slice(0, 120) } : {}),
                  ...(type ? { type } : {}),
                  ...(Number(area) > 0 ? { area: Number(area) } : {}),
                  ...(Number(price) > 0 ? { price: Number(price) } : {}),
                  ...(payment ? { payment } : {}),
                  ...(country ? { country } : {}),
                },
              }))}
              done={
                <>
                  <p>
                    <CheckCircle2 size={17} /> {t("Received. We will send the check within two working days, then arrange the call.")}
                  </p>
                  <Checklist price={Number(price) > 0 ? Number(price) : undefined} />
                </>
              }
            >
              <label className="field">
                <span className="field-label">{t("Listing link (optional)")}</span>
                <span className="input">
                  <input
                    type="url"
                    inputMode="url"
                    dir="ltr"
                    value={link}
                    onChange={(event) => setLink(event.target.value)}
                    placeholder="https://…"
                    maxLength={300}
                  />
                </span>
              </label>
              <label className="field">
                <span className="field-label">{t("Compound")}</span>
                <span className="input">
                  <input
                    value={compound}
                    onChange={(event) => setCompound(event.target.value)}
                    list="deal-compounds"
                    placeholder={t("Start typing a compound name")}
                    maxLength={120}
                  />
                </span>
              </label>
              <datalist id="deal-compounds">
                {catalog?.compounds.map((c) => (
                  <option key={c.key} value={c.name}>
                    {[c.name_ar, place(c.district)].filter(Boolean).join(sep())}
                  </option>
                ))}
              </datalist>
              <div className="form-row">
                <label className="field">
                  <span className="field-label">{t("Unit type")}</span>
                  <span className="select">
                    <select value={type} onChange={(event) => setType(event.target.value)}>
                      {(types.length ? types.map((item) => item.value) : ["apartment", "villa", "chalet"]).map((value) => (
                        <option key={value} value={value}>
                          {titleCase(value)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={15} />
                  </span>
                </label>
                <label className="field">
                  <span className="field-label">{t("Area (m²)")}</span>
                  <span className="input">
                    <input inputMode="decimal" type="number" min={20} max={5000} value={area} onChange={(event) => setArea(event.target.value)} />
                  </span>
                </label>
              </div>
              <label className="field">
                <span className="field-label">{t("Price asked (EGP)")}</span>
                <span className="input">
                  <input inputMode="numeric" type="number" min={0} value={price} onChange={(event) => setPrice(event.target.value)} />
                </span>
                {Number(price) > 0 && <small className="muted num">{egp(Number(price))}</small>}
              </label>
              <Chips
                label="Payment"
                value={payment}
                onChange={setPayment}
                options={[
                  ["cash", "Cash"],
                  ["plan", "Installments"],
                ]}
              />
              <label className="field">
                <span className="field-label">{t("Where do you live?")}</span>
                <span className="select">
                  <select value={country} onChange={(event) => setCountry(event.target.value)}>
                    <option value="">{t("Choose")}</option>
                    {COUNTRIES.map(([code, name]) => (
                      <option key={code} value={code}>
                        {t(name)}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={15} />
                </span>
              </label>
            </CaptureForm>
          ) : (
            <p className="muted">{t("The form is not open yet. Please try again later.")}</p>
          )}
        </section>
      </div>
    </div>
  );
}

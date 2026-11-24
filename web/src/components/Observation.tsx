/** First-party prices: what a buyer was quoted, asked after the comparison and never before it. No contact asked. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, ClipboardCheck, MessageSquareQuote } from "lucide-react";
import { egp } from "../lib";
import { getLanguage, t } from "../locale";
import { visitor } from "../track";
import type { Ref } from "../types";

type Kind = "quoted_over" | "developer_offer";

export function ObservationAsk({
  compound,
  propertyType,
  area,
  price,
}: {
  compound: Ref | null;
  propertyType: string;
  area: number;
  price: number;
}) {
  const [kind, setKind] = useState<Kind>("quoted_over");
  const [amount, setAmount] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [problem, setProblem] = useState("");
  if (!compound) return null;
  if (state === "done")
    return (
      <section className="capture capture-alert observation" aria-live="polite">
        <p className="capture-done">
          <CheckCircle2 size={17} /> {t("Thank you. It goes into next month’s figures, anonymously.")}
        </p>
      </section>
    );
  const value = Number(amount);
  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!(value > 0)) return setProblem(t("Enter an amount in EGP."));
    setState("busy");
    setProblem("");
    try {
      const response = await fetch("/api/observations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          compound: compound.key,
          property_type: propertyType,
          area_m2: area,
          price,
          ...(kind === "quoted_over" ? { over: value } : { developer_price: value }),
          month: new Date().toISOString().slice(0, 7),
          visitor: visitor(),
          lang: getLanguage(),
        }),
      });
      if (!response.ok) throw new Error(String(response.status));
      setState("done");
    } catch {
      setState("idle");
      setProblem(t("We could not send it. Please try again."));
    }
  };
  return (
    <section className="capture capture-alert observation" aria-labelledby="observation-title">
      <div className="capture-head">
        <span className="capture-icon">
          <MessageSquareQuote size={20} />
        </span>
        <div>
          <h3 id="observation-title">{t("Help the next buyer (optional)")}</h3>
          <p>{t("Egypt publishes no sale prices. One anonymous figure from you makes Qayem’s guide better. No name or number is asked.")}</p>
        </div>
      </div>
      <form className="capture-form" onSubmit={onSubmit} noValidate>
        <div className="segmented" role="group" aria-label={t("What were you told?")}>
          <button type="button" aria-pressed={kind === "quoted_over"} onClick={() => setKind("quoted_over")}>
            {t("What over were you quoted?")}
          </button>
          <button type="button" aria-pressed={kind === "developer_offer"} onClick={() => setKind("developer_offer")}>
            {t("What does the developer offer you?")}
          </button>
        </div>
        <label className="field">
          <span className="field-label">
            {t(kind === "quoted_over" ? "The over asked, on top of the contract (EGP)" : "The developer’s price for a similar unit (EGP)")}
          </span>
          <span className="input">
            <input inputMode="numeric" type="number" min={0} value={amount} onChange={(event) => setAmount(event.target.value)} />
          </span>
          {value > 0 && <small className="muted num">{egp(value)}</small>}
        </label>
        {problem && (
          <p className="field-error" role="alert">
            {problem}
          </p>
        )}
        <button type="submit" className="btn btn-sm btn-primary" disabled={state === "busy"}>
          {t("Send it anonymously")}
        </button>
      </form>
    </section>
  );
}

/** The free deal check, offered beside a verdict: for buyers abroad first. */
export function DealCheckLink({
  compound,
  propertyType,
  area,
  price,
  terms,
  unitId,
}: {
  compound?: string | null;
  propertyType?: string;
  area?: number;
  price?: number;
  terms?: string;
  unitId?: number;
}) {
  const query = new URLSearchParams(
    Object.entries({
      unit: unitId ? String(unitId) : "",
      compound: compound ?? "",
      type: propertyType ?? "",
      area: area ? String(area) : "",
      price: price ? String(Math.round(price)) : "",
      terms: terms === "plan" || terms === "cash" ? terms : "",
    }).filter(([, value]) => value),
  );
  return (
    <p className="notice notice-soft deal-link">
      <ClipboardCheck size={18} />
      <span>
        {t("Buying from abroad? Get a free deal check: the developer’s current offer, the transfer checklist and a call.")}{" "}
        <Link to={`/deal-check?${query}`}>{t("Ask for a free deal check")}</Link>
      </span>
    </p>
  );
}

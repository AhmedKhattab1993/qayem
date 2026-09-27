import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Bookmark, Check, Equal, HelpCircle, Plus } from "lucide-react";
import { bucketLabel, planLabel, clamp, classLabel, compact, money, number, percent, signed, titleCase, sep } from "../lib";
import { t } from "../locale";
import { isPinned, useStore, type EntityKind } from "../store";
import type { Breakdown, Grade, Payment, Scope, Valuation, Verdict } from "../types";

const gradeText: Record<Grade, string> = {
  A: "Compound-level evidence",
  B: "Developer or thin compound evidence",
  C: "District-level evidence only",
};

export function GradeBadge({ grade, long = false }: { grade: Grade | null | undefined; long?: boolean }) {
  if (!grade) return <span className="grade grade-none">{t("Not graded")}</span>;
  return (
    <span className={`grade grade-${grade}`} title={t(gradeText[grade])}>
      <b>{grade}</b>
      {long && <span>{t(gradeText[grade])}</span>}
    </span>
  );
}

const verdictText: Record<Verdict, string> = {
  below: "Below fair range",
  within: "Within fair range",
  above: "Above fair range",
  suspect: "Check this listing",
};

export function VerdictBadge({ verdict, deviation }: { verdict: Verdict | null | undefined; deviation?: number | null }) {
  if (!verdict) return <span className="verdict-badge verdict-none">{t("Not positioned")}</span>;
  const Icon = { below: ArrowDownRight, within: Equal, above: ArrowUpRight, suspect: AlertTriangle }[verdict];
  return (
    <span className={`verdict-badge verdict-${verdict}`}>
      <Icon size={14} />
      {t(verdictText[verdict])}
      {deviation != null && verdict !== "within" && <b className="num">{signed(deviation)}</b>}
    </span>
  );
}

/** The fair range as a band, with the compared (cash-equivalent) price placed against it. */
export function FairRange({ valuation, caption }: { valuation: Valuation; caption?: string }) {
  const { fair_low: low, fair_value: fair, fair_high: high, compared_price: compared } = valuation;
  if (low == null || fair == null || high == null) return null;
  const points = [low, high, ...(compared ? [compared] : [])];
  const min = Math.min(...points) * 0.9;
  const max = Math.max(...points) * 1.08;
  const at = (value: number) => clamp(((value - min) / (max - min)) * 100, 1, 99);
  return (
    <figure className="fair-range">
      <div
        className="fair-track"
        role="img"
        aria-label={t("Fair range {low} to {high}; central estimate {fair}.", {
          low: money(low),
          high: money(high),
          fair: money(fair),
        })}
      >
        <span className="fair-band" style={{ insetInlineStart: `${at(low)}%`, width: `${at(high) - at(low)}%` }} />
        <span className="fair-mid" style={{ insetInlineStart: `${at(fair)}%` }} />
        {compared != null && (
          <span
            className={`fair-marker marker-${valuation.verdict ?? "none"}`}
            style={{ insetInlineStart: `${at(compared)}%` }}
          >
            <b className="num">{compact(compared)}</b>
          </span>
        )}
      </div>
      <div className="fair-scale num">
        <span style={{ insetInlineStart: `${at(low)}%` }}>{compact(low)}</span>
        <span style={{ insetInlineStart: `${at(high)}%` }}>{compact(high)}</span>
      </div>
      {caption && <figcaption className="fineprint">{caption}</figcaption>}
    </figure>
  );
}

export function ValuationSummary({ valuation, price }: { valuation: Valuation; price: number }) {
  if (valuation.status !== "valued")
    return (
      <div className="valuation-empty">
        <HelpCircle size={20} />
        <p>{t(valuation.reason ?? "Not enough evidence to value this unit.")}</p>
      </div>
    );
  const basis =
    valuation.basis === "cash_equivalent"
      ? "Compared on a cash-equivalent basis: remaining installments discounted to today’s money."
      : "The payment terms were not fully published, so the asking price is not placed against the range. Classified listings often show only what is due now, not the remaining installments.";
  return (
    <div className="valuation">
      <div className="valuation-head">
        <div>
          <span className="eyebrow no-rule">{t("Qayem fair value · cash today")}</span>
          <strong className="valuation-fair num">{money(valuation.fair_value)}</strong>
          <span className="valuation-range num">
            {t("Likely range {low} – {high}", { low: money(valuation.fair_low, true), high: money(valuation.fair_high, true) })}
          </span>
        </div>
        <GradeBadge grade={valuation.grade} long />
      </div>
      <FairRange valuation={valuation} />
      <div className="valuation-verdict">
        <VerdictBadge verdict={valuation.verdict} deviation={valuation.deviation} />
        {valuation.compared_price != null && (
          <span className="muted">
            {t("Cash-equivalent price {price}", { price: money(valuation.compared_price) })}
          </span>
        )}
      </div>
      {valuation.fair_headline != null && (
        <p className="valuation-headline">
          {t("On this payment plan, a fair headline price would be about {fair} (listed at {price}).", {
            fair: money(valuation.fair_headline),
            price: money(price),
          })}
        </p>
      )}
      <p className="fineprint">{t(basis)}</p>
    </div>
  );
}

export function PaymentFacts({ payment, price }: { payment: Payment; price: number }) {
  const rows: [string, string][] =
    payment.terms === "plan"
      ? [
          ["Headline price", money(price)],
          ["Paid at signing", money(price - (payment.remaining ?? 0))],
          ["Still owed", `${money(payment.remaining)}${sep()}${percent(payment.remaining_share)}`],
          ["Over", t("{n} years", { n: number(payment.years, 1) })],
          ["Worth today", money(payment.cash_equivalent)],
          ["Plan discount", percent(payment.discount, 1)],
        ]
      : payment.terms === "cash"
        ? [
            ["Headline price", money(price)],
            ["Payment", t("Cash")],
          ]
        : [
            ["Headline price", money(price)],
            ["Payment", t(payment.terms === "partial" ? "Installments, term not published" : "Not published")],
          ];
  return (
    <dl className="facts facts-single">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{t(label)}</dt>
          <dd className="num">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const levelText: Record<string, string> = {
  class: "Egypt-wide {class}",
  district: "{label} district",
  developer: "{label} in this district",
  compound: "{label} compound",
};
const factorText: Record<string, string> = {
  type: "Unit type",
  finishing: "Finishing",
  delivery: "Delivery",
  plan: "Payment plan",
  size: "Size",
};

export function BreakdownView({ breakdown, cls }: { breakdown: Breakdown; cls: string | null }) {
  return (
    <div className="breakdown">
      <ol className="breakdown-levels">
        {breakdown.levels.map((level, index) => (
          <li key={level.level}>
            <span className="breakdown-dot" />
            <div>
              <strong dir="auto">
                {t(levelText[level.level] ?? level.level, { class: classLabel(cls), label: level.label ?? "" })}
              </strong>
              <small className="num">
                {index === 0
                  ? t("{n} listings", { n: number(level.listings) })
                  : t("{n} listings · {change}", { n: number(level.listings), change: signed(level.change) })}
              </small>
            </div>
            <b className="num">
              {money(level.ppm, true)}
              <small> / {t("m²")}</small>
            </b>
          </li>
        ))}
      </ol>
      <ul className="breakdown-adjustments">
        {breakdown.adjustments.map((adjustment) => (
          <li key={adjustment.factor}>
            <span>{t(factorText[adjustment.factor])}</span>
            <span className="muted" dir="auto">
              {adjustment.factor === "size"
                ? t("{n} m² vs typical {typical} m²", { n: number(Number(adjustment.value)), typical: number(adjustment.typical) })
                : adjustment.factor === "delivery"
                  ? bucketLabel(String(adjustment.value))
                  : adjustment.factor === "plan"
                    ? planLabel(String(adjustment.value))
                  : titleCase(String(adjustment.value))}
            </span>
            <b className={`num ${adjustment.change > 0.005 ? "is-up" : adjustment.change < -0.005 ? "is-down" : ""}`}>
              {signed(adjustment.change, 1)}
            </b>
          </li>
        ))}
      </ul>
      <p className="fineprint">
        {t(
          "Each level moves part of the way from the one above, in proportion to how many listings support it. A compound with few listings stays close to its developer’s norm.",
        )}
      </p>
    </div>
  );
}

const unknownText: Record<string, string> = {
  payment_terms: "Payment terms",
  installment_term: "Installment term",
  compound: "Compound",
  developer: "Developer",
  finishing: "Finishing",
  delivery: "Delivery date",
  floor_and_view: "Floor, view and orientation",
  legal_status: "Registration and contract status",
  transfer_fee: "Developer transfer fee",
  maintenance_deposit: "Maintenance deposit status",
};

export function Unknowns({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="unknowns">
      {items.map((item) => (
        <li key={item}>
          <HelpCircle size={14} />
          {t(unknownText[item] ?? item)}
        </li>
      ))}
    </ul>
  );
}

export function ScopeNote({ scope }: { scope: Scope }) {
  const top = scope.sources[0];
  if (!top) return null;
  return (
    <p className="scope-note">
      <span className="num">{t("Based on {n} listings", { n: number(scope.count) })}</span>
      <span className="scope-bar" aria-hidden="true">
        {scope.sources.map((source) => (
          <i key={source.id} style={{ flexGrow: source.count }} title={source.name} />
        ))}
      </span>
      <span>
        {t("{share} from {source}", { share: percent(top.share), source: top.name })}
        {scope.sources.length > 1 && `${sep()}${t("{n} sources", { n: number(scope.sources.length) })}`}
      </span>
    </p>
  );
}

export function EntityActions({ kind, entityKey, name }: { kind: EntityKind; entityKey: string; name: string }) {
  const { watch, compare, toggleWatch, toggleCompare } = useStore();
  const watching = isPinned(watch, kind, entityKey);
  const comparing = isPinned(compare, kind, entityKey);
  return (
    <div className="entity-actions">
      <button
        className={`btn btn-sm ${watching ? "btn-ink" : ""}`}
        aria-pressed={watching}
        onClick={() => toggleWatch({ kind, key: entityKey, name })}
      >
        <Bookmark size={15} fill={watching ? "currentColor" : "none"} />
        {t(watching ? "Watching" : "Watch")}
      </button>
      <button
        className={`btn btn-sm ${comparing ? "btn-ink" : ""}`}
        aria-pressed={comparing}
        onClick={() => toggleCompare({ kind, key: entityKey, name })}
      >
        {comparing ? <Check size={15} /> : <Plus size={15} />}
        {t(comparing ? "In comparison" : "Compare")}
      </button>
    </div>
  );
}

/** Diverging bars for premiums against a district norm. */
export function PremiumBars({
  items,
}: {
  items: { key: string; label: string; meta?: string; value: number; to: string }[];
}) {
  const extent = Math.max(0.1, ...items.map((item) => Math.abs(item.value)));
  return (
    <ul className="premium-bars">
      {items.map((item) => {
        const width = (Math.abs(item.value) / extent) * 50;
        return (
          <li key={item.key}>
            <Link to={item.to} className="premium-row">
              <span className="premium-label">
                <b dir="auto">{item.label}</b>
                {item.meta && <small>{item.meta}</small>}
              </span>
              <span className="premium-track" aria-hidden="true">
                <i
                  className={item.value >= 0 ? "is-up" : "is-down"}
                  style={
                    item.value >= 0
                      ? { insetInlineStart: "50%", width: `${width}%` }
                      : { insetInlineEnd: "50%", width: `${width}%` }
                  }
                />
              </span>
              <b className={`num premium-value ${item.value >= 0 ? "is-up" : "is-down"}`}>{signed(item.value)}</b>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

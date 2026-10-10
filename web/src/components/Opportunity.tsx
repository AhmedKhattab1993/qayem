import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Bookmark, Check, CheckCheck, ChevronsDown, Equal, HelpCircle, Plus, Shuffle } from "lucide-react";
import { money, number, percent, quarterly, signed, sep, tone } from "../lib";
import { t } from "../locale";
import { isPinned, useStore, type EntityKind } from "../store";
import type { Level, Opportunity, Payment, Peers, Scope, Unit } from "../types";

export const levelText: Record<Level, string> = {
  strong: "Strong opportunity",
  good: "Good opportunity",
  in_line: "In line",
  mixed: "Mixed signals",
  pricier: "Pricier",
  check: "Check this listing",
  unrated: "Not enough to compare",
};
const levelIcon = { strong: ChevronsDown, good: ArrowDownRight, in_line: Equal, mixed: Shuffle, pricier: ArrowUpRight, check: AlertTriangle, unrated: HelpCircle };

export function LevelBadge({ level }: { level: Level }) {
  const Icon = levelIcon[level];
  return (
    <span className={`level-badge level-${level}`}>
      <Icon size={14} />
      {t(levelText[level])}
    </span>
  );
}

/** Strong or good against the developer and against similar units alike: the strongest case. */
export const cheaperOnBoth = ({ level, signals }: Opportunity) => signals.length === 2 && (level === "strong" || level === "good");

export function BothTag({ opportunity }: { opportunity: Opportunity }) {
  if (!cheaperOnBoth(opportunity)) return null;
  return (
    <span className="both-tag">
      <CheckCheck size={13} />
      {t("Cheaper on both")}
    </span>
  );
}

const levelNote: Record<Level, string> = {
  strong: "Clearly cheaper than what can be bought now: at least 15% under every comparison below, and 25% under one.",
  good: "Cheaper than what can be bought now: at least 5% under every comparison below, and 10% under one.",
  in_line: "Priced about like what can be bought now.",
  mixed: "Cheaper than one comparison and dearer than the other.",
  pricier: "Dearer than what can be bought now, as listed and in today’s money.",
  check: "Far below everything comparable, or even below the cheapest similar unit. It may be a listing error or an unusually early contract: confirm the price and the contract with the seller before anything else.",
  unrated: "No like-for-like developer price and fewer than five similar units listed, so there is no verdict. The facts are below.",
};

/** The unit's verdict and the comparisons behind it. `wide` lays it out as the band that opens a unit page,
 * with the page's actions (children) under it. */
export function OpportunitySummary({
  unit,
  wide = false,
  children,
}: {
  unit: Pick<Unit, "opportunity" | "launch" | "peers">;
  wide?: boolean;
  children?: ReactNode;
}) {
  const { opportunity, launch, peers } = unit;
  return (
    <section className={`valuation opportunity${wide ? " opportunity-wide" : ""}`} aria-label={t("Opportunity")}>
      <div className="opportunity-verdict">
        <span className="eyebrow no-rule">{t("Opportunity")}</span>
        <LevelBadge level={opportunity.level} />
        <BothTag opportunity={opportunity} />
        <p className="opportunity-note">{t(levelNote[opportunity.level])}</p>
      </div>
      <dl className={wide ? "opportunity-figures" : "facts facts-single"}>
        <div>
          <dt>{t("Vs the developer today")}</dt>
          <dd className={`num ${launch?.same_finishing ? tone(launch.gap) : ""}`}>
            {!launch ? t("No current price") : launch.same_finishing ? signed(launch.gap) : t("Different finishing")}
          </dd>
        </div>
        <div>
          <dt>{t("Vs similar units listed now")}</dt>
          <dd className={`num ${peers ? tone(peers.gap) : ""}`}>
            {peers ? signed(peers.gap) : t("Too few to rank")}
          </dd>
        </div>
        {peers && (
          <div>
            <dt>{t(wide ? "Rank in today’s money, cheapest first" : "Rank in today’s money")}</dt>
            <dd className="num">
              {t(wide ? "{rank} of {n}" : "{rank} of {n}, cheapest first", { rank: number(peers.rank), n: number(peers.count) })}
            </dd>
          </div>
        )}
      </dl>
      <p className="fineprint">
        {t("Each gap is the less favourable of the listed price and the price in today’s money. There is no fair price: Egypt publishes no resale sale prices.")}
      </p>
      {children && <div className="opportunity-actions">{children}</div>}
    </section>
  );
}

/** The unit against similar resale units listed now in the same compound. */
export function PeerPanel({ peers, price_per_m2 }: { peers: Peers; price_per_m2: number }) {
  return (
    <div className="launch">
      <div className="launch-lead">
        <div className={`launch-headline ${tone(peers.gap)}`}>
          <strong className="num">{signed(peers.gap)}</strong>
          <p>
            {t(
              peers.gap < 0
                ? "This unit costs this much less than the typical similar unit listed now in the same compound, both as listed and in today’s money."
                : "This unit costs this much more than the typical similar unit listed now in the same compound, on the less favourable of listed price and today’s money.",
            )}
          </p>
        </div>
      </div>
      <dl className="facts facts-single">
        <div>
          <dt>{t("Rank in today’s money")}</dt>
          <dd className="num">{t("{rank} of {n}, cheapest first", { rank: number(peers.rank), n: number(peers.count) })}</dd>
        </div>
        <div>
          <dt>{t("This unit / m², as listed")}</dt>
          <dd className="num">{money(price_per_m2)}</dd>
        </div>
        <div>
          <dt>{t("Similar units / m², as listed")}</dt>
          <dd className="num">{money(peers.median_headline_ppm)}</dd>
        </div>
        <div>
          <dt>{t("This unit / m², today’s money")}</dt>
          <dd className="num">{money(peers.cash_ppm)}</dd>
        </div>
        <div>
          <dt>{t("Similar units / m², today’s money")}</dt>
          <dd className="num">{money(peers.median_cash_ppm)}</dd>
        </div>
        <div>
          <dt>{t("Cheapest similar unit / m², today’s money")}</dt>
          <dd className="num">
            {money(peers.min_cash_ppm)}
            {peers.cheapest_gap < 0 && <small className={`muted ${tone(peers.cheapest_gap)}`}>{sep()}{signed(peers.cheapest_gap)}</small>}
          </dd>
        </div>
      </dl>
      <p className="fineprint">
        {t(
          peers.same_finishing
            ? "Similar means the same compound and unit type, within 1.5× the size, with the same finishing. Medians of the other units; listed prices are the sellers’ contract prices."
            : "Similar means the same compound and unit type, within 1.5× the size; too few share this unit’s finishing, so all finishings are included. Medians of the other units.",
        )}
      </p>
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
          ["Over", t("{n} years", { n: number(payment.years, 1), count: payment.years })],
          ...(quarterly(payment) != null
            ? ([["Each quarter, if paid evenly", `≈ ${money(quarterly(payment))}`]] as [string, string][])
            : []),
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
        {scope.sources.length > 1 && `${sep()}${t("{n} sources", { n: number(scope.sources.length), count: scope.sources.length })}`}
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

/** Diverging bars around zero, e.g. each developer's resale units against its own prices today. */
export function DivergingBars({
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
              <b className={`num premium-value ${tone(item.value)}`}>{signed(item.value)}</b>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

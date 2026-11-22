/** The price guide's building blocks: the answer sentence, segment tables, confidence and the source mix. */
import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { classLabel, date, money, monthLabel, nameOf, number, percent, periodLabel, sep, signed, tone } from "../lib";
import { t } from "../locale";
import { getCurrency, getRates, rateOf } from "../currency";
import type { Confidence, GuideRules, GuideRow, Period, PropertyClass, Segment, SourceShare } from "../types";

const CONFIDENCE: Record<Confidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  indicative: "Indicative",
};
export const confidenceText = (confidence: Confidence) => t(CONFIDENCE[confidence] ?? confidence);

/** What each confidence label means, from the guide's own rules. */
export function confidenceRules(rules?: Partial<GuideRules> | null) {
  return t(
    "High confidence: at least {high} listings, with no source above {share} of them. Medium: at least {multi} listings from two or more sources, or {single} from one. Indicative: published, but read it as a rough guide.",
    {
      high: number(rules?.high_min ?? 20),
      share: percent(rules?.high_max_share ?? 0.8),
      multi: number(rules?.min_multi ?? 5),
      single: number(rules?.min_single ?? 10),
    },
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return <span className={`tag conf conf-${confidence}`}>{confidenceText(confidence)}</span>;
}

/** Size bands as the API names them: "<100", "100-150", "200+". */
export function sizeLabel(size: string) {
  if (size === "*") return t("All sizes");
  const under = /^<(\d+)$/.exec(size);
  if (under) return t("Under {n} m²", { n: number(Number(under[1])) });
  const between = /^(\d+)-(\d+)$/.exec(size);
  if (between) return t("{low}–{high} m²", { low: number(Number(between[1])), high: number(Number(between[2])) });
  const over = /^(\d+)\+$/.exec(size);
  if (over) return t("{n} m² and over", { n: number(Number(over[1])) });
  return size;
}
const SIZE_ORDER = (size: string) => (size === "*" ? -1 : Number(/\d+/.exec(size)?.[0] ?? 0) + (size.startsWith("<") ? -0.5 : 0));

const DELIVERY: Record<string, string> = {
  "*": "Any delivery",
  ready: "Ready now",
  under_2y: "Within 2 years",
  later: "In 2 years or more",
};
export const deliveryText = (delivery: string) => t(DELIVERY[delivery] ?? delivery);
const CLASS_ORDER: PropertyClass[] = ["apartment", "house", "chalet"];

/** The source mix in a few words: "Nawy 57%، AqarExit 39%، +2". */
export function SourceMix({ sources, names }: { sources: (SourceShare | string)[]; names?: Record<string, string> }) {
  if (!sources.length) return null;
  const shares = sources.map((source) =>
    typeof source === "string" ? { id: source, name: names?.[source] ?? source, share: null as number | null } : source,
  );
  const shown = shares.slice(0, 2);
  const more = shares.length - shown.length;
  return (
    <span className="source-mix">
      {shown.map((source, index) => (
        <span key={source.id}>
          {index > 0 && sep()}
          <bdi>{source.name}</bdi>
          {source.share != null && <span className="num"> {percent(source.share)}</span>}
        </span>
      ))}
      {more > 0 && (
        <span className="num">
          {sep()}+{number(more)}
        </span>
      )}
    </span>
  );
}

/** Count, confidence, sources and period: shown with every published figure. */
export function FigureMeta({
  count,
  confidence,
  sources,
  period,
  names,
}: {
  count: number;
  confidence: Confidence;
  sources: (SourceShare | string)[];
  period?: Period | null;
  names?: Record<string, string>;
}) {
  return (
    <p className="figure-meta">
      <ConfidenceBadge confidence={confidence} />
      <span className="num">{t("{n} listings", { n: number(count), count })}</span>
      <SourceMix sources={sources} names={names} />
      {period && <span className="num">{periodLabel(period)}</span>}
    </p>
  );
}

/** A one-line explanation that opens in place: works without JavaScript and with a keyboard. */
export function Tip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="tip">
      <summary aria-label={t(label)} title={t(label)}>
        <Info size={15} />
      </summary>
      <span className="tip-body">{children}</span>
    </details>
  );
}

/** The CBE rate behind converted figures; nothing when prices are in EGP. */
export function RateNote() {
  const currency = getCurrency();
  const rates = getRates();
  if (currency === "EGP" || !rates) return null;
  return (
    <p className="fineprint rate-note num">
      {t("Shown in {currency} at the Central Bank of Egypt rate of {day}: 1 {currency} = {rate}. Listings are priced in EGP.", {
        currency: t(currency),
        day: date(rates.day),
        rate: `${number(rateOf(currency), 2)} ${t("EGP")}`,
      })}
    </p>
  );
}

export function NoSalePrices() {
  return (
    <p className="fineprint no-sale-prices">
      {t("Egypt publishes no property sale prices. These are asking prices from public listings, not completed sales or valuations.")}
    </p>
  );
}

const ASKING: Record<PropertyClass, string> = {
  apartment: "The asking price for apartments in {place} is about {ppm} per m² ({month}).",
  chalet: "The asking price for chalets in {place} is about {ppm} per m² ({month}).",
  house: "The asking price for villas and houses in {place} is about {ppm} per m² ({month}).",
};
const RANGE: Record<PropertyClass, string> = {
  apartment: "The middle half of apartments listed here ask between {low} and {high} per m², about {plow} to {phigh} for a whole unit.",
  chalet: "The middle half of chalets listed here ask between {low} and {high} per m², about {plow} to {phigh} for a whole unit.",
  house: "The middle half of villas and houses listed here ask between {low} and {high} per m², about {plow} to {phigh} for a whole unit.",
};

/** Resale against buying the same kind of unit new from the developer today, in today's money. */
export function resaleVsNewText(value: number | null | undefined) {
  if (value == null) return null;
  if (Math.abs(value) < 0.02) return t("Resale and buying new from the developer cost about the same here, in today’s money.");
  return t(
    value < 0
      ? "Buying resale here costs about {gap} less than buying new from the developer today, in today’s money."
      : "Buying resale here costs about {gap} more than buying new from the developer today, in today’s money.",
    { gap: percent(Math.abs(value)) },
  );
}

/** The answer first: one sentence with the number, the place and the month, then the range and resale against new. */
export function GuideAnswer({
  place,
  segment,
  period,
  month,
}: {
  place: string;
  segment: Segment | (GuideRow & { sources: (SourceShare | string)[]; p25_price?: number; p75_price?: number });
  period?: Period | null;
  month?: string | null;
}) {
  const when = monthLabel(month ?? period?.end?.slice(0, 7));
  const gap = resaleVsNewText(segment.resale_vs_new);
  const hasPrices = "p25_price" in segment && segment.p25_price != null && segment.p75_price != null;
  return (
    <div className="guide-answer">
      <p className="guide-sentence">
        {t(ASKING[segment.class] ?? ASKING.apartment, { place, ppm: money(segment.median_ppm), month: when })}
      </p>
      <div className="guide-range num">
        {hasPrices
          ? t(RANGE[segment.class] ?? RANGE.apartment, {
              low: money(segment.p25_ppm),
              high: money(segment.p75_ppm),
              plow: money(segment.p25_price, true),
              phigh: money(segment.p75_price, true),
            })
          : t("The middle half of listings here ask between {low} and {high} per m².", {
              low: money(segment.p25_ppm),
              high: money(segment.p75_ppm),
            })}
        {segment.median_cash_ppm != null && (
          <>
            {" "}
            {t("In today’s money, with installments discounted, about {cash} per m².", { cash: money(segment.median_cash_ppm) })}
            <Tip label="What is today’s money?">
              {t(
                "A price paid over years of installments is worth less than the same price in cash. Qayem discounts the installments still owed to what they are worth today, so a plan and a cash price can be compared.",
              )}
            </Tip>
          </>
        )}
      </div>
      {gap && <p className={`guide-gap ${tone(segment.resale_vs_new)}`}>{gap}</p>}
      <FigureMeta count={segment.count} confidence={segment.confidence} sources={segment.sources} period={period} />
      <NoSalePrices />
      <RateNote />
    </div>
  );
}

function SegmentRow({ segment, label }: { segment: Segment; label: string }) {
  return (
    <tr>
      <th scope="row">
        <span className="ledger-stack">
          <strong>{label}</strong>
          <small>{classLabel(segment.class)}</small>
        </span>
      </th>
      <td data-label={t("Asking / m²")} className="num ledger-strong">
        {money(segment.median_ppm, true)}
      </td>
      <td data-label={t("Middle half / m²")} className="num">
        {money(segment.p25_ppm, true)} – {money(segment.p75_ppm, true)}
      </td>
      <td data-label={t("Typical price")} className="num">
        {money(segment.median_price, true)}
      </td>
      <td data-label={t("Resale vs new")} className={`num ${tone(segment.resale_vs_new)}`}>
        {signed(segment.resale_vs_new)}
      </td>
      <td data-label={t("Listings")} className="num">
        {number(segment.count)}
      </td>
      <td data-label={t("Confidence")}>
        <span className="ledger-stack">
          <ConfidenceBadge confidence={segment.confidence} />
          <small>
            <SourceMix sources={segment.sources} />
          </small>
        </span>
      </td>
    </tr>
  );
}

function SegmentTable({ caption, rows }: { caption: string; rows: [Segment, string][] }) {
  if (!rows.length) return null;
  return (
    <div className="ledger-frame">
      <div className="ledger stack guide-ledger">
        <table>
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              <th scope="col">{t("Segment")}</th>
              <th scope="col">{t("Asking / m²")}</th>
              <th scope="col">{t("Middle half / m²")}</th>
              <th scope="col">{t("Typical price")}</th>
              <th scope="col">{t("Resale vs new")}</th>
              <th scope="col">{t("Listings")}</th>
              <th scope="col">{t("Confidence")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([segment, label]) => (
              <SegmentRow key={segment.key} segment={segment} label={label} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The guide's segments for one place: by type and size, then by delivery. */
export function SegmentTables({
  segments,
  scope,
  period,
  rules,
}: {
  segments: Segment[];
  /** "*" for a district's own segments, or the compound's key. */
  scope: string;
  period: Period | null | undefined;
  rules?: Partial<GuideRules> | null;
}) {
  const own = segments.filter((s) => s.compound === scope);
  const byClass = (a: Segment, b: Segment) => CLASS_ORDER.indexOf(a.class) - CLASS_ORDER.indexOf(b.class);
  const sizes = own
    .filter((s) => s.delivery === "*")
    .sort((a, b) => byClass(a, b) || SIZE_ORDER(a.size) - SIZE_ORDER(b.size))
    .map((s): [Segment, string] => [s, sizeLabel(s.size)]);
  const outside = scope === "*" ? segments.filter((s) => s.compound === "outside" && s.size === "*" && s.delivery === "*") : [];
  const delivery = own
    .filter((s) => s.size === "*" && s.delivery !== "*")
    .sort((a, b) => byClass(a, b) || ["ready", "under_2y", "later"].indexOf(a.delivery) - ["ready", "under_2y", "later"].indexOf(b.delivery))
    .map((s): [Segment, string] => [s, deliveryText(s.delivery)]);
  if (!sizes.length && !delivery.length) return null;
  return (
    <div className="guide-tables">
      {sizes.length > 0 && (
        <div>
          <h3>{t("By type and size")}</h3>
          <SegmentTable
            caption={t("Asking prices by type and size")}
            rows={[...sizes, ...outside.map((s): [Segment, string] => [s, t("Outside compounds")])]}
          />
        </div>
      )}
      {delivery.length > 0 && (
        <div>
          <h3>{t("By delivery")}</h3>
          <SegmentTable caption={t("Asking prices by delivery")} rows={delivery} />
        </div>
      )}
      <p className="fineprint">
        {t("Asking prices of listings seen {period}, after removing duplicates listed on more than one site. “Middle half” is the range from the cheapest quarter to the dearest quarter.", {
          period: periodLabel(period),
        })}{" "}
        {confidenceRules(rules)}
      </p>
    </div>
  );
}

/** The headline segment of a place: the guide's own pick, else its largest whole-place class. */
export function headlineOf(segments: Segment[], scope: string, headline?: Segment | null) {
  if (headline) return headline;
  return (
    segments
      .filter((s) => s.compound === scope && s.size === "*" && s.delivery === "*")
      .sort((a, b) => b.count - a.count)[0] ?? null
  );
}

/** A place's name from a guide row: Arabic where known. */
export const guideName = (entity: { name: string; name_ar?: string | null }) => nameOf(entity)!;

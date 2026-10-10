import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Bookmark, Building2, Landmark, Plus, Rows3, Scale, X } from "lucide-react";
import { atSigning, classLabel, date, deliveryLabel, money, number, percent, quarterly, signed, sep, titleCase, tone, nameOf, place, year } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { pinnedName, pinnedPath, usePinned, type Loaded } from "../entities";
import type { ClassSummary, Launch, Profile, UnitFull } from "../types";
import { EmptyState } from "../components/States";
import { LevelBadge } from "../components/Opportunity";
import { termsLabel } from "../components/UnitTable";
import { Thumb } from "../components/Gallery";

/** Compounds with compounds, developers with developers, units with units. */
type Ready = Extract<Loaded, { status: "ready" }>;
/** `best` gives a figure where lower is better; the lowest across the columns is marked. */
type Row = { label: string; value: (entry: Ready) => React.ReactNode; best?: (entry: Ready) => number | null | undefined };

const profileOf = (entry: Ready): Profile & { units: number; good_count: number; launch: Launch | null } =>
  entry.kind === "compound" ? entry.data.compound : (entry.data as Profile & { units: number; good_count: number; launch: Launch | null });

const unitOf = (entry: Ready): UnitFull => {
  if (entry.kind !== "unit") throw new Error("Units are compared only with units");
  return entry.data.unit;
};
const cashPpm = (unit: UnitFull) => (unit.payment.cash_equivalent != null ? unit.payment.cash_equivalent / unit.area_m2 : null);

/** Two to three saved units side by side: what each costs now and over time, and how each compares. */
const unitRows: Row[] = [
  {
    label: "Where",
    value: (e) => (
      <span dir="auto">
        {unitOf(e).compound ? (
          <Link to={`/compounds/${encodeURIComponent(unitOf(e).compound!.key)}`}>{nameOf(unitOf(e).compound)}</Link>
        ) : (
          "—"
        )}
        {unitOf(e).district && <small className="muted compare-sub">{place(unitOf(e).district)}</small>}
      </span>
    ),
  },
  { label: "Opportunity", value: (e) => <LevelBadge level={unitOf(e).opportunity.level} /> },
  {
    label: "Vs the developer today",
    value: (e) => {
      const launch = unitOf(e).launch;
      return launch?.same_finishing ? <b className={`num ${tone(launch.gap)}`}>{signed(launch.gap)}</b> : "—";
    },
    best: (e) => (unitOf(e).launch?.same_finishing ? unitOf(e).launch!.gap : null),
  },
  {
    label: "Vs similar units listed now",
    value: (e) => {
      const peers = unitOf(e).peers;
      return peers ? (
        <span className="num">
          <b className={tone(peers.gap)}>{signed(peers.gap)}</b>
          <small className="muted compare-sub">{t("{rank} of {n}", { rank: number(peers.rank), n: number(peers.count) })}</small>
        </span>
      ) : (
        "—"
      );
    },
    best: (e) => unitOf(e).peers?.gap,
  },
  { label: "Asking price", value: (e) => <span className="num">{money(unitOf(e).price)}</span>, best: (e) => unitOf(e).price },
  {
    label: "Cash today",
    value: (e) => <b className="num">{money(unitOf(e).payment.cash_equivalent)}</b>,
    best: (e) => unitOf(e).payment.cash_equivalent,
  },
  {
    label: "Paid at signing",
    value: (e) => <span className="num">{money(atSigning(unitOf(e).price, unitOf(e).payment))}</span>,
    best: (e) => atSigning(unitOf(e).price, unitOf(e).payment),
  },
  {
    label: "Each quarter, if paid evenly",
    value: (e) => <span className="num">{quarterly(unitOf(e).payment) != null ? `≈ ${money(quarterly(unitOf(e).payment))}` : "—"}</span>,
  },
  { label: "Payment", value: (e) => <span className="num">{termsLabel(unitOf(e))}</span> },
  { label: "Area", value: (e) => <span className="num">{number(unitOf(e).area_m2)} {t("m²")}</span> },
  {
    label: "Per m², in today’s money",
    value: (e) => <span className="num">{money(cashPpm(unitOf(e)))}</span>,
    best: (e) => cashPpm(unitOf(e)),
  },
  {
    label: "Bedrooms",
    value: (e) => <span className="num">{unitOf(e).bedrooms === 0 ? t("Studio") : number(unitOf(e).bedrooms)}</span>,
  },
  {
    label: "Delivery",
    value: (e) => {
      const { bucket, date: when, years } = unitOf(e).delivery;
      return <span className="num">{bucket !== "ready" && when ? date(when, "month") : deliveryLabel(bucket, years)}</span>;
    },
  },
  {
    label: "Finishing",
    value: (e) => titleCase(unitOf(e).finishing_class === "unknown" ? null : unitOf(e).finishing_class),
  },
  { label: "Contract signed", value: (e) => <span className="num">{year(unitOf(e).contract_year)}</span> },
];

const classOf = (entry: Ready, cls: string): ClassSummary | undefined =>
  entry.kind === "compound" ? entry.data.compound.classes.find((c) => c.class === cls) : undefined;

export default function Compare() {
  const { compare, toggleCompare, clearCompare } = useStore();
  const { get, retry } = usePinned(compare);
  const kind = compare[0]?.kind;
  const measures: Row[] = kind === "unit" ? unitRows : [
    ...(kind === "compound"
      ? [
          {
            label: "Developer",
            value: (e: Ready) =>
              e.kind === "compound" && e.data.compound.developer ? (
                <Link to={`/developers/${encodeURIComponent(e.data.compound.developer.key)}`}>{nameOf(e.data.compound.developer)}</Link>
              ) : (
                "—"
              ),
          },
          { label: "District", value: (e: Ready) => (e.kind === "compound" ? place(e.data.compound.district) : "—") },
          ...(["apartment", "chalet", "house"] as const).map((cls) => ({
            label: `${classLabel(cls)}${sep()}${t("resale / developer today, per m²")}`,
            value: (e: Ready) => {
              const item = classOf(e, cls);
              return item ? (
                <span className="compare-cell num">
                  <b>{money(item.median_asking_ppm, true)}</b> / {item.developer_ppm ? money(item.developer_ppm, true) : "—"}
                </span>
              ) : (
                "—"
              );
            },
          })),
        ]
      : [
          { label: "Compounds", value: (e: Ready) => (e.kind === "developer" ? number(e.data.compounds.length) : "—") },
          { label: "Districts", value: (e: Ready) => (e.kind === "developer" ? number(e.data.districts.length) : "—") },
        ]),
    {
      label: "Resale vs developer",
      value: (e) => <b className={`num ${tone(profileOf(e).launch?.median_gap)}`}>{signed(profileOf(e).launch?.median_gap)}</b>,
    },
    { label: "Strong or good opportunities", value: (e) => <span className="num">{number(profileOf(e).good_count)}</span> },
    { label: "Resale listings", value: (e) => <span className="num">{number(profileOf(e).units)}</span> },
    { label: "Ready to move in", value: (e) => <span className="num">{percent(profileOf(e).ready_share)}</span> },
    {
      label: "Median wait for the rest",
      value: (e) =>
        profileOf(e).median_years_to_delivery ? t("{n} years", { n: number(profileOf(e).median_years_to_delivery, 1), count: profileOf(e).median_years_to_delivery }) : "—",
    },
    { label: "Listed on installment plans", value: (e) => <span className="num">{percent(profileOf(e).plan_share)}</span> },
    { label: "Median share still owed", value: (e) => <span className="num">{percent(profileOf(e).median_remaining_share)}</span> },
    { label: "Headline above cash value by", value: (e) => <span className="num">{percent(profileOf(e).median_plan_discount)}</span> },
    {
      label: "Main source",
      value: (e) => (
        <>
          <bdi>{profileOf(e).scope.sources[0]?.name ?? "—"}</bdi>
          {sep()}
          <span className="num">{percent(profileOf(e).scope.sources[0]?.share)}</span>
        </>
      ),
    },
  ];
  // With one source (AqarExit) the main-source row says nothing.
  const rows = measures.filter(
    (row) =>
      kind === "unit" ||
      row.label !== "Main source" ||
      compare.some((item) => {
        const entry = get(item);
        return entry.status === "ready" && profileOf(entry as Ready).scope.sources.length > 1;
      }),
  );

  return (
    <div className="compare page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Compare")}</span>
          <h1 className="display">
            {t("Side by side,")} <em>{t("like for like.")}</em>
          </h1>
          <p className="lede">
            {t("Compare up to three units, compounds or developers side by side: prices in today’s money, the comparisons, delivery and payment.")}
          </p>
          {compare.length > 0 && (
            <button className="btn btn-sm" onClick={clearCompare}>
              <X size={15} /> {t("Clear all")}
            </button>
          )}
        </div>
      </header>
      <div className="page">
        {compare.length === 0 ? (
          <EmptyState
            icon={<Scale size={26} />}
            title={t("Nothing to compare yet.")}
            text={t("Open a unit, compound or developer and choose Compare.")}
            action={
              <div className="entity-actions">
                <Link className="btn btn-ink" to="/units">
                  <Rows3 size={16} /> {t("Browse units")}
                </Link>
                <Link className="btn" to="/compounds">
                  <Building2 size={16} /> {t("Browse compounds")}
                </Link>
                <Link className="btn" to="/developers">
                  <Landmark size={16} /> {t("Browse developers")}
                </Link>
              </div>
            }
          />
        ) : (
          <div className="ledger compare-table">
            <table style={{ "--columns": compare.length } as CSSProperties}>
              <caption className="sr-only">{t("Comparison")}</caption>
              <thead>
                <tr>
                  <th scope="col">
                    <span className="sr-only">{t("Measure")}</span>
                  </th>
                  {compare.map((item) => (
                    <th scope="col" key={item.key}>
                      <span className="compare-head">
                        {item.kind === "unit" && (() => {
                          const entry = get(item);
                          return <Thumb url={entry.status === "ready" && entry.kind === "unit" ? entry.data.unit.photo : null} />;
                        })()}
                        <Link to={pinnedPath(item)} dir="auto">
                          {pinnedName(item, get(item))}
                        </Link>
                        <button
                          className="btn btn-sm btn-icon btn-ghost"
                          aria-label={t("Remove {name} from comparison", { name: pinnedName(item, get(item)) })}
                          onClick={() => toggleCompare(item)}
                        >
                          <X size={15} />
                        </button>
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const figures = compare.map((item) => {
                    const entry = get(item);
                    return row.best && entry.status === "ready" ? row.best(entry as Ready) : null;
                  });
                  const known = figures.filter((value): value is number => value != null);
                  const lowest = known.length > 1 && new Set(known).size > 1 ? Math.min(...known) : null;
                  return (
                  <tr key={row.label}>
                    <th scope="row">{t(row.label)}</th>
                    {compare.map((item, index) => {
                      const entry = get(item);
                      const best = lowest != null && figures[index] === lowest;
                      return (
                        <td key={item.key} className={best ? "is-best" : undefined}>
                          {best && <span className="sr-only">{t("Lowest")}: </span>}
                          {entry.status === "ready" ? (
                            row.value(entry as Ready)
                          ) : entry.status === "error" ? (
                            <button className="link-arrow" onClick={retry}>
                              {t("Unavailable · retry")}
                            </button>
                          ) : (
                            <span className="muted">…</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {compare.length > 0 && compare.length < 3 && (
          <p className="compare-more">
            <Link className="link-arrow" to={kind === "developer" ? "/developers" : kind === "unit" ? "/units" : "/compounds"}>
              <Plus size={15} />{" "}
              {t(kind === "developer" ? "Add another developer" : kind === "unit" ? "Add another unit" : "Add another compound")}
            </Link>
            {kind === "unit" && (
              <Link className="link-arrow" to="/watchlist">
                <Bookmark size={15} /> {t("From your watchlist")}
              </Link>
            )}
          </p>
        )}
      </div>
    </div>
  );
}

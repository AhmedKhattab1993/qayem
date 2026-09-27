import { Link } from "react-router-dom";
import { Building2, Landmark, Scale, X } from "lucide-react";
import { classLabel, money, number, percent, signed, sep } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { usePinned, type Loaded } from "../entities";
import type { ClassSummary, Profile } from "../types";
import { EmptyState } from "../components/States";
import { GradeBadge } from "../components/Valuation";

type Row = { label: string; value: (entry: Extract<Loaded, { status: "ready" }>) => React.ReactNode };

const profileOf = (entry: Extract<Loaded, { status: "ready" }>): Profile & { units: number; premium: number | null } =>
  entry.kind === "compound"
    ? { ...entry.data.compound, premium: entry.data.compound.premium_vs_district }
    : { ...entry.data, premium: entry.data.premium_vs_district };

const classOf = (entry: Extract<Loaded, { status: "ready" }>, cls: string): ClassSummary | undefined =>
  entry.kind === "compound" ? entry.data.compound.classes.find((c) => c.class === cls) : undefined;

export default function Compare() {
  const { compare, toggleCompare, clearCompare } = useStore();
  const { get, retry } = usePinned(compare);
  const kind = compare[0]?.kind;
  const rows: Row[] = [
    ...(kind === "compound"
      ? [
          {
            label: "Developer",
            value: (e: Extract<Loaded, { status: "ready" }>) =>
              e.kind === "compound" && e.data.compound.developer ? (
                <Link to={`/developers/${encodeURIComponent(e.data.compound.developer.key)}`}>{e.data.compound.developer.name}</Link>
              ) : (
                "—"
              ),
          },
          { label: "District", value: (e: Extract<Loaded, { status: "ready" }>) => (e.kind === "compound" ? e.data.compound.district : "—") },
          ...(["apartment", "chalet", "house"] as const).map((cls) => ({
            label: `${classLabel(cls)}${sep()}${t("fair cash / m²")}`,
            value: (e: Extract<Loaded, { status: "ready" }>) => {
              const item = classOf(e, cls);
              return item?.reference_ppm ? (
                <span className="compare-cell">
                  <b className="num">{money(item.reference_ppm, true)}</b> <GradeBadge grade={item.grade} />
                </span>
              ) : (
                "—"
              );
            },
          })),
        ]
      : [
          { label: "Compounds", value: (e: Extract<Loaded, { status: "ready" }>) => (e.kind === "developer" ? number(e.data.compounds.length) : "—") },
          { label: "Districts", value: (e: Extract<Loaded, { status: "ready" }>) => (e.kind === "developer" ? number(e.data.districts.length) : "—") },
        ]),
    { label: "Premium vs district", value: (e) => <b className="num">{signed(profileOf(e).premium)}</b> },
    { label: "Resale listings", value: (e) => <span className="num">{number(profileOf(e).units)}</span> },
    { label: "Ready to move in", value: (e) => <span className="num">{percent(profileOf(e).ready_share)}</span> },
    {
      label: "Median wait for the rest",
      value: (e) =>
        profileOf(e).median_years_to_delivery ? t("{n} years", { n: number(profileOf(e).median_years_to_delivery, 1) }) : "—",
    },
    { label: "Listed on installment plans", value: (e) => <span className="num">{percent(profileOf(e).plan_share)}</span> },
    { label: "Median share still owed", value: (e) => <span className="num">{percent(profileOf(e).median_remaining_share)}</span> },
    { label: "Headline above cash value by", value: (e) => <span className="num">{percent(profileOf(e).median_plan_discount)}</span> },
    {
      label: "Priced below / within / above range",
      value: (e) => {
        const v = profileOf(e).verdicts;
        const total = (v.below ?? 0) + (v.within ?? 0) + (v.above ?? 0);
        return total ? (
          <span className="num">
            {percent((v.below ?? 0) / total)}{sep()}{percent((v.within ?? 0) / total)}{sep()}{percent((v.above ?? 0) / total)}
          </span>
        ) : (
          "—"
        );
      },
    },
    { label: "Main source", value: (e) => `${profileOf(e).scope.sources[0]?.name ?? "—"}${sep()}${percent(profileOf(e).scope.sources[0]?.share)}` },
  ];

  return (
    <div className="compare page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Compare")}</span>
          <h1 className="display">
            {t("Side by side,")} <em>{t("like for like.")}</em>
          </h1>
          <p className="lede">
            {t("Compare up to three compounds, or up to three developers, on fair value, delivery and payment structure.")}
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
            text={t("Open a compound or developer and choose Compare.")}
            action={
              <div className="entity-actions">
                <Link className="btn btn-ink" to="/compounds">
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
            <table>
              <caption className="sr-only">{t("Comparison")}</caption>
              <thead>
                <tr>
                  <th scope="col">
                    <span className="sr-only">{t("Measure")}</span>
                  </th>
                  {compare.map((item) => (
                    <th scope="col" key={item.key}>
                      <span className="compare-head">
                        <Link to={`/${item.kind === "compound" ? "compounds" : "developers"}/${encodeURIComponent(item.key)}`} dir="auto">
                          {item.name}
                        </Link>
                        <button
                          className="btn btn-sm btn-icon btn-ghost"
                          aria-label={t("Remove {name} from comparison", { name: item.name })}
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
                {rows.map((row) => (
                  <tr key={row.label}>
                    <th scope="row">{t(row.label)}</th>
                    {compare.map((item) => {
                      const entry = get(item);
                      return (
                        <td key={item.key} dir="auto">
                          {entry.status === "ready" ? (
                            row.value(entry)
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
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

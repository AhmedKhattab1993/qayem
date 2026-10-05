import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Building2, Landmark, Plus, Scale, X } from "lucide-react";
import { classLabel, money, number, percent, signed, sep, tone, nameOf, place } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { pinnedName, usePinned, type Loaded } from "../entities";
import type { ClassSummary, Launch, Profile } from "../types";
import { EmptyState } from "../components/States";

/** Only compounds and developers are compared side by side. */
type Ready = Extract<Loaded, { status: "ready"; kind: "compound" | "developer" }>;
type Row = { label: string; value: (entry: Ready) => React.ReactNode };

const profileOf = (entry: Ready): Profile & { units: number; good_count: number; launch: Launch | null } =>
  entry.kind === "compound" ? entry.data.compound : entry.data;

const classOf = (entry: Ready, cls: string): ClassSummary | undefined =>
  entry.kind === "compound" ? entry.data.compound.classes.find((c) => c.class === cls) : undefined;

export default function Compare() {
  const { compare, toggleCompare, clearCompare } = useStore();
  const { get, retry } = usePinned(compare);
  const kind = compare[0]?.kind;
  const measures: Row[] = [
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
            {t("Compare up to three compounds, or up to three developers, on prices against the developer, opportunities, delivery and payment structure.")}
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
                        <Link to={`/${item.kind === "compound" ? "compounds" : "developers"}/${encodeURIComponent(item.key)}`} dir="auto">
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
                {rows.map((row) => (
                  <tr key={row.label}>
                    <th scope="row">{t(row.label)}</th>
                    {compare.map((item) => {
                      const entry = get(item);
                      return (
                        <td key={item.key}>
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
                ))}
              </tbody>
            </table>
          </div>
        )}
        {compare.length > 0 && compare.length < 3 && (
          <p className="compare-more">
            <Link className="link-arrow" to={kind === "developer" ? "/developers" : "/compounds"}>
              <Plus size={15} /> {t(kind === "developer" ? "Add another developer" : "Add another compound")}
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}

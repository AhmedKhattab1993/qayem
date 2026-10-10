import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { money, number, quarterly, scrollBehavior, signed, titleCase, tone, sep, nameOf, place, year } from "../lib";
import { t } from "../locale";
import type { Unit } from "../types";
import { BothTag, LevelBadge } from "./Opportunity";
import { NameList } from "./Names";
import { Thumb } from "./Gallery";

export type UnitSort = "opportunity" | "launch_gap" | "peer_gap" | "price_asc" | "price_desc" | "area_desc" | "cash_ppm_asc" | "newest";

/** Type · area · bedrooms. Each part keeps its number and unit on one line. */
export const unitName = (unit: Pick<Unit, "property_type" | "bedrooms" | "area_m2">) =>
  [
    titleCase(unit.property_type),
    `${number(unit.area_m2)} ${t("m²")}`,
    unit.bedrooms ? t(unit.bedrooms === 1 ? "{n} bed" : "{n} beds", { n: number(unit.bedrooms), count: unit.bedrooms }) : "",
  ]
    .filter(Boolean)
    .map((part) => part.replace(/ /g, "\u00a0"))
    .join(sep());

export const termsLabel = (unit: Unit) =>
  unit.payment.terms === "plan"
    ? t("{n}-year plan", { n: number(unit.payment.years, 1) })
    : unit.payment.terms === "cash"
      ? t("Cash")
      : unit.payment.terms === "partial"
        ? t("Plan, term unknown")
        : t("Terms unknown");

export function UnitTable({
  items,
  sort,
  onSort,
  busy,
  caption = "Units compared with the developer and with similar units",
}: {
  items: Unit[];
  sort?: string;
  onSort?: (sort: UnitSort) => void;
  busy?: boolean;
  caption?: string;
}) {
  const header = (label: string, options: UnitSort[]) => {
    if (!onSort) return <th scope="col">{t(label)}</th>;
    const active = options.find((option) => option === sort);
    const next = active && options.length > 1 ? options[(options.indexOf(active) + 1) % options.length] : options[0];
    return (
      <th scope="col" aria-sort={active ? (active.endsWith("desc") ? "descending" : "ascending") : undefined}>
        <button className={active ? "is-active" : ""} onClick={() => onSort(next)}>
          {t(label)}
          {active && (active.endsWith("desc") ? <ArrowDown size={13} /> : <ArrowUp size={13} />)}
        </button>
      </th>
    );
  };
  // With a single source (AqarExit) a source column repeats the same name on every row.
  const sources = new Set(items.map((unit) => unit.source_name)).size > 1;
  return (
    <div className="ledger-frame">
      <div className={`ledger stack row-link unit-ledger${busy ? " is-busy" : ""}`}>
        <table>
          <caption className="sr-only">{t(caption)}</caption>
          <thead>
            <tr>
              <th scope="col">{t("Unit")}</th>
              {header("Asking price", ["price_asc", "price_desc"])}
              {header("Cash today", ["cash_ppm_asc"])}
              {header("Vs developer", ["launch_gap"])}
              {header("Vs similar units", ["peer_gap"])}
              {header("Opportunity", ["opportunity"])}
              {sources && <th scope="col">{t("Source")}</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((unit) => (
              <tr key={unit.id}>
                <th scope="row">
                  <Link className="ledger-title has-thumb" to={`/units/${unit.id}`}>
                    <Thumb url={unit.photo} />
                    <strong>{unitName(unit)}</strong>
                    <small>
                      <NameList
                        items={[
                          nameOf(unit.compound),
                          place(unit.district),
                          unit.contract_year ? t("signed {year}", { year: year(unit.contract_year) }) : null,
                        ]}
                      />
                    </small>
                  </Link>
                </th>
                <td data-label={t("Asking price")} className="num ledger-strong cell-price">{money(unit.price, true)}</td>
                <td data-label={t("Cash today")} className="cell-cash">
                  <span className="ledger-stack">
                    <span className="num">
                      {unit.payment.cash_equivalent != null ? money(unit.payment.cash_equivalent, true) : "—"}
                    </span>
                    <small>{termsLabel(unit)}</small>
                    {quarterly(unit.payment) != null && (
                      <small>{t("≈ {amount} a quarter", { amount: money(quarterly(unit.payment), true) })}</small>
                    )}
                  </span>
                </td>
                <td data-label={t("Vs developer")} className={`num cell-gap ${unit.launch?.same_finishing ? tone(unit.launch.gap) : ""}`}>
                  {unit.launch ? (
                    <span className="ledger-stack">
                      <span>{signed(unit.launch.gap)}</span>
                      {!unit.launch.same_finishing && <small>{t("other finishing")}</small>}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td data-label={t("Vs similar units")} data-short={t("Vs similar")} className={`num cell-gap ${unit.peers ? tone(unit.peers.gap) : ""}`}>
                  {unit.peers ? (
                    <span className="ledger-stack">
                      <span>{signed(unit.peers.gap)}</span>
                      <small>{t("{rank} of {n}", { rank: number(unit.peers.rank), n: number(unit.peers.count) })}</small>
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td data-label={t("Opportunity")} className="cell-level">
                  <LevelBadge level={unit.opportunity.level} />
                  <BothTag opportunity={unit.opportunity} />
                </td>
                {sources && (
                  <td data-label={t("Source")} className="ledger-muted cell-source">
                    {unit.source_name}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The similar units behind a comparison: the nearest six, and the rest on request. */
export function Comparables({ items, caption }: { items: Unit[]; caption: string }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 6);
  return (
    <>
      <UnitTable items={shown} caption={caption} />
      {items.length > 6 && (
        <button type="button" className="btn btn-sm comparables-more" aria-expanded={all} onClick={() => setAll((v) => !v)}>
          {all ? t("Show the nearest six") : t("Show all {n} similar units", { n: number(items.length) })}
        </button>
      )}
    </>
  );
}

/** After a page change, bring the top of the list (the element with id="results") back into view. */
export const scrollToResults = () =>
  requestAnimationFrame(() => document.getElementById("results")?.scrollIntoView({ block: "start", behavior: scrollBehavior() }));

export function Pager({
  page,
  pages,
  total,
  pageSize,
  onPage,
  noun = "units",
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  noun?: string;
}) {
  if (pages <= 1) return null;
  const start = (page - 1) * pageSize + 1;
  const around = Array.from({ length: Math.min(5, pages) }, (_, i) => Math.min(Math.max(1, page - 2), Math.max(1, pages - 4)) + i);
  const first = around[0];
  const last = around[around.length - 1];
  const numbers: (number | "…")[] = [
    ...(first > 1 ? [1, ...(first > 2 ? ["…" as const] : [])] : []),
    ...around,
    ...(last < pages ? [...(last < pages - 1 ? ["…" as const] : []), pages] : []),
  ];
  return (
    <div className="pager">
      <span className="muted num">
        {t("{start}–{end} of {total} " + noun, {
          start: number(start),
          end: number(Math.min(page * pageSize, total)),
          total: number(total),
        })}
      </span>
      <nav aria-label={t("Pages")}>
        <button onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label={t("Previous page")}>
          <ChevronLeft size={16} className="flip-rtl" />
        </button>
        {numbers.map((n, index) =>
          n === "…" ? (
            <span key={`gap-${index}`} className="pager-gap" aria-hidden="true">
              …
            </span>
          ) : (
            <button
              key={n}
              className={n === page ? "is-current num" : "num"}
              aria-current={n === page ? "page" : undefined}
              onClick={() => onPage(n)}
            >
              {number(n)}
            </button>
          ),
        )}
        <button onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label={t("Next page")}>
          <ChevronRight size={16} className="flip-rtl" />
        </button>
      </nav>
    </div>
  );
}

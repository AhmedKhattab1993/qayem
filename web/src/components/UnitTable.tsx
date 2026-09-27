import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp } from "lucide-react";
import { money, number, titleCase, sep } from "../lib";
import { t } from "../locale";
import type { Unit } from "../types";
import { GradeBadge, VerdictBadge } from "./Valuation";

export type UnitSort = "grade" | "value" | "price_asc" | "price_desc" | "area_desc" | "cash_ppm_asc";

export const unitPlace = (unit: Pick<Unit, "compound" | "district">) =>
  [unit.compound?.name, unit.district].filter(Boolean).join(sep());

export const unitName = (unit: Pick<Unit, "property_type" | "bedrooms" | "area_m2">) =>
  `${titleCase(unit.property_type)}${sep()}${number(unit.area_m2)} ${t("m²")}${
    unit.bedrooms ? `${sep()}${t(unit.bedrooms === 1 ? "{n} bed" : "{n} beds", { n: number(unit.bedrooms) })}` : ""
  }`;

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
  caption = "Units with their fair-value range",
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
  return (
    <div className={`ledger stack${busy ? " is-busy" : ""}`}>
      <table>
        <caption className="sr-only">{t(caption)}</caption>
        <thead>
          <tr>
            <th scope="col">{t("Unit")}</th>
            {header("Asking price", ["price_asc", "price_desc"])}
            {header("Cash today", ["cash_ppm_asc"])}
            <th scope="col">{t("Fair range")}</th>
            {header("Position", ["value"])}
            {header("Evidence", ["grade"])}
            <th scope="col">{t("Source")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((unit) => (
            <tr key={unit.id}>
              <th scope="row">
                <Link className="ledger-title" to={`/units/${unit.id}`}>
                  <strong>{unitName(unit)}</strong>
                  <small dir="auto">{unitPlace(unit)}</small>
                </Link>
              </th>
              <td data-label={t("Asking price")} className="num ledger-strong">{money(unit.price, true)}</td>
              <td data-label={t("Cash today")}>
                <span className="ledger-stack">
                  <span className="num">
                    {unit.payment.cash_equivalent != null ? money(unit.payment.cash_equivalent, true) : "—"}
                  </span>
                  <small>{termsLabel(unit)}</small>
                </span>
              </td>
              <td data-label={t("Fair range")} className="num">
                {unit.valuation.status === "valued"
                  ? `${money(unit.valuation.fair_low, true)} – ${money(unit.valuation.fair_high, true)}`
                  : t("Not valued")}
              </td>
              <td data-label={t("Position")}>
                <VerdictBadge verdict={unit.valuation.verdict} deviation={unit.valuation.deviation} />
              </td>
              <td data-label={t("Evidence")}>
                <GradeBadge grade={unit.valuation.grade} />
              </td>
              <td data-label={t("Source")} className="ledger-muted">{unit.source_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

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
  const numbers = Array.from({ length: Math.min(5, pages) }, (_, i) => Math.min(Math.max(1, page - 2), Math.max(1, pages - 4)) + i);
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
          ‹
        </button>
        {numbers.map((n) => (
          <button
            key={n}
            className={n === page ? "is-current num" : "num"}
            aria-current={n === page ? "page" : undefined}
            onClick={() => onPage(n)}
          >
            {number(n)}
          </button>
        ))}
        <button onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label={t("Next page")}>
          ›
        </button>
      </nav>
    </div>
  );
}

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, Search, X } from "lucide-react";
import { number, titleCase, useApi, useCatalog, sep } from "../lib";
import { t } from "../locale";
import type { Page, Unit } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager, UnitTable, type UnitSort } from "../components/UnitTable";

const KEYS = ["q", "district", "compound", "developer", "property_type", "verdict", "grade", "terms", "sort", "page"];

export default function Units() {
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const [search, setSearch] = useState(params.get("q") ?? "");
  useEffect(() => setSearch(params.get("q") ?? ""), [params]);
  const query = useMemo(() => {
    const next = new URLSearchParams();
    for (const key of KEYS) {
      const value = params.get(key);
      if (value) next.set(key, value);
    }
    return `/units?${next}`;
  }, [params]);
  const { data, error, retry } = useApi<Page<Unit>>(query);

  const update = (changes: Record<string, string>) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(changes)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      if (!("page" in changes)) next.delete("page");
      return next;
    });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    update({ q: search.trim() });
  };
  const select = (key: string, label: string, all: string, options: { value: string; label: string }[]) => (
    <label className="field">
      <span className="field-label">{t(label)}</span>
      <span className="select">
        <select value={params.get(key) ?? ""} onChange={(event) => update({ [key]: event.target.value })}>
          <option value="">{t(all)}</option>
          {params.get(key) && !options.some((o) => o.value === params.get(key)) && (
            <option value={params.get(key)!}>{params.get(key)}</option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown size={15} />
      </span>
    </label>
  );
  const filtered = KEYS.some((key) => key !== "sort" && key !== "page" && params.get(key));

  return (
    <div className="units page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Units")}</span>
          <h1 className="display">
            {t("Every resale unit,")} <em>{t("valued.")}</em>
          </h1>
          <p className="lede">
            {t(
              "Identified resale listings with their cash-equivalent price, Qayem’s fair range and the strength of the evidence behind it.",
            )}
          </p>
          <form className="searchbar" onSubmit={submit} role="search">
            <Search size={19} />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("A compound, developer, or district…")}
              aria-label={t("Search units")}
              maxLength={200}
            />
            {search && (
              <button
                type="button"
                className="searchbar-clear"
                aria-label={t("Clear search")}
                onClick={() => {
                  setSearch("");
                  update({ q: "" });
                }}
              >
                <X size={15} />
              </button>
            )}
            <button type="submit" className="btn btn-ink">
              {t("Search")}
            </button>
          </form>
        </div>
      </header>

      <div className="page">
        <div className="filters">
          {select(
            "district",
            "District",
            "All districts",
            catalog?.districts.filter((d) => d.units >= 10).map((d) => ({ value: d.key, label: d.name })) ?? [],
          )}
          {select(
            "developer",
            "Developer",
            "All developers",
            catalog?.developers.filter((d) => d.units >= 10).map((d) => ({ value: d.key, label: d.name })) ?? [],
          )}
          {select(
            "property_type",
            "Unit type",
            "All unit types",
            catalog?.property_types.map((p) => ({ value: p.value, label: `${titleCase(p.value)} (${number(p.count)})` })) ?? [],
          )}
          {select("verdict", "Position", "Any position", [
            { value: "below", label: t("Below fair range") },
            { value: "within", label: t("Within fair range") },
            { value: "above", label: t("Above fair range") },
            { value: "suspect", label: t("Check this listing") },
          ])}
          {select("grade", "Evidence", "Any evidence", [
            { value: "A", label: t("A · compound level") },
            { value: "B", label: t("B · developer level") },
            { value: "C", label: t("C · district level") },
          ])}
          {select("terms", "Payment", "Any payment", [
            { value: "cash", label: t("Cash") },
            { value: "plan", label: t("Installment plan") },
            { value: "partial", label: t("Plan, term unknown") },
            { value: "unknown", label: t("Terms unknown") },
          ])}
        </div>
        <div className="results-bar">
          <p className="muted num">
            {data ? t("{n} units", { n: number(data.total) }) : "—"}
            {params.get("compound") && `${sep()}${params.get("compound")}`}
          </p>
          {filtered && (
            <button className="link-arrow" onClick={() => setParams(new URLSearchParams())}>
              {t("Clear filters")}
            </button>
          )}
        </div>
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <EmptyState title={t("No units match.")} text={t("Try fewer filters or a broader search.")} />
        ) : (
          <>
            <UnitTable
              items={data.items}
              sort={params.get("sort") ?? "grade"}
              onSort={(sort: UnitSort) => update({ sort })}
            />
            <Pager
              page={data.page}
              pages={data.pages}
              total={data.total}
              pageSize={data.page_size}
              onPage={(page) => update({ page: String(page) })}
            />
          </>
        )}
        <p className="fineprint">
          {t(
            "Below or above means the cash-equivalent price falls outside the range that held 80% of comparable units in our backtest. It is a prompt to look closer, not a recommendation.",
          )}
        </p>
      </div>
    </div>
  );
}

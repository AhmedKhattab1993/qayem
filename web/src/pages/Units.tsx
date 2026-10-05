import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { number, titleCase, useApi, useCatalog, sep, nameOf, place } from "../lib";
import { t } from "../locale";
import type { Page, Unit } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager, UnitTable, scrollToResults, type UnitSort } from "../components/UnitTable";
import { levelText } from "../components/Opportunity";

const KEYS = ["q", "district", "compound", "developer", "property_type", "level", "terms", "launch", "sort", "page"];

export default function Units() {
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => setSearch(params.get("q") ?? ""), [params]);
  const query = useMemo(() => {
    const next = new URLSearchParams();
    for (const key of KEYS) {
      const value = params.get(key);
      if (value) next.set(key, value);
    }
    return `/units?${next}`;
  }, [params]);
  const { data, latest, error, retry } = useApi<Page<Unit>>(query);
  // While the next page or filter loads, the current list stays on screen, dimmed.
  const list = data ?? latest;

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
  const select = (key: string, label: string, all: string, options: { value: string; label: string }[], first?: string) => {
    // The default sort is the empty option, whether or not the link spells it out.
    const value = key === "sort" && params.get(key) === "opportunity" ? "" : (params.get(key) ?? "");
    return (
    <label className={`field field-${key}`}>
      <span className="field-label">{t(label)}</span>
      <span className="select">
        <select value={value} onChange={(event) => update({ [key]: event.target.value })}>
          <option value="">{t(first ?? all)}</option>
          {value && !options.some((o) => o.value === value) && <option value={value}>{value}</option>}
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
  };
  const filtered = KEYS.some((key) => key !== "sort" && key !== "page" && params.get(key));
  const active = ["district", "developer", "property_type", "level", "terms", "launch"].filter((key) => params.get(key)).length;
  const compoundKey = params.get("compound");
  const compound = compoundKey ? catalog?.compounds.find((c) => c.key === compoundKey) : undefined;

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
              "Every resale unit against the developer’s price today and the similar units listed in its compound, best opportunities first.",
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
        <div className="list-controls">
          <button
            type="button"
            className="btn btn-sm filters-toggle"
            aria-expanded={filtersOpen}
            aria-controls="unit-filters"
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <SlidersHorizontal size={15} />
            {t("Filters")}
            {active > 0 && <span className="count-pill num">{number(active)}</span>}
          </button>
          {select("sort", "Sort by", "", [
            { value: "launch_gap", label: t("Furthest below the developer") },
            { value: "peer_gap", label: t("Furthest below similar units") },
            { value: "price_asc", label: t("Price, low to high") },
            { value: "price_desc", label: t("Price, high to low") },
            { value: "cash_ppm_asc", label: t("Cheapest per m² in today’s money") },
            { value: "area_desc", label: t("Largest first") },
          ], "Best opportunities first")}
          <div className={`filters${filtersOpen ? " is-open" : ""}`} id="unit-filters">
            {select(
              "district",
              "District",
              "All districts",
              catalog?.districts.filter((d) => d.units >= 10).map((d) => ({ value: d.key, label: place(d.name)! })) ?? [],
            )}
            {select(
              "developer",
              "Developer",
              "All developers",
              catalog?.developers.filter((d) => d.units >= 10).map((d) => ({ value: d.key, label: nameOf(d)! })) ?? [],
            )}
            {select(
              "property_type",
              "Unit type",
              "All unit types",
              catalog?.property_types.map((p) => ({ value: p.value, label: `${titleCase(p.value)} (${number(p.count)})` })) ?? [],
            )}
            {select(
              "level",
              "Opportunity",
              "Any level",
              (["strong", "good", "in_line", "mixed", "pricier", "check", "unrated"] as const).map((level) => ({
                value: level,
                label: t(levelText[level]),
              })),
            )}
            {select("terms", "Payment", "Any payment", [
              { value: "cash", label: t("Cash") },
              { value: "plan", label: t("Installment plan") },
              { value: "partial", label: t("Plan, term unknown") },
              { value: "unknown", label: t("Terms unknown") },
            ])}
            {select("launch", "Developer price", "All units", [
              { value: "true", label: t("Developer selling similar units") },
            ])}
          </div>
          <div className="results-bar" id="results">
            <p className="muted num">
              {list ? t("{n} units", { n: number(list.total), count: list.total }) : "—"}
              {compoundKey && (
                <>
                  {sep()}
                  <button type="button" className="chip" onClick={() => update({ compound: "" })} aria-label={t("Remove filter: {name}", { name: nameOf(compound) ?? compoundKey })}>
                    <bdi>{nameOf(compound) ?? compoundKey}</bdi>
                    <X size={13} />
                  </button>
                </>
              )}
            </p>
            {filtered && (
              <button
                className="link-arrow"
                onClick={() => setParams(params.get("sort") ? new URLSearchParams({ sort: params.get("sort")! }) : new URLSearchParams())}
              >
                {t("Clear filters")}
              </button>
            )}
          </div>
        </div>
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !list ? (
          <Loading />
        ) : list.items.length === 0 ? (
          <EmptyState title={t("No units match.")} text={t("Try fewer filters or a broader search.")} />
        ) : (
          <>
            <UnitTable
              items={list.items}
              busy={!data}
              sort={params.get("sort") ?? "opportunity"}
              onSort={(sort: UnitSort) => update({ sort })}
            />
            <Pager
              page={list.page}
              pages={list.pages}
              total={list.total}
              pageSize={list.page_size}
              onPage={(page) => {
                update({ page: String(page) });
                scrollToResults();
              }}
            />
          </>
        )}
        <p className="fineprint">
          {t(
            "Vs developer compares the unit with the developer’s current price for similar units in the same compound; vs similar units compares it with the other resale units of the same type and size listed there, with its rank. Each gap is the less favourable of listed price and today’s money. A level is a prompt to look closer, not a recommendation.",
          )}
        </p>
      </div>
    </div>
  );
}

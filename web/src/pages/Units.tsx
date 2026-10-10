import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { BellPlus, BellRing, ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { api, money, number, titleCase, useApi, useCatalog, sep, nameOf, place, year } from "../lib";
import { useStore } from "../store";
import { searchQuery } from "../searches";
import { t } from "../locale";
import type { Page, Unit } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager, UnitTable, scrollToResults, type UnitSort } from "../components/UnitTable";
import { levelText } from "../components/Opportunity";

/** A buyer's budget and needs first, then where and what. */
const BUDGET = ["price_max", "cash_max", "signing_max", "bedrooms_min", "area_min", "area_max", "delivery"];
const FILTERS = [...BUDGET, "district", "developer", "property_type", "level", "terms", "launch"];
const KEYS = ["q", "compound", ...FILTERS, "sort", "page"];
const thisYear = new Date().getFullYear();
const AREAS: [number | null, number | null][] = [[null, 100], [100, 150], [150, 200], [200, 300], [300, null]];
const upTo = (amounts: number[]) => amounts.map((value) => ({ value: String(value), label: t("Up to {amount}", { amount: money(value, true) }) }));

export default function Units() {
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const { searches, toggleSearch, toast } = useStore();
  const saved = searchQuery(params);
  const isSaved = searches.some((item) => item.query === saved);
  const save = async () => {
    if (isSaved) return toggleSearch(saved, 0);
    try {
      // what counts as new later: listings indexed after the newest one matching now
      const newest = await api<Page<Unit>>(`/units?${saved}${saved ? "&" : ""}sort=newest&page_size=1`);
      toggleSearch(saved, newest.items[0]?.id ?? 0);
    } catch {
      toast("We could not save this search. Please try again.");
    }
  };
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
  // the two ends of the area range are one filter
  const active = FILTERS.filter((key) => key !== "area_max" && params.get(key)).length + (!params.get("area_min") && params.get("area_max") ? 1 : 0);
  const area = `${params.get("area_min") ?? ""}-${params.get("area_max") ?? ""}`;
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
            { value: "newest", label: t("Newest listings first") },
          ], "Best opportunities first")}
          <div className={`filters${filtersOpen ? " is-open" : ""}`} id="unit-filters">
            {select("price_max", "Asking price", "Any price", upTo([3e6, 5e6, 7.5e6, 10e6, 15e6, 20e6, 30e6, 50e6]))}
            {select("cash_max", "Cash today", "Any amount", upTo([2e6, 3e6, 5e6, 7.5e6, 10e6, 15e6, 20e6]))}
            {select("signing_max", "Paid at signing", "Any amount", upTo([5e5, 1e6, 1.5e6, 2e6, 3e6, 5e6, 7.5e6]))}
            {select(
              "bedrooms_min",
              "Bedrooms",
              "Any",
              [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: t("{n}+ bedrooms", { n: number(n) }) })),
            )}
            <label className="field field-area">
              <span className="field-label">{t("Area")}</span>
              <span className="select">
                <select
                  value={area === "-" ? "" : area}
                  onChange={(event) => {
                    const [min = "", max = ""] = event.target.value.split("-");
                    update({ area_min: min, area_max: max });
                  }}
                >
                  <option value="">{t("Any size")}</option>
                  {area !== "-" && !AREAS.some(([min, max]) => `${min ?? ""}-${max ?? ""}` === area) && (
                    <option value={area}>{area} {t("m²")}</option>
                  )}
                  {AREAS.map(([min, max]) => (
                    <option key={`${min}-${max}`} value={`${min ?? ""}-${max ?? ""}`}>
                      {min == null
                        ? t("Under {n} m²", { n: number(max) })
                        : max == null
                          ? t("{n} m² or more", { n: number(min) })
                          : t("{min}–{max} m²", { min: number(min), max: number(max) })}
                    </option>
                  ))}
                </select>
                <ChevronDown size={15} />
              </span>
            </label>
            {select("delivery", "Delivery", "Any time", [
              { value: "ready", label: t("Ready now") },
              ...Array.from({ length: 6 }, (_, i) => ({
                value: String(thisYear + i),
                label: t("By {year}", { year: year(thisYear + i) }),
              })),
            ])}
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
            {saved && (
              <button type="button" className={`btn btn-sm${isSaved ? " btn-ink" : ""}`} aria-pressed={isSaved} onClick={save}>
                {isSaved ? <BellRing size={15} /> : <BellPlus size={15} />} {t(isSaved ? "Search saved" : "Save this search")}
              </button>
            )}
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

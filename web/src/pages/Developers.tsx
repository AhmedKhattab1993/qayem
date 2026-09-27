import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, Search, X } from "lucide-react";
import { number, percent, signed, useApi, sep } from "../lib";
import { t } from "../locale";
import type { Developer, Page } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager } from "../components/UnitTable";

export default function Developers() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  useEffect(() => setSearch(params.get("q") ?? ""), [params]);
  const query = useMemo(() => {
    const next = new URLSearchParams();
    for (const key of ["q", "sort", "page"]) {
      const value = params.get(key);
      if (value) next.set(key, value);
    }
    return `/developers?${next}`;
  }, [params]);
  const { data, error, retry } = useApi<Page<Developer>>(query);
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

  return (
    <div className="developers page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Developers")}</span>
          <h1 className="display">
            {t("The name on the gate")} <em>{t("is priced in.")}</em>
          </h1>
          <p className="lede">
            {t(
              "How each developer’s resale units price against comparable units in the same districts, and what their stock looks like: delivery, payment plans and finishing.",
            )}
          </p>
          <form className="searchbar" onSubmit={submit} role="search">
            <Search size={19} />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("A developer or one of its compounds…")}
              aria-label={t("Search developers")}
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
        <div className="filters filters-2">
          <label className="field">
            <span className="field-label">{t("Sort by")}</span>
            <span className="select">
              <select value={params.get("sort") ?? "units"} onChange={(event) => update({ sort: event.target.value })}>
                <option value="units">{t("Most listings")}</option>
                <option value="premium_desc">{t("Highest premium")}</option>
                <option value="premium_asc">{t("Lowest premium")}</option>
                <option value="name">{t("Name")}</option>
              </select>
              <ChevronDown size={15} />
            </span>
          </label>
        </div>
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <EmptyState title={t("No developers match.")} text={t("Try a different name.")} />
        ) : (
          <>
            <div className="ledger stack">
              <table>
                <caption className="sr-only">{t("Developers with their premium against district norms")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("Developer")}</th>
                    <th scope="col">{t("Vs district")}</th>
                    <th scope="col">{t("Compounds")}</th>
                    <th scope="col">{t("Listings")}</th>
                    <th scope="col">{t("Ready")}</th>
                    <th scope="col">{t("On plans")}</th>
                    <th scope="col">{t("Plan discount")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((developer) => (
                    <tr key={developer.key}>
                      <th scope="row">
                        <Link className="ledger-title" to={`/developers/${encodeURIComponent(developer.key)}`}>
                          <strong dir="auto">{developer.name}</strong>
                          <small dir="auto">
                            {developer.districts
                              .slice(0, 2)
                              .map((d) => d.name)
                              .join(sep())}
                          </small>
                        </Link>
                      </th>
                      <td data-label={t("Vs district")} className={`num ledger-strong ${(developer.premium_vs_district ?? 0) >= 0 ? "is-up" : "is-down"}`}>
                        {signed(developer.premium_vs_district)}
                      </td>
                      <td data-label={t("Compounds")} className="num">{number(developer.compounds.length)}</td>
                      <td data-label={t("Listings")} className="num">{number(developer.units)}</td>
                      <td data-label={t("Ready")} className="num">{percent(developer.ready_share)}</td>
                      <td data-label={t("On plans")} className="num">{percent(developer.plan_share)}</td>
                      <td data-label={t("Plan discount")} className="num">{percent(developer.median_plan_discount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={data.page}
              pages={data.pages}
              total={data.total}
              pageSize={data.page_size}
              noun="developers"
              onPage={(page) => update({ page: String(page) })}
            />
          </>
        )}
        <p className="fineprint">
          {t(
            "Vs district is the average gap between the developer’s units and the benchmark for the same class in the same district, after adjusting for unit type, finishing, delivery and size. It needs at least five valued units, and twenty to appear in a premium ranking.",
          )}
        </p>
      </div>
    </div>
  );
}

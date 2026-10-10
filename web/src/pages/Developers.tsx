import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, Search, X } from "lucide-react";
import { number, percent, signed, useApi, tone, nameOf, place } from "../lib";
import { t } from "../locale";
import type { Developer, Page } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager, scrollToResults } from "../components/UnitTable";
import { NameList } from "../components/Names";

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
  const { data, latest, error, retry } = useApi<Page<Developer>>(query);
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
              "How each developer’s resale units compare with what it sells today, how many are real opportunities, and what the stock looks like: delivery, payment plans and finishing.",
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
                <option value="opportunities">{t("Most opportunities")}</option>
                <option value="gap_asc">{t("Resale furthest below the developer")}</option>
                <option value="gap_desc">{t("Resale furthest above the developer")}</option>
                <option value="name">{t("Name")}</option>
              </select>
              <ChevronDown size={15} />
            </span>
          </label>
        </div>
        <div className="results-bar" id="results">
          <p className="muted num">{list ? t("{n} developers", { n: number(list.total), count: list.total }) : "—"}</p>
        </div>
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !list ? (
          <Loading />
        ) : list.items.length === 0 ? (
          <EmptyState title={t("No developers match.")} text={t("Try a different name.")} />
        ) : (
          <>
            <div className="ledger-frame">
              <div className={`ledger stack row-link grid-cards${data ? "" : " is-busy"}`}>
                <table>
                  <caption className="sr-only">{t("Developers with their resale units against their prices today")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("Developer")}</th>
                      <th scope="col">{t("Resale vs developer")}</th>
                      <th scope="col">{t("Opportunities")}</th>
                      <th scope="col">{t("Compounds")}</th>
                      <th scope="col">{t("Listings")}</th>
                      <th scope="col">{t("Ready")}</th>
                      <th scope="col">{t("On plans")}</th>
                      <th scope="col">{t("Plan discount")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.items.map((developer) => (
                      <tr key={developer.key}>
                        <th scope="row">
                          <Link className="ledger-title" to={`/developers/${encodeURIComponent(developer.key)}`}>
                            <strong dir="auto">{nameOf(developer)}</strong>
                            <small>
                              <NameList items={developer.districts.slice(0, 2).map((d) => place(d.name))} />
                            </small>
                          </Link>
                        </th>
                        <td data-label={t("Resale vs developer")} className={`num ledger-strong ${tone(developer.launch?.median_gap)}`}>
                          {signed(developer.launch?.median_gap)}
                        </td>
                        <td data-label={t("Opportunities")} className="num">{developer.good_count ? number(developer.good_count) : "—"}</td>
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
            </div>
            <Pager
              page={list.page}
              pages={list.pages}
              total={list.total}
              pageSize={list.page_size}
              noun="developers"
              onPage={(page) => {
                update({ page: String(page) });
                scrollToResults();
              }}
            />
          </>
        )}
        <p className="fineprint">
          {t(
            "Resale vs developer is the median gap between the developer’s resale units and its own current units of the same type, finishing and similar size, on the less favourable of listed price and today’s money. A developer needs twenty such units to be ranked. Opportunities counts strong and good units.",
          )}
        </p>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, Search, X } from "lucide-react";
import { classLabel, money, number, percent, signed, useApi, useCatalog, tone, nameOf, place, sep } from "../lib";
import { t } from "../locale";
import type { Compound, District, Page } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager, scrollToResults } from "../components/UnitTable";
import { ScopeNote } from "../components/Opportunity";
import { ClassCards } from "../components/Entity";
import { NameList } from "../components/Names";

export default function Compounds() {
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog();
  const [search, setSearch] = useState(params.get("q") ?? "");
  useEffect(() => setSearch(params.get("q") ?? ""), [params]);
  const query = useMemo(() => {
    const next = new URLSearchParams();
    for (const key of ["q", "district", "developer", "sort", "page"]) {
      const value = params.get(key);
      if (value) next.set(key, value);
    }
    return `/compounds?${next}`;
  }, [params]);
  const { data, latest, error, retry } = useApi<Page<Compound> & { district: District | null }>(query);
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
  const district = list?.district;
  const developerKey = params.get("developer");
  const developer = developerKey ? catalog?.developers.find((d) => d.key === developerKey) : undefined;
  const sort = params.get("sort") ?? "units";

  return (
    <div className="compounds page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Compounds")}</span>
          <h1 className="display">
            {t("The compound")} <em>{t("sets the price.")}</em>
          </h1>
          <p className="lede">
            {t(
              "What resale units cost in each compound, what the developer asks there today, and how many units are real opportunities.",
            )}
          </p>
          <form className="searchbar" onSubmit={submit} role="search">
            <Search size={19} />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("A compound or developer…")}
              aria-label={t("Search compounds")}
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
            <span className="field-label">{t("District")}</span>
            <span className="select">
              <select value={params.get("district") ?? ""} onChange={(event) => update({ district: event.target.value })}>
                <option value="">{t("All districts")}</option>
                {catalog?.districts
                  .filter((d) => d.units >= 10)
                  .map((d) => (
                    <option key={d.key} value={d.key}>
                      {place(d.name)}
                    </option>
                  ))}
              </select>
              <ChevronDown size={15} />
            </span>
          </label>
          <label className="field">
            <span className="field-label">{t("Sort by")}</span>
            <span className="select">
              <select value={sort} onChange={(event) => update({ sort: event.target.value })}>
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

        {district && (
          <section className="district-card" aria-label={t("District summary")}>
            <div className="section-row">
              <div>
                <span className="eyebrow">{t("District benchmark")}</span>
                <h2 className="display">{place(district.name)}</h2>
              </div>
              <ScopeNote scope={district.scope} />
            </div>
            <ClassCards classes={district.classes} />
          </section>
        )}

        <div className="results-bar" id="results">
          <p className="muted num">
            {list ? t("{n} compounds", { n: number(list.total), count: list.total }) : "—"}
            {developerKey && (
              <>
                {sep()}
                <button type="button" className="chip" onClick={() => update({ developer: "" })} aria-label={t("Remove filter: {name}", { name: nameOf(developer) ?? developerKey })}>
                  <bdi>{nameOf(developer) ?? developerKey}</bdi>
                  <X size={13} />
                </button>
              </>
            )}
          </p>
        </div>
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !list ? (
          <Loading />
        ) : list.items.length === 0 ? (
          <EmptyState title={t("No compounds match.")} text={t("Try a different name or district.")} />
        ) : (
          <>
            <div className={`ledger stack row-link grid-cards${data ? "" : " is-busy"}`}>
              <table>
                <caption className="sr-only">{t("Compounds with their prices and opportunities")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("Compound")}</th>
                    <th scope="col">{t("Main class")}</th>
                    <th scope="col">{t("Resale / m²")}</th>
                    <th scope="col">{t("Developer today / m²")}</th>
                    <th scope="col">{t("Resale vs developer")}</th>
                    <th scope="col">{t("Opportunities")}</th>
                    <th scope="col">{t("Ready")}</th>
                    <th scope="col">{t("Listings")}</th>
                  </tr>
                </thead>
                <tbody>
                  {list.items.map((compound) => {
                    const main = [...compound.classes].sort((a, b) => b.units - a.units)[0];
                    return (
                      <tr key={compound.key}>
                        <th scope="row">
                          <Link className="ledger-title" to={`/compounds/${encodeURIComponent(compound.key)}`}>
                            <strong dir="auto">{nameOf(compound)}</strong>
                            <small>
                              <NameList items={[nameOf(compound.developer), place(compound.district)]} />
                            </small>
                          </Link>
                        </th>
                        <td data-label={t("Main class")}>{main ? classLabel(main.class) : "—"}</td>
                        <td data-label={t("Resale / m²")} className="num ledger-strong">{money(main?.median_asking_ppm, true)}</td>
                        <td data-label={t("Developer today / m²")} className="num">
                          {main?.developer_ppm ? money(main.developer_ppm, true) : "—"}
                        </td>
                        <td data-label={t("Resale vs developer")} className={`num ${tone(compound.launch?.median_gap)}`}>
                          {signed(compound.launch?.median_gap)}
                        </td>
                        <td data-label={t("Opportunities")} className="num">{compound.good_count ? number(compound.good_count) : "—"}</td>
                        <td data-label={t("Ready")} className="num">{percent(compound.ready_share)}</td>
                        <td data-label={t("Listings")} className="num">{number(compound.units)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pager
              page={list.page}
              pages={list.pages}
              total={list.total}
              pageSize={list.page_size}
              noun="compounds"
              onPage={(page) => {
                update({ page: String(page) });
                scrollToResults();
              }}
            />
          </>
        )}
        <p className="fineprint">
          {t(
            "Resale / m² is the median listed price of the most listed class: AqarExit units sell at their original contract price. Developer today / m² is the developer’s current list price for that class on Nawy. Resale vs developer is the median gap of like-for-like units, on the less favourable of listed price and today’s money. Opportunities counts strong and good units.",
          )}
        </p>
      </div>
    </div>
  );
}

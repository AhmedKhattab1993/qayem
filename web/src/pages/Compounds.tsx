import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, Search, X } from "lucide-react";
import { classLabel, money, number, percent, signed, useApi, useCatalog, sep } from "../lib";
import { t } from "../locale";
import type { Compound, District, Page } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { Pager } from "../components/UnitTable";
import { GradeBadge, ScopeNote } from "../components/Valuation";
import { ClassCards } from "../components/Entity";

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
  const { data, error, retry } = useApi<Page<Compound> & { district: District | null }>(query);
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
  const district = data?.district;
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
              "Fair cash value per m² for each compound, and how far it sits above or below comparable units in its district.",
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
                      {d.name}
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
                <option value="premium_desc">{t("Highest premium")}</option>
                <option value="premium_asc">{t("Lowest premium")}</option>
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
                <h2 className="display">{district.name}</h2>
              </div>
              <ScopeNote scope={district.scope} />
            </div>
            <ClassCards classes={district.classes} />
          </section>
        )}

        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <EmptyState title={t("No compounds match.")} text={t("Try a different name or district.")} />
        ) : (
          <>
            <div className="ledger stack">
              <table>
                <caption className="sr-only">{t("Compounds with their fair value and premium")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("Compound")}</th>
                    <th scope="col">{t("Main class")}</th>
                    <th scope="col">{t("Fair cash / m²")}</th>
                    <th scope="col">{t("Vs district")}</th>
                    <th scope="col">{t("Vs launch")}</th>
                    <th scope="col">{t("Ready")}</th>
                    <th scope="col">{t("Plan discount")}</th>
                    <th scope="col">{t("Listings")}</th>
                    <th scope="col">{t("Evidence")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((compound) => {
                    const main = [...compound.classes].sort((a, b) => b.units - a.units)[0];
                    return (
                      <tr key={compound.key}>
                        <th scope="row">
                          <Link className="ledger-title" to={`/compounds/${encodeURIComponent(compound.key)}`}>
                            <strong dir="auto">{compound.name}</strong>
                            <small dir="auto">
                              {[compound.developer?.name, compound.district].filter(Boolean).join(sep())}
                            </small>
                          </Link>
                        </th>
                        <td data-label={t("Main class")}>{main ? classLabel(main.class) : "—"}</td>
                        <td data-label={t("Fair cash / m²")} className="num ledger-strong">{main?.reference_ppm ? money(main.reference_ppm, true) : "—"}</td>
                        <td data-label={t("Vs district")} className={`num ${(compound.premium_vs_district ?? 0) >= 0 ? "is-up" : "is-down"}`}>
                          {signed(compound.premium_vs_district)}
                        </td>
                        <td data-label={t("Vs launch")} className="num">{signed(compound.launch?.median_spread)}</td>
                        <td data-label={t("Ready")} className="num">{percent(compound.ready_share)}</td>
                        <td data-label={t("Plan discount")} className="num">{percent(compound.median_plan_discount)}</td>
                        <td data-label={t("Listings")} className="num">{number(compound.units)}</td>
                        <td data-label={t("Evidence")}>
                          <GradeBadge grade={compound.grade} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pager
              page={data.page}
              pages={data.pages}
              total={data.total}
              pageSize={data.page_size}
              noun="compounds"
              onPage={(page) => update({ page: String(page) })}
            />
          </>
        )}
        <p className="fineprint">
          {t(
            "Fair cash / m² is for a finished, ready unit of typical size in the compound’s most listed class. Vs district compares it with the district’s own benchmark for the same class. Plan discount is how far the median installment headline sits above its value in today’s money. Vs launch is how far the developer’s current launch price sits above what the resale market pays for the same unit.",
          )}
        </p>
      </div>
    </div>
  );
}

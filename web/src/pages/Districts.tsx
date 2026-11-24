import { Link } from "react-router-dom";
import { Map as MapIcon } from "lucide-react";
import { classLabel, money, monthLabel, nameOf, number, periodLabel, sep, useApi } from "../lib";
import { t } from "../locale";
import type { Guide } from "../types";
import { ErrorState, Loading } from "../components/States";
import { GuideTabs } from "../components/GuideTabs";
import { NoSalePrices, RateNote } from "../components/Guide";

/** Every district with a published figure, region by region, each with its asking price per m². */
export default function Districts() {
  const { data, error, retry } = useApi<Guide>("/guide");
  // Listings no district could be matched to (no region) are in the figures, but are not a place to open.
  const districts = (data?.districts ?? []).filter((d) => d.region && (d.headline || d.listings >= 5));
  const regions = Object.entries(data?.regions ?? {})
    .map(([key, names]) => ({ key, names, places: districts.filter((d) => d.region === key) }))
    .filter((region) => region.places.length > 0);
  const known = new Set(regions.map((region) => region.key));
  const others = districts.filter((d) => !known.has(d.region));
  return (
    <div className="page-enter">
      <header className="page-head">
        <div className="page">
          <GuideTabs />
          <span className="eyebrow">{data ? t("Price guide, {month}", { month: monthLabel(data.index_month) }) : t("Districts")}</span>
          <h1 className="display">
            {t("Where to buy,")} <em>{t("district by district.")}</em>
          </h1>
          <p className="lede">
            {data
              ? t("The median asking price per m² in {n} districts, from listings seen {period}. Open a district for its sizes, delivery dates, compounds and resale against new.", {
                  n: number(districts.filter((d) => d.headline).length),
                  period: periodLabel(data.period),
                })
              : t("Resale prices per m², the developer’s prices today and the opportunities in each district, from every listing compared.")}
          </p>
          <div className="entity-bar">
            <Link className="btn btn-sm btn-primary" to="/map">
              <MapIcon size={15} /> {t("See prices on the map")}
            </Link>
          </div>
        </div>
      </header>
      <div className="page">
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : !data ? (
          <Loading />
        ) : (
          <div className="district-regions">
            {[...regions, ...(others.length ? [{ key: "other", names: { name: "Other", name_ar: "أخرى" }, places: others }] : [])].map((region) => (
              <section key={region.key} className="district-region" aria-labelledby={`region-${region.key}`}>
                <h2 id={`region-${region.key}`}>
                  {nameOf(region.names)}
                  <small className="num">{t("{n} districts", { n: number(region.places.length), count: region.places.length })}</small>
                </h2>
                <ul className="district-grid">
                  {region.places.map((district) => (
                    <li key={district.key}>
                      <Link to={`/districts/${encodeURIComponent(district.key)}`}>
                        <b dir="auto">{nameOf(district)}</b>
                        <small className="num">
                          {district.headline && `${classLabel(district.headline.class)}${sep()}`}
                          {t("{n} listings", { n: number(district.listings), count: district.listings })}
                        </small>
                        {district.headline && (
                          <span className="district-price num">
                            {money(district.headline.median_ppm, true)}
                            <small>/ {t("m²")}</small>
                          </span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
            <div>
              <NoSalePrices />
              <RateNote />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

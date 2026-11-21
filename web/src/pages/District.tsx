import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, BellRing, Calculator } from "lucide-react";
import { nameOf, number, place, sep, signed, useApi, useTitle } from "../lib";
import { t } from "../locale";
import type { District, Overview, Page, Unit } from "../types";
import { ErrorState, Loading } from "../components/States";
import { DivergingBars, ScopeNote } from "../components/Opportunity";
import { ClassCards, HistoryPanel, ProfileFacts } from "../components/Entity";
import { UnitTable } from "../components/UnitTable";
import { AlertSignup } from "../components/Capture";
import { Faq, districtFaq } from "../components/Faq";
import { track } from "../track";

export default function DistrictPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, missing, retry } = useApi<District>(`/districts/${encodeURIComponent(key)}`);
  const units = useApi<Page<Unit>>(`/units?district=${encodeURIComponent(key)}&page_size=10&sort=opportunity`);
  const [alerting, setAlerting] = useState(false);
  useTitle(data && place(data.name));
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const name = place(data.name)!;
  const compounds = data.compounds ?? [];
  const priced = compounds.filter((c) => c.median_gap != null && c.compared >= 5);
  const good = (data.opportunities.strong ?? 0) + (data.opportunities.good ?? 0);
  return (
    <div className="entity page-enter">
      <header className="page-head">
        <div className="page">
          <Link className="link-arrow back" to="/districts">
            <ArrowLeft size={15} className="flip-rtl" /> {t("All districts")}
          </Link>
          <span className="eyebrow">{t("District")}</span>
          <h1 className="display" dir="auto">
            {t("Resale opportunities in {name}", { name })}
          </h1>
          <p className="unit-place num">
            {t("{n} listings", { n: number(data.units), count: data.units })}
            {sep()}
            {t("{n} compounds", { n: number(data.compound_count), count: data.compound_count })}
            {sep()}
            {t("{n} strong or good opportunities", { n: number(good), count: good })}
          </p>
          <div className="entity-bar">
            <button
              type="button"
              className={`btn btn-sm${alerting ? " btn-ink" : ""}`}
              aria-expanded={alerting}
              onClick={() => {
                setAlerting((open) => !open);
                if (!alerting) track("alert_open", { entity: data.key, meta: { cta: "district_alert" } });
              }}
            >
              <BellRing size={15} /> {t("Alert me about deals here")}
            </button>
            <Link className="btn btn-sm btn-brass" to="/evaluate">
              <Calculator size={15} /> {t("Compare a unit here")}
            </Link>
          </div>
        </div>
      </header>

      <div className="page">
        {alerting && <AlertSignup query={`district=${encodeURIComponent(data.key)}`} label={name} />}
        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Prices here")}</span>
              <h2 className="display">{t("What resale units here cost")}</h2>
            </div>
            <ScopeNote scope={data.scope} />
          </div>
          <ClassCards classes={data.classes} />
        </section>

        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Its compounds")}</span>
              <h2 className="display">
                {t(priced.length ? "Resale against the developer, compound by compound" : "Where its resale units are")}
              </h2>
            </div>
            <Link className="link-arrow" to={`/compounds?district=${encodeURIComponent(data.key)}`}>
              {t("All {n} compounds", { n: number(data.compound_count), count: data.compound_count })}{" "}
              <ArrowUpRight size={16} className="flip-rtl" />
            </Link>
          </div>
          {priced.length > 0 && (
            <div className="chart-card">
              <DivergingBars
                items={[...priced]
                  .sort((a, b) => a.median_gap! - b.median_gap!)
                  .slice(0, 15)
                  .map((c) => ({
                    key: c.key,
                    label: nameOf(c)!,
                    meta: `${nameOf(c.developer) ?? ""}${c.developer ? sep() : ""}${t("{n} listings", { n: number(c.units), count: c.units })}`,
                    value: c.median_gap!,
                    to: `/compounds/${encodeURIComponent(c.key)}`,
                  }))}
              />
              <p className="fineprint">
                {t("Median gap of like-for-like resale units against the developer’s current price, on the less favourable of listed price and today’s money.")}
              </p>
            </div>
          )}
          <ul className="district-compounds">
            {compounds.slice(0, 24).map((c) => (
              <li key={c.key}>
                <Link to={`/compounds/${encodeURIComponent(c.key)}`}>
                  <b dir="auto">{nameOf(c)}</b>
                  <small className="num">
                    {t("{n} listings", { n: number(c.units), count: c.units })}
                    {c.good_count > 0 && `${sep()}${t("{n} opportunities", { n: number(c.good_count), count: c.good_count })}`}
                    {c.median_gap != null && `${sep()}${t("vs developer")} ${signed(c.median_gap)}`}
                  </small>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="section-tight split">
          <div>
            <span className="eyebrow">{t("Delivery and payment")}</span>
            <h2 className="display">{t("What you are really buying")}</h2>
            <ProfileFacts profile={data} />
          </div>
          <div>
            <span className="eyebrow">{t("Units")}</span>
            <h2 className="display">{t("Best opportunities first")}</h2>
            <p className="entity-link">
              <Link className="link-arrow" to={`/units?district=${encodeURIComponent(data.key)}`}>
                {t("All {n} units", { n: number(data.units), count: data.units })} <ArrowUpRight size={15} className="flip-rtl" />
              </Link>
            </p>
          </div>
        </section>

        <section className="section-tight">
          {units.data ? (
            <UnitTable items={units.data.items} caption="Units in this district" />
          ) : units.error ? (
            <ErrorState message={units.error} retry={units.retry} />
          ) : (
            <Loading />
          )}
        </section>

        <HistoryPanel history={data.history} overview={overview} />
        <Faq items={districtFaq(data)} />
      </div>
    </div>
  );
}

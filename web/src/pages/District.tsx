import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, BellRing, Ruler, Map as MapIcon } from "lucide-react";
import { nameOf, number, place, sep, signed, useApi, useTitle } from "../lib";
import { t } from "../locale";
import type { District, Overview } from "../types";
import { ErrorState, Loading } from "../components/States";
import { DivergingBars, ScopeNote } from "../components/Opportunity";
import { ClassCards, HistoryPanel, ProfileFacts } from "../components/Entity";
import { AlertSignup } from "../components/Capture";
import { Faq, districtFaq } from "../components/Faq";
import { track } from "../track";
import { GuideAnswer, SegmentTables, headlineOf } from "../components/Guide";

export default function DistrictPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, missing, retry } = useApi<District>(`/districts/${encodeURIComponent(key)}`);
  const [alerting, setAlerting] = useState(false);
  const hasUnits = Boolean(data && data.units > 0);
  useTitle(data && (data.name_ar ? nameOf({ name: data.name, name_ar: data.name_ar }) : place(data.name)));
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const name = data.name_ar ? nameOf({ name: data.name, name_ar: data.name_ar })! : place(data.name)!;
  const guide = data.guide;
  const headline = guide ? headlineOf(guide.segments, "*", guide.headline) : null;
  const listings = data.listings ?? data.units;
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
            {t("Property prices in {name}", { name })}
          </h1>
          {headline && <GuideAnswer place={name} segment={headline} period={guide?.period} />}
          <p className="unit-place num">
            {t("{n} listings", { n: number(listings), count: listings })}
            {hasUnits && (
              <>
                {sep()}
                {t("{n} compounds", { n: number(data.compound_count), count: data.compound_count })}
                {sep()}
                {t("{n} strong or good opportunities", { n: number(good), count: good })}
              </>
            )}
          </p>
          <div className="entity-bar">
            {hasUnits && (
              <button
                type="button"
                className={`btn btn-sm${alerting ? " btn-primary" : ""}`}
                aria-expanded={alerting}
                onClick={() => {
                  setAlerting((open) => !open);
                  if (!alerting) track("alert_open", { entity: data.key, meta: { cta: "district_alert" } });
                }}
              >
                <BellRing size={15} /> {t("Alert me about deals here")}
              </button>
            )}
            <Link className="btn btn-sm btn-accent" to="/evaluate">
              <Ruler size={15} /> {t("Check a price here")}
            </Link>
            <Link className="btn btn-sm" to={`/map?focus=${encodeURIComponent(data.key)}`}>
              <MapIcon size={15} /> {t("See it on the map")}
            </Link>
          </div>
        </div>
      </header>

      <div className="page">
        {alerting && <AlertSignup query={`district=${encodeURIComponent(data.key)}`} label={name} />}
        {guide && guide.segments.length > 0 && (
          <section className="section-tight" aria-labelledby="guide-heading">
            <span className="eyebrow">{t("Price guide")}</span>
            <h2 id="guide-heading" className="display section-title">
              {t("Asking prices in {name}, segment by segment", { name })}
            </h2>
            <SegmentTables segments={guide.segments} scope="*" period={guide.period} rules={overview?.guide?.rules} />
          </section>
        )}
        {!hasUnits && (
          <p className="notice notice-soft">
            <span>
              {t("Qayem has no identified resale units to compare in {name} yet: the figures above come from classified listings only.", { name })}{" "}
              <Link to="/districts">{t("All districts")}</Link>
            </span>
          </p>
        )}
        {hasUnits && (
          <>
        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Resale opportunities")}</span>
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

        <section className="section-tight">
          <span className="eyebrow">{t("Delivery and payment")}</span>
          <h2 className="display">{t("What you are really buying")}</h2>
          <ProfileFacts profile={data} />
        </section>

        <HistoryPanel history={data.history} overview={overview} />
          </>
        )}
        <Faq items={districtFaq(data)} />
      </div>
    </div>
  );
}

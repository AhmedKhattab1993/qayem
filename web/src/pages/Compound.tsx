import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, BellRing, Calculator } from "lucide-react";
import { number, signed, titleCase, useApi, useTitle, nameOf, place } from "../lib";
import { t } from "../locale";
import type { CompoundDetail, Overview, Page, Unit } from "../types";
import { ErrorState, Loading } from "../components/States";
import { EntityActions, ScopeNote } from "../components/Opportunity";
import { ClassCards, HistoryPanel, LaunchPanel, ProfileFacts } from "../components/Entity";
import { AlertSignup } from "../components/Capture";
import { Faq, compoundFaq } from "../components/Faq";
import { track } from "../track";
import { UnitTable } from "../components/UnitTable";
import { NameList } from "../components/Names";
import { GuideAnswer, SegmentTables, headlineOf } from "../components/Guide";

export default function CompoundPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, missing, retry } = useApi<CompoundDetail>(`/compounds/${encodeURIComponent(key)}`);
  const units = useApi<Page<Unit>>(`/units?compound=${encodeURIComponent(key)}&page_size=10&sort=opportunity`);
  const [alerting, setAlerting] = useState(false);
  useTitle(nameOf(data?.compound));
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const { compound, developer } = data;
  const guide = compound.guide;
  const headline = guide ? headlineOf(guide.segments, compound.key, guide.headline) : null;
  return (
    <div className="entity page-enter">
      <header className="page-head">
        <div className="page">
          <Link className="link-arrow back" to="/compounds">
            <ArrowLeft size={15} className="flip-rtl" /> {t("All compounds")}
          </Link>
          <span className="eyebrow">{t("Compound")}</span>
          <div className="entity-title">
            <h1 className="display" dir="auto">
              {nameOf(compound)}
            </h1>
          </div>
          <p className="unit-place">
            <NameList
              items={[
                compound.developer && (
                  <Link to={`/developers/${encodeURIComponent(compound.developer.key)}`}>{nameOf(compound.developer)}</Link>
                ),
                <Link to={`/districts/${encodeURIComponent(compound.district_key)}`}>{place(compound.district)}</Link>,
              ]}
            />
          </p>
          {headline && <GuideAnswer place={nameOf(compound)!} segment={headline} period={guide?.period} />}
          <div className="entity-bar">
            <EntityActions kind="compound" entityKey={compound.key} name={compound.name} />
            <button
              type="button"
              className={`btn btn-sm${alerting ? " btn-ink" : ""}`}
              aria-expanded={alerting}
              onClick={() => {
                setAlerting((open) => !open);
                if (!alerting) track("alert_open", { entity: compound.key, meta: { cta: "compound_alert" } });
              }}
            >
              <BellRing size={15} /> {t("Alert me about deals here")}
            </button>
            <Link className="btn btn-sm btn-brass" to={`/evaluate?compound=${encodeURIComponent(compound.name)}`}>
              <Calculator size={15} /> {t("Compare a unit here")}
            </Link>
            <Link className="btn btn-sm" to={`/evaluate?mode=sell&compound=${encodeURIComponent(compound.name)}`}>
              {t("Selling here?")}
            </Link>
          </div>
        </div>
      </header>

      <div className="page">
        {alerting && <AlertSignup query={`compound=${encodeURIComponent(compound.key)}`} label={nameOf(compound)!} />}
        {guide && guide.segments.some((s) => s.compound === compound.key) && (
          <section className="section-tight" aria-labelledby="guide-heading">
            <span className="eyebrow">{t("Price guide")}</span>
            <h2 id="guide-heading" className="display section-title">
              {t("Asking prices in {name}, segment by segment", { name: nameOf(compound) })}
            </h2>
            <SegmentTables segments={guide.segments} scope={compound.key} period={guide.period} rules={overview?.guide?.rules} />
          </section>
        )}
        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Resale opportunities")}</span>
              <h2 className="display">
                {compound.good_count
                  ? t("{n} strong or good opportunities", { n: number(compound.good_count), count: compound.good_count })
                  : t("What resale units here cost")}
              </h2>
            </div>
            <ScopeNote scope={compound.scope} />
          </div>
          <ClassCards classes={compound.classes} />
        </section>

        {/* Developer prices need a benchmark source; without one the comparison is not shown. */}
        {overview?.launch.units ? (
          <section className="section-tight">
            <span className="eyebrow">{t("Resale vs buying new")}</span>
            <h2 className="display section-title">{t("Against the developer’s price today")}</h2>
            <LaunchPanel launch={compound.launch} scope="compound" />
          </section>
        ) : null}

        <section className="section-tight split">
          <div>
            <span className="eyebrow">{t("Delivery and payment")}</span>
            <h2 className="display">{t("What you are really buying")}</h2>
            <ProfileFacts profile={compound} />
          </div>
          <div>
            <span className="eyebrow">{t("Stock on the resale market")}</span>
            <h2 className="display">{t("{n} listings", { n: number(compound.units), count: compound.units })}</h2>
            <ul className="type-mix">
              {Object.entries(compound.types).map(([type, count]) => (
                <li key={type}>
                  <span>{titleCase(type)}</span>
                  <b className="num">{number(count)}</b>
                </li>
              ))}
            </ul>
            <p className="muted num">
              {t("Sizes from {min} to {max} m²", { min: number(compound.area_range[0]), max: number(compound.area_range[1]) })}
            </p>
            {developer && (
              <p className="entity-link">
                <Link className="link-arrow" to={`/developers/${encodeURIComponent(developer.key)}`}>
                  {developer.launch?.median_gap != null
                    ? t("{developer}: resale {gap} vs its prices today, across {n} listings", {
                        developer: nameOf(developer),
                        gap: signed(developer.launch.median_gap),
                        n: number(developer.units),
                      })
                    : t("{developer}: {n} resale listings", { developer: nameOf(developer), n: number(developer.units) })}
                  <ArrowUpRight size={15} className="flip-rtl" />
                </Link>
              </p>
            )}
          </div>
        </section>

        <HistoryPanel history={compound.history} overview={overview} />

        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Units")}</span>
              <h2 className="display">{t("Best opportunities first")}</h2>
            </div>
            <Link className="link-arrow" to={`/units?compound=${encodeURIComponent(compound.key)}`}>
              {t("All {n} units", { n: number(compound.units), count: compound.units })} <ArrowUpRight size={16} className="flip-rtl" />
            </Link>
          </div>
          {units.data ? (
            <UnitTable items={units.data.items} caption="Units in this compound" />
          ) : units.error ? (
            <ErrorState message={units.error} retry={units.retry} />
          ) : (
            <Loading />
          )}
        </section>
        <Faq items={compoundFaq(compound)} />
      </div>
    </div>
  );
}

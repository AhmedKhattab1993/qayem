import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, CalendarClock } from "lucide-react";
import { number, signed, useApi, useTitle, sep, nameOf, place } from "../lib";
import { t } from "../locale";
import type { Developer, Overview } from "../types";
import { ErrorState, Loading } from "../components/States";
import { DivergingBars, EntityActions, ScopeNote } from "../components/Opportunity";
import { HistoryPending, LaunchPanel, ProfileFacts } from "../components/Entity";
import { NameList } from "../components/Names";

export default function DeveloperPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, missing, retry } = useApi<Developer>(`/developers/${encodeURIComponent(key)}`);
  useTitle(nameOf(data));
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const priced = data.compounds.filter((c) => c.median_gap != null);
  const changes = data.delivery_changes;
  return (
    <div className="entity page-enter">
      <header className="page-head">
        <div className="page">
          <Link className="link-arrow back" to="/developers">
            <ArrowLeft size={15} className="flip-rtl" /> {t("All developers")}
          </Link>
          <span className="eyebrow">{t("Developer")}</span>
          <h1 className="display" dir="auto">
            {nameOf(data)}
          </h1>
          <p className="unit-place">
            <NameList items={data.districts.slice(0, 4).map((d) => place(d.name))} />
          </p>
          <div className="entity-bar">
            <EntityActions kind="developer" entityKey={data.key} name={data.name} />
          </div>
        </div>
      </header>
      <div className="page">
        <section className="section-tight">
          <div className="kpis">
            <article className="kpi-feature">
              <span>{t("Resale vs its prices today")}</span>
              <strong className="num">{signed(data.launch?.median_gap)}</strong>
              <small>
                {data.launch?.median_gap == null
                  ? t("No like-for-like developer price yet")
                  : t("Median of {n} like-for-like resale units", { n: number(data.launch.compared) })}
              </small>
            </article>
            <article>
              <span>{t("Strong or good opportunities")}</span>
              <strong className="num">{number(data.good_count)}</strong>
              <small>{t("of {n} resale listings", { n: number(data.units) })}</small>
            </article>
            <article>
              <span>{t("Compounds")}</span>
              <strong className="num">{number(data.compounds.length)}</strong>
              <small>{t("{n} districts", { n: number(data.districts.length), count: data.districts.length })}</small>
            </article>
            <article>
              <span>{t("Resale listings")}</span>
              <strong className="num">{number(data.units)}</strong>
              <ScopeNote scope={data.scope} />
            </article>
          </div>
        </section>

        {overview?.launch.units ? (
          <section className="section-tight">
            <span className="eyebrow">{t("Resale vs buying new")}</span>
            <h2 className="display section-title">{t("Against the developer’s prices today")}</h2>
            <LaunchPanel launch={data.launch} scope="developer" />
          </section>
        ) : null}

        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Its compounds")}</span>
              <h2 className="display">
                {t(priced.length > 0 ? "Resale against the developer, compound by compound" : "Where its resale units are")}
              </h2>
            </div>
            <Link className="link-arrow" to={`/compounds?developer=${encodeURIComponent(data.key)}`}>
              {t("All {n} compounds", { n: number(data.compounds.length), count: data.compounds.length })}{" "}
              <ArrowUpRight size={16} className="flip-rtl" />
            </Link>
          </div>
          {priced.length > 0 && (
            <div className="chart-card">
              <DivergingBars
                items={[...priced]
                  .sort((a, b) => a.median_gap! - b.median_gap!)
                  .slice(0, 20)
                  .map((c) => ({
                    key: c.key,
                    label: nameOf(c)!,
                    meta: `${place(c.district)}${sep()}${t("{n} listings", { n: number(c.units), count: c.units })}`,
                    value: c.median_gap!,
                    to: `/compounds/${encodeURIComponent(c.key)}`,
                  }))}
              />
              <p className="fineprint">
                {t("Median gap of like-for-like resale units against the developer’s current price, on the less favourable of listed price and today’s money.")}
              </p>
            </div>
          )}
        </section>

        <section className="section-tight split">
          <div>
            <span className="eyebrow">{t("Delivery and payment")}</span>
            <h2 className="display">{t("What its resale stock looks like")}</h2>
            <ProfileFacts profile={data} />
          </div>
          <div>
            <span className="eyebrow">{t("Delivery reliability")}</span>
            <h2 className="display">{t("Promised dates, tracked")}</h2>
            <div className="reliability">
              <CalendarClock size={22} />
              <dl>
                <div>
                  <dt>{t("Units with a promised delivery date")}</dt>
                  <dd className="num">{number(changes.tracked_units)}</dd>
                </div>
                <div>
                  <dt>{t("Dates pushed later since we started watching")}</dt>
                  <dd className="num">{number(changes.postponed)}</dd>
                </div>
                <div>
                  <dt>{t("Dates brought forward")}</dt>
                  <dd className="num">{number(changes.brought_forward)}</dd>
                </div>
              </dl>
            </div>
            <p className="fineprint">
              {t(
                "Every re-crawl compares each unit’s promised handover date with the last one we saw. A pattern of postponements is a risk signal that marketing never shows.",
              )}
            </p>
            {data.compounds.length > priced.length && (
              <p className="muted">
                {t("{n} further compounds have no like-for-like developer price.", { n: number(data.compounds.length - priced.length), count: data.compounds.length - priced.length })}
              </p>
            )}
            <p className="entity-link">
              <Link className="link-arrow" to={`/units?developer=${encodeURIComponent(data.key)}&sort=opportunity`}>
                {t("See its units")} <ArrowUpRight size={15} className="flip-rtl" />
              </Link>
            </p>
          </div>
        </section>
        <HistoryPending overview={overview} />
      </div>
    </div>
  );
}

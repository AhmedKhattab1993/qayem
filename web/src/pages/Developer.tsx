import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, CalendarClock } from "lucide-react";
import { number, signed, useApi, sep } from "../lib";
import { t } from "../locale";
import type { Developer, Overview } from "../types";
import { ErrorState, Loading } from "../components/States";
import { EntityActions, PremiumBars, ScopeNote } from "../components/Valuation";
import { HistoryPending, LaunchPanel, ProfileFacts } from "../components/Entity";

export default function DeveloperPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, retry } = useApi<Developer>(`/developers/${encodeURIComponent(key)}`);
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} />
      </div>
    );
  if (!data) return <Loading />;
  const priced = data.compounds.filter((c) => c.premium_vs_district != null);
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
            {data.name}
          </h1>
          <p className="unit-place" dir="auto">
            {data.districts
              .slice(0, 4)
              .map((d) => d.name)
              .join(sep())}
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
              <span>{t("Premium vs district norm")}</span>
              <strong className="num">{signed(data.premium_vs_district)}</strong>
              <small>
                {data.premium_vs_district == null
                  ? t("Not enough valued units yet")
                  : t("Across {n} valued units, like for like", { n: number(data.premium_basis) })}
              </small>
            </article>
            <article>
              <span>{t("Compounds")}</span>
              <strong className="num">{number(data.compounds.length)}</strong>
              <small>{t("{n} districts", { n: number(data.districts.length) })}</small>
            </article>
            <article>
              <span>{t("Resale listings")}</span>
              <strong className="num">{number(data.units)}</strong>
              <ScopeNote scope={data.scope} />
            </article>
          </div>
        </section>

        <section className="section-tight">
          <span className="eyebrow">{t("Resale vs buying new")}</span>
          <h2 className="display section-title">{t("Against the developer’s launch prices")}</h2>
          <LaunchPanel launch={data.launch} scope="developer" />
        </section>

        {priced.length > 0 && (
          <section className="section-tight">
            <div className="section-row">
              <div>
                <span className="eyebrow">{t("Its compounds")}</span>
                <h2 className="display">{t("Premium against each district")}</h2>
              </div>
            </div>
            <div className="chart-card">
              <PremiumBars
                items={priced.slice(0, 20).map((c) => ({
                  key: c.key,
                  label: c.name,
                  meta: `${c.district}${sep()}${t("{n} listings", { n: number(c.units) })}`,
                  value: c.premium_vs_district!,
                  to: `/compounds/${encodeURIComponent(c.key)}`,
                }))}
              />
            </div>
          </section>
        )}

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
                {t("{n} further compounds have too few listings for a premium.", { n: number(data.compounds.length - priced.length) })}
              </p>
            )}
            <p className="entity-link">
              <Link className="link-arrow" to={`/units?developer=${encodeURIComponent(data.key)}&sort=value`}>
                {t("See its units")} <ArrowUpRight size={15} />
              </Link>
            </p>
          </div>
        </section>
        <HistoryPending overview={overview} />
      </div>
    </div>
  );
}

import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, Calculator } from "lucide-react";
import { number, signed, titleCase, useApi, useTitle, nameOf, place } from "../lib";
import { t } from "../locale";
import type { CompoundDetail, Overview, Page, Unit } from "../types";
import { ErrorState, Loading } from "../components/States";
import { EntityActions, ScopeNote } from "../components/Opportunity";
import { ClassCards, HistoryPending, LaunchPanel, ProfileFacts } from "../components/Entity";
import { UnitTable } from "../components/UnitTable";
import { NameList } from "../components/Names";

export default function CompoundPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, missing, retry } = useApi<CompoundDetail>(`/compounds/${encodeURIComponent(key)}`);
  const units = useApi<Page<Unit>>(`/units?compound=${encodeURIComponent(key)}&page_size=10&sort=opportunity`);
  useTitle(nameOf(data?.compound));
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const { compound, developer } = data;
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
                <Link to={`/compounds?district=${encodeURIComponent(compound.district_key)}`}>{place(compound.district)}</Link>,
              ]}
            />
          </p>
          <div className="entity-bar">
            <EntityActions kind="compound" entityKey={compound.key} name={compound.name} />
            <Link className="btn btn-sm btn-brass" to={`/evaluate?compound=${encodeURIComponent(compound.name)}`}>
              <Calculator size={15} /> {t("Compare a unit here")}
            </Link>
          </div>
        </div>
      </header>

      <div className="page">
        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Prices here")}</span>
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

        <HistoryPending overview={overview} />

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
      </div>
    </div>
  );
}

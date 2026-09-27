import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, Calculator } from "lucide-react";
import { number, signed, titleCase, useApi, sep } from "../lib";
import { t } from "../locale";
import type { CompoundDetail, Overview, Page, Unit } from "../types";
import { ErrorState, Loading } from "../components/States";
import { EntityActions, GradeBadge, ScopeNote } from "../components/Valuation";
import { ClassCards, HistoryPending, LaunchPanel, ProfileFacts } from "../components/Entity";
import { UnitTable } from "../components/UnitTable";

export default function CompoundPage({ overview }: { overview: Overview | null }) {
  const { key = "" } = useParams();
  const { data, error, retry } = useApi<CompoundDetail>(`/compounds/${encodeURIComponent(key)}`);
  const units = useApi<Page<Unit>>(`/units?compound=${encodeURIComponent(key)}&page_size=10&sort=value`);
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} />
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
              {compound.name}
            </h1>
            <GradeBadge grade={compound.grade} long />
          </div>
          <p className="unit-place" dir="auto">
            {compound.developer && (
              <Link to={`/developers/${encodeURIComponent(compound.developer.key)}`}>{compound.developer.name}</Link>
            )}
            <span>{sep()}</span>
            <Link to={`/compounds?district=${encodeURIComponent(compound.district_key)}`}>{compound.district}</Link>
          </p>
          <div className="entity-bar">
            <EntityActions kind="compound" entityKey={compound.key} name={compound.name} />
            <Link className="btn btn-sm btn-brass" to={`/evaluate?compound=${encodeURIComponent(compound.name)}`}>
              <Calculator size={15} /> {t("Value a unit here")}
            </Link>
          </div>
        </div>
      </header>

      <div className="page">
        <section className="section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("Fair value")}</span>
              <h2 className="display">
                {compound.premium_vs_district == null
                  ? t("Priced against its district")
                  : t("{premium} against comparable units in {district}", {
                      premium: signed(compound.premium_vs_district),
                      district: compound.district,
                    })}
              </h2>
            </div>
            <ScopeNote scope={compound.scope} />
          </div>
          <ClassCards classes={compound.classes} />
        </section>

        <section className="section-tight">
          <span className="eyebrow">{t("Resale vs buying new")}</span>
          <h2 className="display section-title">{t("Against the developer’s launch price")}</h2>
          <LaunchPanel launch={compound.launch} scope="compound" />
        </section>

        <section className="section-tight split">
          <div>
            <span className="eyebrow">{t("Delivery and payment")}</span>
            <h2 className="display">{t("What you are really buying")}</h2>
            <ProfileFacts profile={compound} />
          </div>
          <div>
            <span className="eyebrow">{t("Stock on the resale market")}</span>
            <h2 className="display">{t("{n} listings", { n: number(compound.units) })}</h2>
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
                  {t("{developer}: {premium} vs district across {n} listings", {
                    developer: developer.name,
                    premium: signed(developer.premium_vs_district),
                    n: number(developer.units),
                  })}
                  <ArrowUpRight size={15} />
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
              <h2 className="display">{t("Furthest below fair value first")}</h2>
            </div>
            <Link className="link-arrow" to={`/units?compound=${encodeURIComponent(compound.key)}`}>
              {t("All {n} units", { n: number(compound.units) })} <ArrowUpRight size={16} />
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

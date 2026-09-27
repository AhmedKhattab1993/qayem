import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { date, deliveryLabel, money, number, safeExternalUrl, titleCase, useApi, sep } from "../lib";
import { t } from "../locale";
import type { UnitDetail } from "../types";
import { ErrorState, Loading } from "../components/States";
import { BreakdownView, PaymentFacts, Unknowns, ValuationSummary } from "../components/Valuation";
import { UnitTable, unitName } from "../components/UnitTable";

export default function UnitPage() {
  const { id } = useParams();
  const valid = id && /^\d+$/.test(id);
  const { data, error, retry } = useApi<UnitDetail>(valid ? `/units/${id}` : null);
  const [fullText, setFullText] = useState(false);
  if (!valid) return <ErrorState message="This page is not available." />;
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} />
      </div>
    );
  if (!data) return <Loading label="Valuing the unit…" />;
  const { unit, breakdown, comparables } = data;
  const source = safeExternalUrl(unit.source_url);
  const facts: [string, string][] = [
    ["Unit type", titleCase(unit.property_type)],
    ["Area", `${number(unit.area_m2)} ${t("m²")}`],
    ["Bedrooms", unit.bedrooms == null ? t("Not provided") : unit.bedrooms === 0 ? t("Studio") : number(unit.bedrooms)],
    ["Bathrooms", number(unit.bathrooms)],
    ["Finishing", titleCase(unit.finishing_class === "unknown" ? null : unit.finishing_class)],
    ["Delivery", `${deliveryLabel(unit.delivery.bucket, unit.delivery.years)}${unit.delivery.date ? `${sep()}${date(unit.delivery.date, "month")}` : ""}`],
    ["Asking price per m²", money(unit.price_per_m2)],
    ["Last observed", date(unit.last_seen_at)],
  ];

  return (
    <div className="unit page-enter">
      <header className="page-head">
        <div className="page">
          <Link className="link-arrow back" to="/units">
            <ArrowLeft size={15} className="flip-rtl" /> {t("All units")}
          </Link>
          <span className="eyebrow">
            {t("Unit valuation")} <span className="num">#{unit.id}</span>
          </span>
          <h1 className="display unit-title">{unitName(unit)}</h1>
          <p className="unit-place" dir="auto">
            {unit.compound && <Link to={`/compounds/${encodeURIComponent(unit.compound.key)}`}>{unit.compound.name}</Link>}
            {unit.developer && (
              <>
                <span aria-hidden="true">{sep()}</span>
                <Link to={`/developers/${encodeURIComponent(unit.developer.key)}`}>{unit.developer.name}</Link>
              </>
            )}
            {unit.district && <span>{sep()}{unit.district}</span>}
          </p>
          <div className="tags">
            <span className="tag">{unit.source_name}</span>
            <span className={`tag ${unit.is_resale ? "tag-nile" : ""}`}>
              {t(unit.is_resale ? "Identified resale" : "Resale status unclassified")}
            </span>
            {unit.resale_evidence?.includes("verified by AqarExit") && (
              <span className="tag tag-nile">{t("Contract and receipts verified by AqarExit")}</span>
            )}
          </div>
        </div>
      </header>

      <div className="page unit-grid">
        <div className="unit-main">
          <section className="result-section">
            <h2>{t("The unit")}</h2>
            <dl className="facts">
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{t(label)}</dt>
                  <dd className="num" dir="auto">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            {unit.resale_evidence && (
              <p className="evidence">
                <span>{t("Resale evidence")}</span>
                <q dir="auto">{unit.resale_evidence}</q>
              </p>
            )}
          </section>
          <section className="result-section">
            <h2>{t("The payment plan, in today’s money")}</h2>
            <PaymentFacts payment={unit.payment} price={unit.price} />
          </section>
          {breakdown && (
            <section className="result-section">
              <h2>{t("How the fair value was built")}</h2>
              <BreakdownView breakdown={breakdown} cls={unit.class} />
            </section>
          )}
          <section className="result-section">
            <h2>{t("What this valuation cannot see")}</h2>
            <Unknowns items={unit.unknowns} />
          </section>
          {unit.description && (
            <section className="result-section">
              <h2>{t("In the listing’s own words")}</h2>
              <p className={`unit-text${fullText ? "" : " is-clamped"}`} dir="auto">
                {unit.description}
              </p>
              {unit.description.length > 420 && (
                <button className="link-arrow" aria-expanded={fullText} onClick={() => setFullText((v) => !v)}>
                  {t(fullText ? "Show less" : "Read full description")}
                </button>
              )}
            </section>
          )}
        </div>
        <aside className="unit-aside">
          <ValuationSummary valuation={unit.valuation} price={unit.price} />
          {source ? (
            <a className="btn btn-nile btn-block" href={source} target="_blank" rel="noopener noreferrer">
              {t("View on {source}", { source: unit.source_name })} <ExternalLink size={15} />
            </a>
          ) : (
            <p className="fineprint">{t("An original source link was not provided.")}</p>
          )}
          <Link
            className="btn btn-block"
            to={`/evaluate?${new URLSearchParams({
              property_type: unit.property_type,
              area: String(unit.area_m2),
              price: String(unit.price),
              ...(unit.compound ? { compound: unit.compound.name } : unit.district ? { district: unit.district } : {}),
              ...(unit.payment.terms === "plan" && unit.down_payment != null && unit.installment_months
                ? { down_payment: String(unit.down_payment), installment_years: String(unit.installment_months / 12) }
                : {}),
            })}`}
          >
            {t("Adjust the details and re-value")}
          </Link>
        </aside>
      </div>

      {comparables.length > 0 && (
        <section className="page section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("The evidence")}</span>
              <h2 className="display">{t("Closest comparable listings")}</h2>
            </div>
          </div>
          <UnitTable items={comparables} caption="Comparable listings" />
        </section>
      )}
    </div>
  );
}

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Bookmark, Check, ExternalLink, Plus, Share2 } from "lucide-react";
import { year, date, money, number, safeExternalUrl, titleCase, useApi, useTitle, sep, nameOf, place } from "../lib";
import { t } from "../locale";
import type { UnitDetail } from "../types";
import { ErrorState, Loading } from "../components/States";
import { OpportunitySummary, PaymentFacts, PeerPanel, Unknowns } from "../components/Opportunity";
import { Comparables, termsLabel, unitName } from "../components/UnitTable";
import { isPinned, useStore } from "../store";
import { NameList } from "../components/Names";
import { DeveloperPrice } from "../components/DeveloperPrice";
import { Gallery } from "../components/Gallery";
import { Glance } from "../components/Glance";

/** The pipeline records why a listing counts as resale in its own shorthand; say it in words. */
function evidenceText(raw: string) {
  const keyword = /keyword '([^']+)'/.exec(raw)?.[1];
  if (keyword) return t("The listing says «{word}» (resale).", { word: keyword });
  const known: [RegExp, string][] = [
    [/saleType=resale/, "Listed in Nawy’s resale section."],
    [/verified by AqarExit/, "A contract transfer (تنازل). AqarExit verified the contract and receipts."],
    [/contract-transfer/, "Listed on a contract-transfer (تنازل) marketplace."],
    [/تمليك/, "The listing says «تمليك» (freehold), wording used for resale."],
    [/\/resale catalogue/, "Listed in GPM’s resale catalogue."],
    [/owner-direct/, "Sold directly by the owner."],
    [/isResaleInstallment/, "Aqarmap marks it as a resale on installments."],
    [/^description$/, "The listing description says it is a resale."],
  ];
  const match = known.find(([pattern]) => pattern.test(raw));
  return match ? t(match[1]) : raw;
}

export default function UnitPage() {
  const { id } = useParams();
  const valid = id && /^\d+$/.test(id);
  const { data, error, missing, retry } = useApi<UnitDetail>(valid ? `/units/${id}` : null);
  const [fullText, setFullText] = useState(false);
  const { toast, watch, toggleWatch, compare, toggleCompare } = useStore();
  useTitle(data && [unitName(data.unit), nameOf(data.unit.compound)].filter(Boolean).join(sep()));
  if (!valid)
    return (
      <div className="page">
        <ErrorState message="This page is not available." missing />
      </div>
    );
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading label="Comparing the unit…" />;
  const { unit, comparables } = data;
  const source = safeExternalUrl(unit.source_url);
  const saved = isPinned(watch, "unit", String(unit.id));
  const comparing = isPinned(compare, "unit", String(unit.id));
  const share = async () => {
    const url = window.location.href;
    const title = `${unitName(unit)}${unit.compound ? `${sep()}${nameOf(unit.compound)}` : ""}`;
    try {
      if (navigator.share) return await navigator.share({ title, url });
      await navigator.clipboard.writeText(url);
      toast("Link copied");
    } catch (error) {
      if ((error as Error).name !== "AbortError") toast("Copy the link from the address bar to share this unit.");
    }
  };
  const facts: [string, string][] = [
    // Area, rooms, price per m² and delivery are in the tiles above.
    ["Unit type", titleCase(unit.property_type)],
    ["Finishing", titleCase(unit.finishing_class === "unknown" ? null : unit.finishing_class)],
    ...(unit.contract_year ? ([["Contract signed", year(unit.contract_year)]] as [string, string][]) : []),
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
            {t("Unit")} <span className="num">#{unit.id}</span>
          </span>
          <h1 className="display unit-title">{unitName(unit)}</h1>
          <p className="unit-place">
            <NameList
              items={[
                unit.compound && <Link to={`/compounds/${encodeURIComponent(unit.compound.key)}`}>{nameOf(unit.compound)}</Link>,
                unit.developer && (
                  <Link to={`/developers/${encodeURIComponent(unit.developer.key)}`}>{nameOf(unit.developer)}</Link>
                ),
                place(unit.district),
              ]}
            />
          </p>
          <div className="unit-price">
            <strong className="num">{money(unit.price)}</strong>
            <span className="muted">{termsLabel(unit)}</span>
          </div>
          <div className="tags">
            <span className="tag">{unit.source_name}</span>
            <span className={`tag ${unit.is_resale ? "tag-nile" : ""}`}>
              {t(unit.is_resale ? "Identified resale" : "Resale status unclassified")}
            </span>
            {unit.resale_evidence?.includes("verified by AqarExit") && (
              <span className="tag tag-nile">{t("Contract and receipts verified by AqarExit")}</span>
            )}
            <span className="unit-actions">
              <button
                type="button"
                className={`btn btn-sm${saved ? " btn-ink" : ""}`}
                aria-pressed={saved}
                onClick={() => toggleWatch({ kind: "unit", key: String(unit.id), name: unitName(unit) })}
              >
                <Bookmark size={15} fill={saved ? "currentColor" : "none"} /> {t(saved ? "Saved" : "Save")}
              </button>
              <button
                type="button"
                className={`btn btn-sm${comparing ? " btn-ink" : ""}`}
                aria-pressed={comparing}
                onClick={() => toggleCompare({ kind: "unit", key: String(unit.id), name: unitName(unit) })}
              >
                {comparing ? <Check size={15} /> : <Plus size={15} />} {t(comparing ? "In comparison" : "Compare")}
              </button>
              <button type="button" className="btn btn-sm" onClick={share}>
                <Share2 size={15} /> {t("Share")}
              </button>
            </span>
          </div>
        </div>
      </header>

      <div className="page unit-verdict">
        <OpportunitySummary unit={unit} wide>
          {source ? (
            <a className="btn btn-nile" href={source} target="_blank" rel="noopener noreferrer">
              {t("View on {source}", { source: unit.source_name })} <ExternalLink size={15} />
            </a>
          ) : (
            <p className="fineprint">{t("An original source link was not provided.")}</p>
          )}
          {unit.compound && (
            <Link
              className="btn"
              to={`/evaluate?${new URLSearchParams({
                property_type: unit.property_type,
                area: String(unit.area_m2),
                price: String(unit.price),
                compound: unit.compound.name,
                ...(unit.finishing_class !== "unknown" ? { finishing: unit.finishing_class } : {}),
                ...(unit.payment.terms === "plan" && unit.down_payment != null && unit.installment_months
                  ? { down_payment: String(unit.down_payment), installment_years: String(unit.installment_months / 12) }
                  : {}),
              })}`}
            >
              {t("Adjust the details and compare again")}
            </Link>
          )}
        </OpportunitySummary>
      </div>

      <div className="page">
        <Glance unit={unit} />
      </div>

      <div className={`page unit-grid${unit.images.length ? "" : " no-aside"}`}>
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
                <span>{evidenceText(unit.resale_evidence)}</span>
              </p>
            )}
            {unit.description && (
              <figure className="unit-quote">
                <figcaption>{t("In the listing’s own words")}</figcaption>
                <blockquote className={`unit-text${fullText ? "" : " is-clamped"}`} dir="auto">
                  {unit.description}
                </blockquote>
                {unit.description.length > 420 && (
                  <button className="link-arrow" aria-expanded={fullText} onClick={() => setFullText((v) => !v)}>
                    {t(fullText ? "Show less" : "Read full description")}
                  </button>
                )}
              </figure>
            )}
          </section>
          {unit.launch && (
            <section className="result-section">
              <h2>{t("Against the developer’s price today")}</h2>
              <DeveloperPrice unit={unit} />
            </section>
          )}
          {unit.peers && (
            <section className="result-section">
              <h2>{t("Against similar units listed now")}</h2>
              <PeerPanel peers={unit.peers} price_per_m2={unit.price_per_m2} />
            </section>
          )}
          <section className="result-section">
            <h2>{t("The payment plan, in today’s money")}</h2>
            <PaymentFacts payment={unit.payment} price={unit.price} />
          </section>
          <section className="result-section">
            <h2>{t("What this comparison cannot see")}</h2>
            <Unknowns items={unit.unknowns} />
          </section>
        </div>
        {unit.images.length > 0 && (
          <aside className="unit-aside">
            <Gallery images={unit.images} title={unitName(unit)} source={unit.source_name} />
          </aside>
        )}
      </div>

      {comparables.length > 0 && (
        <section className="page section-tight">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("The evidence")}</span>
              <h2 className="display">{t(unit.peers ? "The similar units it is ranked against" : "Closest units in the same compound")}</h2>
              <p className="muted section-note">
                {t(
                  unit.peers
                    ? "All {n}: same compound and unit type, within 1.5× the size, and the same finishing when enough share it. Nearest in size first, with the year each seller signed."
                    : "Same compound and property class, nearest in size first, with the year each seller signed.",
                  { n: number(comparables.length) },
                )}
              </p>
            </div>
          </div>
          <Comparables items={comparables} caption="Comparable listings" />
        </section>
      )}
    </div>
  );
}

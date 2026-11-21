import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Printer } from "lucide-react";
import { atSigning, date, money, nameOf, number, place, quarterly, signed, sep, tone, useApi, useTitle, year } from "../lib";
import { t } from "../locale";
import type { UnitDetail } from "../types";
import { ErrorState, Loading } from "../components/States";
import { BothTag, LevelBadge } from "../components/Opportunity";
import { termsLabel, unitName } from "../components/UnitTable";
import { Mark } from "../components/Brand";
import { ShareBar, unitShareText } from "../components/Share";
import { SendSheet } from "../components/Capture";
import { track } from "../track";

/** One page to forward or print: the unit, its price in today's money and both comparisons. */
export default function Sheet() {
  const { id = "" } = useParams();
  const valid = /^\d+$/.test(id);
  const { data, error, missing, retry } = useApi<UnitDetail>(valid ? `/units/${id}` : null);
  useTitle(data && `${t("Deal sheet")}${sep()}${unitName(data.unit)}`);
  useEffect(() => {
    if (valid) track("sheet_view", { unit_id: Number(id) });
  }, [id, valid]);
  if (!valid || error)
    return (
      <div className="page">
        <ErrorState message={error || "This page is not available."} retry={retry} missing={missing || !valid} />
      </div>
    );
  if (!data) return <Loading label="Comparing the unit…" />;
  const { unit } = data;
  const launch = unit.launch?.same_finishing ? unit.launch : null;
  const rows: [string, string, string?][] = [
    ["Asking price", money(unit.price), termsLabel(unit)],
    ["Worth in today’s money", money(unit.payment.cash_equivalent)],
    ...(atSigning(unit.price, unit.payment) != null ? ([["Paid at signing", money(atSigning(unit.price, unit.payment))]] as [string, string][]) : []),
    ...(quarterly(unit.payment) != null ? ([["Each quarter, if paid evenly", `≈ ${money(quarterly(unit.payment))}`]] as [string, string][]) : []),
    ["Price per m², as listed", money(unit.price_per_m2)],
    ...(unit.contract_year ? ([["Contract signed", year(unit.contract_year)]] as [string, string][]) : []),
  ];
  return (
    <div className="sheet-page page-enter">
      <div className="page sheet-tools no-print">
        <Link className="link-arrow back" to={`/units/${unit.id}`}>
          <ArrowLeft size={15} className="flip-rtl" /> {t("Back to the unit")}
        </Link>
        <span className="sheet-actions">
          <button type="button" className="btn btn-sm btn-ink" onClick={() => window.print()}>
            <Printer size={15} /> {t("Print or save as PDF")}
          </button>
          <ShareBar text={unitShareText(unit)} path={`/units/${unit.id}`} unitId={unit.id} sheet={false} />
        </span>
      </div>
      <article className="page sheet">
        <header className="sheet-head">
          <div>
            <span className="eyebrow no-rule">{t("Deal sheet")}</span>
            <h1>{unitName(unit)}</h1>
            <p className="muted">
              {[nameOf(unit.compound), nameOf(unit.developer), place(unit.district)].filter(Boolean).join(sep())}
            </p>
          </div>
          <span className="sheet-brand">
            <Mark size={34} />
            <b>{t("Qayem")}</b>
          </span>
        </header>
        <div className="sheet-verdict">
          <LevelBadge level={unit.opportunity.level} />
          <BothTag opportunity={unit.opportunity} />
        </div>
        <div className="sheet-gaps">
          <div>
            <span>{t("Vs the developer today")}</span>
            <strong className={`num ${launch ? tone(launch.gap) : ""}`}>{launch ? signed(launch.gap) : t("No like-for-like price")}</strong>
            {launch && (
              <small className="num">
                {t("A similar new unit: {price} in today’s money", { price: money(launch.developer_cash, true) })}
              </small>
            )}
          </div>
          <div>
            <span>{t("Vs similar units listed now")}</span>
            <strong className={`num ${unit.peers ? tone(unit.peers.gap) : ""}`}>{unit.peers ? signed(unit.peers.gap) : t("Too few to rank")}</strong>
            {unit.peers && (
              <small className="num">{t("{rank} of {n}, cheapest first", { rank: number(unit.peers.rank), n: number(unit.peers.count) })}</small>
            )}
          </div>
          {unit.launch?.since_contract && (
            <div>
              <span>{t("Developer price since the seller signed")}</span>
              <strong className={`num ${tone(unit.launch.since_contract.change)}`}>{signed(unit.launch.since_contract.change)}</strong>
              <small className="num">{t("Since {year}", { year: year(unit.launch.since_contract.year) })}</small>
            </div>
          )}
        </div>
        <dl className="facts facts-single sheet-facts">
          {rows.map(([label, value, note]) => (
            <div key={label}>
              <dt>{t(label)}</dt>
              <dd className="num">
                {value}
                {note && <small className="muted">{sep()}{note}</small>}
              </dd>
            </div>
          ))}
        </dl>
        <footer className="sheet-foot">
          <span className="num" dir="ltr">
            qayem.ai/units/{unit.id}
          </span>
          <span>{t("Checked {date}. Listed and developer list prices, not sale prices: confirm every detail with the seller and the developer.", { date: date(unit.last_seen_at) })}</span>
        </footer>
      </article>
      <div className="page">
        <SendSheet unitId={unit.id} compound={unit.compound} />
      </div>
    </div>
  );
}

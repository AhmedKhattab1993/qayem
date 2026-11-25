import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowUpRight, Download, Map as MapIcon } from "lucide-react";
import { classLabel, date, money, monthLabel, nameOf, number, percent, periodLabel, signed, tone, useApi, useTitle } from "../lib";
import { getLanguage, t } from "../locale";
import { ErrorState, Loading } from "../components/States";
import { ConfidenceBadge, NoSalePrices, RateNote, SourceMix, confidenceRules } from "../components/Guide";
import { MarketSignals } from "../components/Signals";
import type { GuideRow, Overview, QayemIndex } from "../types";

const COMPOUNDS_SHOWN = 25;
const CLASS_ORDER = ["apartment", "house", "chalet"];
const byClass = (rows: GuideRow[]) => [...rows].sort((a, b) => CLASS_ORDER.indexOf(a.class) - CLASS_ORDER.indexOf(b.class));

function IndexTable({
  caption,
  rows,
  names,
}: {
  caption: string;
  rows: { key: string; name: string; meta?: string; to: string; row: GuideRow; first: boolean }[];
  names: Record<string, string>;
}) {
  return (
    <div className="ledger-frame">
      <div className="ledger stack guide-ledger index-ledger">
        <table>
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              <th scope="col">{t("Place")}</th>
              <th scope="col">{t("Type")}</th>
              <th scope="col">{t("Asking / m²")}</th>
              <th scope="col">{t("Middle half / m²")}</th>
              <th scope="col">{t("Listings")}</th>
              <th scope="col">{t("Confidence")}</th>
              <th scope="col">{t("Resale vs new")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ key, name, meta, to, row, first }) => (
              <tr key={`${key}-${row.class}`} className={first ? "is-first" : "is-continued"}>
                <th scope="row">
                  <Link className="ledger-title" to={to}>
                    <strong dir="auto">{name}</strong>
                    {meta && <small dir="auto">{meta}</small>}
                  </Link>
                </th>
                <td data-label={t("Type")}>{classLabel(row.class)}</td>
                <td data-label={t("Asking / m²")} className="num ledger-strong">
                  {money(row.median_ppm, true)}
                </td>
                <td data-label={t("Middle half / m²")} className="num">
                  {money(row.p25_ppm, true)} – {money(row.p75_ppm, true)}
                </td>
                <td data-label={t("Listings")} className="num">
                  {number(row.count)}
                </td>
                <td data-label={t("Confidence")}>
                  <span className="ledger-stack">
                    <ConfidenceBadge confidence={row.confidence} />
                    <small>
                      <SourceMix sources={row.sources} names={names} />
                    </small>
                  </span>
                </td>
                <td data-label={t("Resale vs new")} className={`num ${tone(row.resale_vs_new)}`}>
                  {signed(row.resale_vs_new)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function IndexPage({ overview }: { overview: Overview | null }) {
  const { month } = useParams();
  const { data, error, missing, retry } = useApi<QayemIndex>(month ? `/index/${encodeURIComponent(month)}` : "/index");
  const [allCompounds, setAllCompounds] = useState(false);
  const arabic = getLanguage() === "ar";
  const title = data ? `${arabic ? data.name_ar : data.name} — ${monthLabel(data.month)}` : null;
  useTitle(title);
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} missing={missing} />
      </div>
    );
  if (!data) return <Loading />;
  const names = Object.fromEntries(data.counts.sources.map((s) => [s.id, s.name]));
  const label = monthLabel(data.month);
  const districtRows = data.districts.flatMap((d) =>
    byClass(d.classes).map((row, index) => ({
      key: d.key,
      name: nameOf(d)!,
      to: `/districts/${encodeURIComponent(d.key)}`,
      row,
      first: index === 0,
    })),
  );
  const compounds = [...data.compounds].sort((a, b) => b.count - a.count);
  const shown = allCompounds ? compounds : compounds.slice(0, COMPOUNDS_SHOWN);
  const compoundRows = shown.flatMap((c) =>
    byClass(c.classes).map((row, index) => ({
      key: c.key,
      name: nameOf(c)!,
      meta: nameOf({ name: c.district_name, name_ar: data.districts.find((d) => d.key === c.district)?.name_ar }),
      to: `/compounds/${encodeURIComponent(c.key)}`,
      row,
      first: index === 0,
    })),
  );
  const months = (overview?.index_months ?? [data.month]).filter(Boolean);
  const csv = `/data/qayem-index-${data.month}.csv`;
  const citation = `${data.attribution}, ${data.label}. ${data.licence}.`;

  return (
    <div className="index-page page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Monthly, every district and compound")}</span>
          <h1 className="display">
            {t("Qayem Index — {month}", { month: label })}
            {data.provisional && <span className="tag tag-provisional">{t("Provisional")}</span>}
          </h1>
          <p className="lede">
            {t("Asking prices per m² for {d} districts and {c} compounds, from {n} listings seen {period} across {s} sites, duplicates removed.", {
              d: number(data.districts.length),
              c: number(data.compounds.length),
              n: number(data.counts.kept),
              period: periodLabel(data.period),
              s: number(data.counts.sources.length),
            })}
          </p>
          {data.provisional && (
            <p className="fineprint">
              {t("Provisional: the month is not over, so these figures can still change until it closes. Each closed month keeps its own page.")}
            </p>
          )}
          <div className="entity-bar">
            <a className="btn btn-sm btn-primary" href={csv} download>
              <Download size={15} /> {t("Download this month (CSV)")}
            </a>
            <a className="btn btn-sm" href="/data/qayem-index-latest.csv" download>
              <Download size={15} /> {t("Latest month (CSV)")}
            </a>
            <Link className="btn btn-sm" to="/map">
              <MapIcon size={15} /> {t("See it on the map")}
            </Link>
          </div>
        </div>
      </header>

      <div className="page">
        <section className="section-tight" aria-labelledby="index-districts">
          <span className="eyebrow">{t("Districts")}</span>
          <h2 id="index-districts" className="display section-title">
            {t("Asking price per m² by district, {month}", { month: label })}
          </h2>
          <IndexTable caption={t("Qayem Index by district")} rows={districtRows} names={names} />
          <RateNote />
        </section>

        <section className="section-tight" aria-labelledby="index-compounds">
          <span className="eyebrow">{t("Compounds")}</span>
          <h2 id="index-compounds" className="display section-title">
            {t("Asking price per m² by compound, {month}", { month: label })}
          </h2>
          <IndexTable caption={t("Qayem Index by compound")} rows={compoundRows} names={names} />
          {compounds.length > COMPOUNDS_SHOWN && (
            <div className="section-foot">
              <button type="button" className="btn btn-sm" aria-expanded={allCompounds} onClick={() => setAllCompounds((all) => !all)}>
                {allCompounds
                  ? t("Show the {n} largest", { n: number(COMPOUNDS_SHOWN) })
                  : t("Show all {n} compounds", { n: number(compounds.length) })}
              </button>
            </div>
          )}
        </section>

        {data.changes.length > 0 && (
          <section className="section-tight" aria-labelledby="index-changes">
            <span className="eyebrow">{t("Since last month")}</span>
            <h2 id="index-changes" className="display section-title">
              {t("The biggest moves")}
            </h2>
            <ul className="index-changes">
              {data.changes.map((change) => (
                <li key={`${change.kind}-${change.key}-${change.class}`}>
                  <Link to={`/${change.kind === "compound" ? "compounds" : "districts"}/${encodeURIComponent(change.key)}`}>
                    <b dir="auto">{nameOf(change)}</b>
                    <small>{classLabel(change.class)}</small>
                  </Link>
                  <span className={`num ${tone(change.change)}`}>{signed(change.change, 1)}</span>
                  <small className="num">
                    {money(change.from, true)} → {money(change.to, true)}
                    {" · "}
                    {t("{n} listings", { n: number(change.count), count: change.count })}
                  </small>
                </li>
              ))}
            </ul>
          </section>
        )}

        <MarketSignals overview={overview} />

        <section className="section-tight split index-about">
          <div>
            <span className="eyebrow">{t("How it is made")}</span>
            <h2 className="display">{t("One named, dated set of figures")}</h2>
            <p>
              {t("Each figure is the median asking price per m² of the listings of one type in one place, seen in the month. Listings that appear on several sites count once; implausible prices are left out. {multi} of figures draw on more than one site.", {
                multi: percent(data.counts.multi_source_share),
              })}
            </p>
            <p className="fineprint">{confidenceRules(overview?.guide?.rules)}</p>
            <NoSalePrices />
            <p>
              <Link className="link-arrow" to="/methodology">
                {t("Read the methodology")} <ArrowUpRight size={15} className="flip-rtl" />
              </Link>
            </p>
          </div>
          <div>
            <span className="eyebrow">{t("Use and cite")}</span>
            <h2 className="display">{t("Free to reuse, with credit")}</h2>
            <p>
              {t("The Qayem Index is published under the Creative Commons Attribution 4.0 licence ({licence}): reuse it freely, including commercially, as long as you credit it.", {
                licence: data.licence,
              })}
            </p>
            <p className="index-cite">
              <span className="field-label">{t("Credit it as")}</span>
              <code dir="ltr">{citation}</code>
            </p>
            <p className="fineprint num">
              {t("Method version {version}. As of {date}. Only aggregates are published: no listing, seller or photo.", {
                version: data.method_version,
                date: date(data.as_of),
              })}
            </p>
            {months.length > 0 && (
              <nav aria-label={t("Index archive")} className="index-archive">
                <span className="field-label">{t("Every month")}</span>
                <ul>
                  {months.map((m) => (
                    <li key={m}>
                      {m === data.month ? (
                        <b aria-current="page">{monthLabel(m)}</b>
                      ) : (
                        <Link to={`/index/${m}`}>{monthLabel(m)}</Link>
                      )}
                      {" "}
                      <a href={`/data/qayem-index-${m}.csv`} download aria-label={t("CSV for {month}", { month: monthLabel(m) })}>
                        <bdi>CSV</bdi>
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

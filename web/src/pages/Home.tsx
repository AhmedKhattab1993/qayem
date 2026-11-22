import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Banknote, BarChart3, Building2, Landmark, Link2, Map as MapIcon, PlayCircle, Scale, Users } from "lucide-react";
import type { Guide, Overview } from "../types";
import { classLabel, date, money, monthLabel, number, percent, periodLabel, sep, signed, tone, useApi, useCatalog, nameOf } from "../lib";
import { ConfidenceBadge, NoSalePrices, RateNote } from "../components/Guide";
import { t } from "../locale";
import { ErrorState, Loading } from "../components/States";
import { DivergingBars, ScopeNote } from "../components/Opportunity";
import { Explainer, explainerLength, type ExplainerHandle } from "../components/Explainer";

/** The price guide's headline figures: the busiest districts, each a link to its guide, and the way into the map. */
function GuideHeadlines() {
  const { data } = useApi<Guide>("/guide");
  const places = (data?.districts ?? []).filter((d) => d.headline).slice(0, 6);
  if (!data || !places.length) return null;
  const month = monthLabel(data.index_month);
  return (
    <section className="page section guide-home" aria-labelledby="guide-heading">
      <div className="section-head">
        <div>
          <span className="eyebrow">{t("Price guide, {month}", { month })}</span>
          <h2 id="guide-heading" className="display">
            {t("What a square metre")} <em>{t("asks, place by place.")}</em>
          </h2>
        </div>
        <p className="lede">
          {t("Median asking prices from {n} listings across {s} sites, seen {period}, with duplicates removed. Every district and compound is on the map.", {
            n: number(data.counts.kept),
            s: number(data.counts.sources.length),
            period: periodLabel(data.period),
          })}
        </p>
      </div>
      <ul className="guide-cards">
        {places.map((d) => (
          <li key={d.key}>
            <Link to={`/districts/${encodeURIComponent(d.key)}`}>
              <span className="guide-card-head">
                <b dir="auto">{nameOf(d)}</b>
                <ConfidenceBadge confidence={d.headline!.confidence} />
              </span>
              <strong className="num">
                {money(d.headline!.median_ppm, true)} <small>/ {t("m²")}</small>
              </strong>
              <span className="muted num">
                {classLabel(d.headline!.class)}
                {sep()}
                {t("{n} listings", { n: number(d.headline!.count), count: d.headline!.count })}
              </span>
              {d.headline!.resale_vs_new != null && (
                <span className={`num guide-card-gap ${tone(d.headline!.resale_vs_new)}`}>
                  {t("Resale vs new {gap}", { gap: signed(d.headline!.resale_vs_new) })}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
      <div className="section-foot">
        <Link className="btn btn-brass" to="/map">
          <MapIcon size={16} /> {t("Open the price map")}
        </Link>
        <Link className="btn btn-ink" to="/index">
          <BarChart3 size={16} /> {t("The Qayem Index, {month}", { month })}
        </Link>
        <Link className="link-arrow" to="/districts">
          {t("All districts")} <ArrowUpRight size={16} className="flip-rtl" />
        </Link>
      </div>
      <NoSalePrices />
      <RateNote />
    </section>
  );
}

export default function Home({ data, error, retry }: { data: Overview | null; error: string; retry: () => void }) {
  const navigate = useNavigate();
  const explainer = useRef<ExplainerHandle>(null);
  const catalog = useCatalog();
  const [placeQuery, setPlaceQuery] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = placeQuery.trim();
    if (!value) {
      navigate("/map");
      return;
    }
    const lower = value.toLocaleLowerCase();
    const districtMatch = catalog?.districts.find((d) => d.name.toLocaleLowerCase() === lower || d.key === lower);
    if (districtMatch) {
      navigate(`/districts/${encodeURIComponent(districtMatch.key)}`);
      return;
    }
    const compoundMatch = catalog?.compounds.find((c) =>
      [c.name, c.name_ar].some((name) => name?.toLocaleLowerCase() === lower),
    );
    navigate(compoundMatch ? `/compounds/${encodeURIComponent(compoundMatch.key)}` : `/compounds?q=${encodeURIComponent(value)}`);
  };
  const gaps = data?.developer_gaps ?? [];
  const spread = [...gaps.slice(0, 5), ...gaps.slice(-5)].filter(
    (item, index, all) => all.findIndex((other) => other.key === item.key) === index,
  );
  const guideKept = data?.guide?.kept ?? data?.total_records ?? 0;

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-grid" aria-hidden="true" />
        <div className="page hero-inner">
          <div className="hero-copy page-enter">
            <span className="hero-live">
              <span className="live-dot" />
              {t("Egypt property price guide")}
              {sep()}
              {data ? t("observed {date}", { date: date(data.last_updated) }) : t("loading…")}
            </span>
            <h1 className="display">
              {t("What does property")}
              <br />
              <em>{t("really cost in Egypt?")}</em>
            </h1>
            <p className="hero-lede">
              {t(
                "Asking prices per m² across Egypt’s districts and compounds, from public listings with duplicates removed — plus a free check against the developer’s price today.",
              )}
            </p>
            <form className="hero-search" onSubmit={submit} role="search">
              <Building2 size={20} />
              <input
                value={placeQuery}
                onChange={(event) => setPlaceQuery(event.target.value)}
                placeholder={t("Search a district or compound")}
                aria-label={t("District or compound")}
                list="home-places"
                maxLength={200}
              />
              <datalist id="home-places">
                {catalog?.districts.map((d) => <option key={`d-${d.key}`} value={d.name} />)}
                {catalog?.compounds.map((c) => <option key={`c-${c.key}`} value={nameOf(c)} />)}
              </datalist>
              <button type="submit" className="btn btn-brass">
                {t("See prices")} <ArrowRight size={16} className="flip-rtl" />
              </button>
            </form>
            <div className="hero-alts">
              <Link className="hero-alt hero-alt-map" to="/map">
                <MapIcon size={15} /> {t("See prices on the map")}
              </Link>
              <Link className="hero-alt" to="/evaluate">
                <Scale size={15} /> {t("Check a unit price")}
              </Link>
              <Link className="hero-alt" to="/evaluate?mode=link">
                <Link2 size={15} /> {t("Or paste a listing link")}
              </Link>
              {data && !error && (
                <a
                  className="hero-alt"
                  href="#explainer"
                  onClick={(event) => {
                    event.preventDefault();
                    explainer.current?.play();
                  }}
                >
                  <PlayCircle size={15} /> {t("Watch how it works")} <span className="num">{explainerLength()}</span>
                </a>
              )}
            </div>
          </div>
          {data && (
            <dl className="hero-stats hero-stats-2 page-enter">
              <div>
                <dt>{t("Listings in the price guide")}</dt>
                <dd className="num">{number(guideKept)}</dd>
                <dd className="hero-stat-note">
                  <Link to="/index">
                    {t("The Qayem Index")} <ArrowRight size={13} className="flip-rtl" />
                  </Link>
                </dd>
              </div>
              <div>
                <dt>{t("Districts and compounds")}</dt>
                <dd className="num">
                  <Link to="/map">{number(data.district_count)} · {number(data.compound_count)}</Link>
                </dd>
                <dd className="hero-stat-note">
                  <Link to="/map">
                    {t("Open the price map")} <ArrowRight size={13} className="flip-rtl" />
                  </Link>
                </dd>
              </div>
            </dl>
          )}
        </div>
      </section>

      {error ? (
        <div className="page">
          <ErrorState message={error} retry={retry} />
        </div>
      ) : !data ? (
        <div className="page">
          <Loading />
        </div>
      ) : (
        <>
          <GuideHeadlines />

          <section className="page section" aria-labelledby="developers-heading">
            <div className="section-head">
              <div>
                <span className="eyebrow">{t("Resale against the developer")}</span>
                <h2 id="developers-heading" className="display">
                  {t("Same unit.")} <em>{t("Different price.")}</em>
                </h2>
              </div>
              <p className="lede">
                {t(
                  "AqarExit sellers transfer their contract at the price they paid. Developers have raised their prices since, so an old contract can cost well below buying the same unit new.",
                )}
              </p>
            </div>
            <div className="split">
              <div className="chart-card">
                <div className="chart-head">
                  <div>
                    <span className="eyebrow">{t("Resale vs the developer’s prices today")}</span>
                    <h3>{t("By developer")}</h3>
                  </div>
                  <Link className="link-arrow" to="/developers?sort=gap_asc">
                    {t("All developers")} <ArrowUpRight size={16} className="flip-rtl" />
                  </Link>
                </div>
                {spread.length > 0 ? (
                  <DivergingBars
                    items={spread.map((item) => ({
                      key: item.key,
                      label: nameOf(item)!,
                      meta: t("{n} units compared", { n: number(item.units), count: item.units }),
                      value: item.gap,
                      to: `/developers/${encodeURIComponent(item.key)}`,
                    }))}
                  />
                ) : (
                  <p className="muted">{t("Not enough like-for-like developer prices yet.")}</p>
                )}
                <p className="fineprint">
                  {t(
                    "Median gap of each developer’s resale units against its own current units of the same type, finishing and similar size. Developers with at least 20 such units.",
                  )}
                </p>
              </div>
              <div className="accuracy">
                <span className="eyebrow">{t("Since the sellers signed")}</span>
                <h3>{t("Developer list prices per m²")}</h3>
                <strong className="since-figure num">{t("{annual} a year", { annual: signed(data.since_contract.median_annual, 1) })}</strong>
                <p className="fineprint">
                  {t(
                    "Median yearly change between the price per m² a seller signed for and the developer’s price today for a similar unit in the same compound, across {n} units.",
                    { n: number(data.since_contract.units) },
                  )}
                </p>
              </div>
            </div>
          </section>

          <section className="weigh" aria-labelledby="cash-heading">
            <div className="page">
              <div className="section-head section-head-center">
                <span className="eyebrow">{t("How a unit is judged")}</span>
                <h2 id="cash-heading" className="display">
                  {t("Three steps,")} <em>{t("every unit.")}</em>
                </h2>
              </div>
              <Explainer ref={explainer} />
              <div className="weigh-steps">
                <article className="weigh-step">
                  <span className="weigh-index num">01</span>
                  <h3>
                    <Banknote size={18} /> {t("Convert to cash today")}
                  </h3>
                  <p>
                    {t(
                      "A headline price on a long plan is not a cash price. Remaining installments are discounted at {rate} a year. For half of installment listings that removes at least {cut} from the headline.",
                      { rate: percent(data.discount_rate), cut: percent(data.plan_median_discount) },
                    )}
                  </p>
                </article>
                <article className="weigh-step">
                  <span className="weigh-index num">02</span>
                  <h3>
                    <Landmark size={18} /> {t("Against the developer today")}
                  </h3>
                  <p>
                    {t(
                      "What the developer asks now for a unit of the same type, finishing and similar size in the same compound, from its current listings on Nawy.",
                    )}
                  </p>
                </article>
                <article className="weigh-step">
                  <span className="weigh-index num">03</span>
                  <h3>
                    <Users size={18} /> {t("Against similar units now")}
                  </h3>
                  <p>
                    {t(
                      "Where the unit ranks among at least four similar units listed in the same compound. A unit is an opportunity only if it is cheaper both as listed and in today’s money.",
                    )}
                  </p>
                </article>
              </div>
              <div className="home-evidence">
                <ScopeNote scope={data.scope} />
                <p className="fineprint">
                  {t(
                    data.history_ready
                      ? "{days} days of observation. Comparisons use listed contract prices and developer list prices: there is no fair price. Compound pages show how fast listings leave and how prices move."
                      : "{days} days of observation. Comparisons use listed contract prices and developer list prices: there is no fair price, and trends wait for eight weeks of history.",
                    { days: number(data.observation_days) },
                  )}{" "}
                  <Link to="/methodology#coverage">{t("See source coverage")}</Link>
                </p>
              </div>
              <div className="section-foot section-foot-center">
                <Link className="btn btn-ink" to="/evaluate">
                  <Scale size={16} /> {t("Compare a unit")}
                </Link>
                <Link className="link-arrow" to="/methodology">
                  {t("Read the methodology")} <ArrowUpRight size={16} className="flip-rtl" />
                </Link>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

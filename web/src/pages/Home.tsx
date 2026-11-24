import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ArrowUpRight, BarChart3, Download, Link2, Map as MapIcon, PlayCircle, Ruler, Search } from "lucide-react";
import type { ArticlePage, Guide, GuideDistrict, Overview } from "../types";
import { classLabel, date, money, monthLabel, number, percent, periodLabel, sep, signed, tone, useApi, useCatalog, nameOf } from "../lib";
import { ConfidenceBadge, NoSalePrices, RangeBar, RateNote } from "../components/Guide";
import { getLanguage, t } from "../locale";
import { ErrorState, Loading } from "../components/States";
import { DivergingBars } from "../components/Opportunity";
import { Explainer, explainerLength, type ExplainerHandle } from "../components/Explainer";

type Priced = GuideDistrict & { headline: NonNullable<GuideDistrict["headline"]> };
const priced = (guide: Guide | null) => (guide?.districts ?? []).filter((d): d is Priced => Boolean(d.headline && d.region));

/** The hero's picture is the product itself: the busiest districts as square tiles, each shaded by its price per m². */
function Mosaic({ guide }: { guide: Guide }) {
  const places = priced(guide).slice(0, 12);
  const order = [...places].sort((a, b) => a.headline.median_ppm - b.headline.median_ppm).map((d) => d.key);
  const step = (key: string) => Math.min(4, Math.floor((order.indexOf(key) / Math.max(1, order.length)) * 5)) + 1;
  return (
    <div className="mosaic page-enter">
      <ul>
        {places.map((d) => (
          <li key={d.key}>
            <Link
              to={`/districts/${encodeURIComponent(d.key)}`}
              className={`tile tile-${step(d.key)}`}
              title={`${classLabel(d.headline.class)}${sep()}${t("{n} listings", { n: number(d.headline.count), count: d.headline.count })}`}
            >
              <b dir="auto">{nameOf(d)}</b>
              <span className="num">{money(d.headline.median_ppm, true)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="mosaic-key">
        <span>{t("Median asking price per m², {month}", { month: monthLabel(guide.index_month) })}</span>
        <span className="mosaic-scale" aria-hidden="true">
          {t("Cheaper")}
          <i className="tile-1" />
          <i className="tile-2" />
          <i className="tile-3" />
          <i className="tile-4" />
          <i className="tile-5" />
          {t("Dearer")}
        </span>
      </p>
    </div>
  );
}

/** The price board: each district's middle half and median on one shared scale, so places compare at a glance. */
function PriceBoard({ guide }: { guide: Guide }) {
  const [region, setRegion] = useState("");
  const all = priced(guide);
  const regions = Object.entries(guide.regions).filter(([key]) => all.filter((d) => d.region === key).length >= 2);
  const rows = (region ? all.filter((d) => d.region === region) : all).slice(0, 8);
  const min = Math.min(...rows.map((d) => d.headline.p25_ppm));
  const max = Math.max(...rows.map((d) => d.headline.p75_ppm));
  const month = monthLabel(guide.index_month);
  return (
    <section className="page section" aria-labelledby="guide-heading">
      <div className="section-head">
        <div>
          <span className="eyebrow">{t("Price guide, {month}", { month })}</span>
          <h2 id="guide-heading" className="display">
            {t("What a square metre")} <em>{t("asks, place by place.")}</em>
          </h2>
        </div>
        <p className="lede">
          {t("Median asking prices from {n} listings across {s} sites, seen {period}, with duplicates removed. Every district and compound is on the map.", {
            n: number(guide.counts.kept),
            s: number(guide.counts.sources.length),
            period: periodLabel(guide.period),
          })}
        </p>
      </div>
      <div className="board">
        <div className="board-tools">
          <div className="segmented board-regions" role="group" aria-label={t("Region")}>
            <button type="button" aria-pressed={region === ""} onClick={() => setRegion("")}>
              {t("All Egypt")}
            </button>
            {regions.map(([key, names]) => (
              <button key={key} type="button" aria-pressed={region === key} onClick={() => setRegion(key)}>
                {nameOf(names)}
              </button>
            ))}
          </div>
          <p className="board-key">
            <span className="range-bar" aria-hidden="true">
              <i style={{ insetInlineStart: "15%", width: "70%" }} />
              <b style={{ insetInlineStart: "48%" }} />
            </span>
            {t("The bar is the middle half of asking prices; the mark is the median.")}
          </p>
        </div>
        <ol className="board-rows">
          {rows.map((d, index) => (
            <li key={d.key}>
              <Link to={`/districts/${encodeURIComponent(d.key)}`} className="board-row">
                <span className="board-rank num">{number(index + 1)}</span>
                <span className="board-place">
                  <b dir="auto">{nameOf(d)}</b>
                  <small className="num">
                    {classLabel(d.headline.class)}
                    {sep()}
                    {t("{n} listings", { n: number(d.headline.count), count: d.headline.count })}
                  </small>
                </span>
                <span className="board-range">
                  <RangeBar low={d.headline.p25_ppm} high={d.headline.p75_ppm} mid={d.headline.median_ppm} min={min} max={max} />
                  <small className="num">
                    {money(d.headline.p25_ppm, true)} – {money(d.headline.p75_ppm, true)}
                  </small>
                </span>
                <strong className="board-price num">
                  {money(d.headline.median_ppm, true)} <small>/ {t("m²")}</small>
                </strong>
                <span className="board-gap">
                  {d.headline.resale_vs_new != null ? (
                    <span className={`num gap-tag ${tone(d.headline.resale_vs_new)}`}>
                      {t("Resale vs new {gap}", { gap: signed(d.headline.resale_vs_new) })}
                    </span>
                  ) : (
                    <ConfidenceBadge confidence={d.headline.confidence} />
                  )}
                </span>
                <ArrowUpRight size={17} className="board-go flip-rtl" />
              </Link>
            </li>
          ))}
        </ol>
      </div>
      <div className="section-foot">
        <Link className="btn btn-primary" to="/map">
          <MapIcon size={16} /> {t("Open the price map")}
        </Link>
        <Link className="btn" to="/districts">
          {t("All districts")}
        </Link>
        <Link className="link-arrow" to="/index">
          {t("The Qayem Index, {month}", { month })} <ArrowUpRight size={16} className="flip-rtl" />
        </Link>
      </div>
      <NoSalePrices />
      <RateNote />
    </section>
  );
}

const DOORS = [
  {
    to: "/map",
    question: "What does a metre cost there?",
    text: "Every district and compound on one map, coloured by price.",
    action: "Open the price map",
  },
  {
    to: "/map?budget=10000000",
    question: "What does my budget buy?",
    text: "Set a budget and see where a typical unit fits it.",
    action: "Filter the map by budget",
  },
  {
    to: "/developers?sort=gap_asc",
    question: "Resale or new from the developer?",
    text: "Resale against the developer’s own price today, compound by compound.",
    action: "Compare developers",
  },
  {
    to: "/evaluate",
    question: "Is the price I was quoted fair?",
    text: "Describe the unit or paste its link: checked against the guide in a minute.",
    action: "Check a price",
  },
];

/** The monthly index, and what the figures say this month. */
function IndexAndArticles({ guide }: { guide: Guide }) {
  const { data } = useApi<ArticlePage>(`/articles?lang=${getLanguage()}&page=1`);
  const articles = (data?.items ?? []).slice(0, 3);
  const month = monthLabel(guide.index_month);
  return (
    <section className="page section read">
      <article className="index-card">
        <span className="eyebrow">{t("Published monthly")}</span>
        <h2 className="display">{t("The Qayem Index, {month}", { month })}</h2>
        <p>{t("One named, dated set of figures for every district and compound: free to quote, with credit.")}</p>
        <dl className="index-card-figures">
          <div>
            <dt>{t("Districts")}</dt>
            <dd className="num">{number(priced(guide).length)}</dd>
          </div>
          <div>
            <dt>{t("Published figures")}</dt>
            <dd className="num">{number(guide.counts.segments)}</dd>
          </div>
          <div>
            <dt>{t("High confidence")}</dt>
            <dd className="num">{number(guide.counts.high)}</dd>
          </div>
        </dl>
        <div className="index-card-actions">
          <Link className="btn btn-accent" to="/index">
            <BarChart3 size={16} /> {t("Open the index")}
          </Link>
          <a className="btn index-card-csv" href="/data/qayem-index-latest.csv" download>
            <Download size={16} /> {t("Download CSV")}
          </a>
        </div>
      </article>
      <div className="read-articles">
        <div className="section-row">
          <div>
            <span className="eyebrow">{t("Articles")}</span>
            <h2 className="display">{t("What the figures say")}</h2>
          </div>
          <Link className="link-arrow" to="/articles">
            {t("All articles")} <ArrowUpRight size={16} className="flip-rtl" />
          </Link>
        </div>
        {articles.length > 0 ? (
          <ol className="read-list">
            {articles.map((item) => (
              <li key={item.slug}>
                <Link to={`/articles/${encodeURIComponent(item.slug)}`}>
                  <small className="num">{date(item.published_at)}</small>
                  <b dir="auto">{item.title}</b>
                  <span dir="auto">{item.summary}</span>
                </Link>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">
            {t("Articles are written when the figures move. Until then, the method behind every number is one page.")}{" "}
            <Link className="link-arrow" to="/methodology">
              {t("Read the methodology")}
            </Link>
          </p>
        )}
      </div>
    </section>
  );
}

export default function Home({ data, error, retry }: { data: Overview | null; error: string; retry: () => void }) {
  const navigate = useNavigate();
  const explainer = useRef<ExplainerHandle>(null);
  const catalog = useCatalog();
  const { data: guide } = useApi<Guide>("/guide");
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
    const compoundMatch = catalog?.compounds.find((c) => [c.name, c.name_ar].some((name) => name?.toLocaleLowerCase() === lower));
    navigate(compoundMatch ? `/compounds/${encodeURIComponent(compoundMatch.key)}` : `/compounds?q=${encodeURIComponent(value)}`);
  };
  const spread = useMemo(() => {
    const gaps = data?.developer_gaps ?? [];
    return [...gaps.slice(0, 5), ...gaps.slice(-5)].filter((item, index, all) => all.findIndex((other) => other.key === item.key) === index);
  }, [data]);
  const counts = guide?.counts ?? data?.guide ?? null;
  const kept = counts?.kept ?? data?.total_records ?? 0;

  return (
    <div className="home">
      <section className="hero">
        <div className="page hero-inner">
          <div className="hero-copy page-enter">
            <span className="hero-live">
              <span className="live-dot" />
              {t("Egypt property price guide")}
              {sep()}
              {data ? t("observed {date}", { date: date(data.last_updated) }) : t("loading…")}
            </span>
            <h1 className="display">
              {t("The price of a square metre,")} <em>{t("anywhere in Egypt.")}</em>
            </h1>
            <p className="hero-lede">
              {t("The asking price per m² in every district and compound, from public listings with duplicates removed: the number, its date and its sources.")}
            </p>
            <form className="hero-search" onSubmit={submit} role="search">
              <Search size={20} />
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
              <button type="submit" className="btn btn-accent">
                {t("See prices")} <ArrowRight size={16} className="flip-rtl" />
              </button>
            </form>
            <div className="hero-alts">
              <Link className="hero-alt" to="/map">
                <MapIcon size={15} /> {t("See prices on the map")}
              </Link>
              <Link className="hero-alt" to="/evaluate">
                <Ruler size={15} /> {t("Check a price")}
              </Link>
              <Link className="hero-alt" to="/evaluate?mode=link">
                <Link2 size={15} /> {t("Or paste a listing link")}
              </Link>
            </div>
          </div>
          {guide ? <Mosaic guide={guide} /> : <div className="mosaic mosaic-wait" aria-hidden="true" />}
        </div>
        {data && (
          <dl className="page hero-stats page-enter">
            <div>
              <dd className="num">{number(kept)}</dd>
              <dt>{t("listings, duplicates removed")}</dt>
            </div>
            <div>
              <dd className="num">{number(data.district_count)}</dd>
              <dt>{t("districts")}</dt>
            </div>
            <div>
              <dd className="num">{number(data.compound_count)}</dd>
              <dt>{t("compounds")}</dt>
            </div>
            <div>
              <dd className="num">{number(counts?.sources.length ?? data.sources.length)}</dd>
              <dt>{t("public sources")}</dt>
            </div>
          </dl>
        )}
      </section>

      <section className="page section doors-section" aria-labelledby="doors-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">{t("Start from your question")}</span>
            <h2 id="doors-heading" className="display">
              {t("Four questions,")} <em>{t("one guide.")}</em>
            </h2>
          </div>
        </div>
        <ol className="doors">
          {DOORS.map((door, index) => (
            <li key={door.to}>
              <Link to={door.to} className="door">
                <span className="door-index num">{number(index + 1)}</span>
                <h3>{t(door.question)}</h3>
                <p>{t(door.text)}</p>
                <span className="door-action">
                  {t(door.action)} <ArrowRight size={16} className="flip-rtl" />
                </span>
              </Link>
            </li>
          ))}
        </ol>
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
          {guide && priced(guide).length > 0 && <PriceBoard guide={guide} />}

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
            <div className="split resale">
              <div className="chart-card">
                <div className="chart-head">
                  <div>
                    <span className="eyebrow no-rule">{t("Resale vs the developer’s prices today")}</span>
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
              <div className="since">
                <span className="eyebrow no-rule">{t("Since the sellers signed")}</span>
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

          {guide && <IndexAndArticles guide={guide} />}

          <section className="made" aria-labelledby="made-heading">
            <div className="page">
              <div className="section-head">
                <div>
                  <span className="eyebrow">{t("How the guide is made")}</span>
                  <h2 id="made-heading" className="display">
                    {t("Counted,")} <em>{t("not estimated.")}</em>
                  </h2>
                </div>
                <p className="lede">
                  {t("Egypt publishes no property sale prices. These are asking prices from public listings, not completed sales or valuations.")}
                </p>
              </div>
              <ol className="made-steps">
                <li>
                  <span className="made-index num">{number(1)}</span>
                  <h3>{t("Collect")}</h3>
                  <p>
                    {t("{n} public listings from {s} sites, read every night.", {
                      n: number(counts?.listings ?? data.total_records),
                      s: number(counts?.sources.length ?? data.sources.length),
                    })}
                  </p>
                </li>
                <li>
                  <span className="made-index num">{number(2)}</span>
                  <h3>{t("Remove duplicates")}</h3>
                  <p>{t("{n} listings posted on more than one site are counted once.", { n: number(counts?.duplicates ?? 0) })}</p>
                </li>
                <li>
                  <span className="made-index num">{number(3)}</span>
                  <h3>{t("Compare like with like")}</h3>
                  <p>{t("{n} segments: district, compound, type, size and delivery.", { n: number(counts?.segments ?? 0) })}</p>
                </li>
                <li>
                  <span className="made-index num">{number(4)}</span>
                  <h3>{t("Say how sure")}</h3>
                  <p>
                    {t("Every figure names its listings and sources. Installment plans are discounted at {rate} a year to today’s money.", {
                      rate: percent(data.discount_rate),
                    })}
                  </p>
                </li>
              </ol>
              <div className="made-film">
                <Explainer ref={explainer} />
                <div className="made-film-copy">
                  <h3>{t("Watch how Qayem works")}</h3>
                  <p>
                    {t(
                      "A headline price on a long plan is not a cash price. The film shows how a unit is checked: in today’s money, against the developer and against similar units.",
                    )}
                  </p>
                  <div className="section-foot">
                    <a
                      className="btn btn-primary"
                      href="#explainer"
                      onClick={(event) => {
                        event.preventDefault();
                        explainer.current?.play();
                      }}
                    >
                      <PlayCircle size={16} /> {t("Watch how it works")} <span className="num">{explainerLength()}</span>
                    </a>
                    <Link className="link-arrow" to="/methodology">
                      {t("Read the methodology")} <ArrowUpRight size={16} className="flip-rtl" />
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="page closing">
            <div>
              <h2 className="display">{t("Have a price in hand?")}</h2>
              <p>{t("Check it against the developer’s price today and the similar units listed now. Free, no sign-up.")}</p>
            </div>
            <div className="closing-actions">
              <Link className="btn btn-accent" to="/evaluate">
                <Ruler size={16} /> {t("Check a price")}
              </Link>
              <Link className="btn closing-link" to="/evaluate?mode=link">
                <Link2 size={16} /> {t("Or paste a listing link")}
              </Link>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

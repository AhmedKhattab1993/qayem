import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Banknote, Building2, Link2, Scale, Target } from "lucide-react";
import type { Overview } from "../types";
import { date, number, percent, useCatalog } from "../lib";
import { t } from "../locale";
import { ErrorState, Loading } from "../components/States";
import { PremiumBars, ScopeNote } from "../components/Valuation";

export default function Home({ data, error, retry }: { data: Overview | null; error: string; retry: () => void }) {
  const navigate = useNavigate();
  const catalog = useCatalog();
  const [compound, setCompound] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = compound.trim();
    const match = catalog?.compounds.find((c) => c.name.toLocaleLowerCase() === value.toLocaleLowerCase());
    navigate(match ? `/evaluate?compound=${encodeURIComponent(match.name)}` : value ? `/compounds?q=${encodeURIComponent(value)}` : "/evaluate");
  };
  const premiums = data?.developer_premiums ?? [];
  const spread = [...premiums.slice(0, 5), ...premiums.slice(-5)].filter(
    (item, index, all) => all.findIndex((other) => other.key === item.key) === index,
  );
  const backtest = data?.backtest;
  const naive = backtest?.naive_baseline;

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-grid" aria-hidden="true" />
        <div className="page hero-inner">
          <div className="hero-copy page-enter">
            <span className="hero-live">
              <span className="live-dot" />
              {t("Resale fair-value index")} ·{" "}
              {data ? t("observed {date}", { date: date(data.last_updated) }) : t("loading…")}
            </span>
            <h1 className="display">
              {t("What is it")}
              <br />
              <em>{t("really worth?")}</em>
            </h1>
            <p className="hero-lede">
              {t(
                "Qayem values Egypt’s resale units by compound, developer, delivery date and payment plan, not by area alone, and tells you how sure it is.",
              )}
            </p>
            <form className="hero-search" onSubmit={submit} role="search">
              <Building2 size={20} />
              <input
                value={compound}
                onChange={(event) => setCompound(event.target.value)}
                placeholder={t("Which compound is the unit in?")}
                aria-label={t("Compound")}
                list="home-compounds"
                maxLength={200}
              />
              <datalist id="home-compounds">
                {catalog?.compounds.map((c) => <option key={c.key} value={c.name} />)}
              </datalist>
              <button type="submit" className="btn btn-brass">
                {t("Value a unit")} <ArrowRight size={16} className="flip-rtl" />
              </button>
            </form>
            <Link className="hero-alt" to="/evaluate?mode=link">
              <Link2 size={15} /> {t("Or paste a listing link")}
            </Link>
          </div>
          {data && backtest && (
            <dl className="hero-stats page-enter">
              <div>
                <dt>{t("Resale units valued")}</dt>
                <dd className="num">{number(data.valued_count)}</dd>
              </div>
              <div>
                <dt>{t("Median error on held-out units")}</dt>
                <dd className="num">{percent(backtest.median_abs_error, 1)}</dd>
              </div>
              <div>
                <dt>{t("Compounds")}</dt>
                <dd className="num">{number(data.compound_count)}</dd>
              </div>
              <div>
                <dt>{t("Developers")}</dt>
                <dd className="num">{number(data.developer_count)}</dd>
              </div>
            </dl>
          )}
        </div>
      </section>

      {error ? (
        <div className="page">
          <ErrorState message={error} retry={retry} />
        </div>
      ) : !data || !backtest || !naive ? (
        <div className="page">
          <Loading />
        </div>
      ) : (
        <>
          <section className="page section" aria-labelledby="area-heading">
            <div className="section-head">
              <div>
                <span className="eyebrow">{t("Why area alone misleads")}</span>
                <h2 id="area-heading" className="display">
                  {t("Same district.")} <em>{t("Different price.")}</em>
                </h2>
              </div>
              <p className="lede">
                {t(
                  "In Egypt the developer and the compound set the price per m² as much as the neighbourhood does. Here is how each developer’s resale units price against comparable units in the same districts.",
                )}
              </p>
            </div>
            <div className="split">
              <div className="chart-card">
                <div className="chart-head">
                  <div>
                    <span className="eyebrow">{t("Developer premium vs district norm")}</span>
                    <h3>{t("Highest and lowest")}</h3>
                  </div>
                  <Link className="link-arrow" to="/developers?sort=premium_desc">
                    {t("All developers")} <ArrowUpRight size={16} />
                  </Link>
                </div>
                <PremiumBars
                  items={spread.map((item) => ({
                    key: item.key,
                    label: item.name,
                    meta: t("{n} listings", { n: number(item.units) }),
                    value: item.premium,
                    to: `/developers/${encodeURIComponent(item.key)}`,
                  }))}
                />
                <p className="fineprint">
                  {t("Adjusted for unit type, finishing, delivery and size. Developers with at least 40 resale listings.")}
                </p>
              </div>
              <div className="accuracy">
                <span className="eyebrow">{t("Held-out accuracy")}</span>
                <h3>{t("Typical valuation error")}</h3>
                <div className="accuracy-bars">
                  <div>
                    <span>{t("District median per m²")}</span>
                    <i style={{ width: "100%" }} className="is-naive" />
                    <b className="num">{percent(naive.median_abs_error, 1)}</b>
                  </div>
                  <div>
                    <span>{t("Qayem model")}</span>
                    <i
                      style={{ width: `${((naive.model_median_abs_error ?? 0) / (naive.median_abs_error || 1)) * 100}%` }}
                    />
                    <b className="num">{percent(naive.model_median_abs_error, 1)}</b>
                  </div>
                </div>
                <p className="fineprint">
                  {t(
                    "Median gap between each unit’s cash-equivalent asking price and the value predicted without it, across {n} units.",
                    { n: number(naive.evaluated) },
                  )}
                </p>
              </div>
            </div>
          </section>

          <section className="weigh" aria-labelledby="cash-heading">
            <div className="page">
              <div className="section-head section-head-center">
                <span className="eyebrow">{t("How a unit is valued")}</span>
                <h2 id="cash-heading" className="display">
                  {t("Three steps,")} <em>{t("every unit.")}</em>
                </h2>
              </div>
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
                    <Building2 size={18} /> {t("Price the compound, not the map")}
                  </h3>
                  <p>
                    {t(
                      "Each unit starts from its district, then its developer, then its compound, and is adjusted for unit type, finishing, delivery date and size.",
                    )}
                  </p>
                </article>
                <article className="weigh-step">
                  <span className="weigh-index num">03</span>
                  <h3>
                    <Target size={18} /> {t("Say how sure we are")}
                  </h3>
                  <p>
                    {t(
                      "Every value carries an evidence grade and a range measured on held-out units. When the evidence is thin, we say so instead of guessing.",
                    )}
                  </p>
                </article>
              </div>
              <div className="section-foot section-foot-center">
                <Link className="btn btn-ink" to="/evaluate">
                  <Scale size={16} /> {t("Evaluate a unit")}
                </Link>
                <Link className="link-arrow" to="/methodology">
                  {t("Read the methodology")} <ArrowUpRight size={16} />
                </Link>
              </div>
            </div>
          </section>

          <section className="page section" aria-labelledby="scope-heading">
            <div className="section-head">
              <div>
                <span className="eyebrow">{t("Know the evidence")}</span>
                <h2 id="scope-heading" className="display">
                  {t("What this is built on,")} <em>{t("plainly.")}</em>
                </h2>
              </div>
              <Link className="link-arrow" to="/methodology#coverage">
                {t("See source coverage")} <ArrowUpRight size={16} />
              </Link>
            </div>
            <div className="evidence-grid">
              <article>
                <ScopeNote scope={data.scope} />
                <p>
                  {t(
                    "Most identified resale listings come from one source. Figures describe the listings we index, not the whole Egyptian market.",
                  )}
                </p>
              </article>
              <article>
                <strong className="num">{number(data.observation_days)}</strong>
                <p>
                  {t(
                    "Days of observation so far. Price trends, time on market and delivery delays are shown only once there are at least eight weeks of history.",
                  )}
                </p>
              </article>
              <article>
                <strong className="num">{t("Asking")}</strong>
                <p>
                  {t(
                    "Prices are what sellers ask, not what buyers paid. Egypt publishes no resale transaction prices, so a fair value is where comparable asking prices sit.",
                  )}
                </p>
              </article>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

import { ArrowDown, Banknote, Building2, CalendarClock, FileQuestion, Files, Gavel, History, Layers3, ScanLine } from "lucide-react";
import { planLabel, bucketLabel, classLabel, date, number, percent, signed, titleCase, sep } from "../lib";
import { t } from "../locale";
import type { Overview } from "../types";
import { ErrorState, Loading } from "../components/States";
import { GradeBadge, ScopeNote } from "../components/Valuation";

const limits = [
  {
    icon: ScanLine,
    title: "Asking prices, not sale prices",
    text: "Egypt publishes no resale transaction prices. A fair value is where comparable asking prices sit once payment plans are converted to cash, and final deals are often lower.",
  },
  {
    icon: Building2,
    title: "Floor, view and orientation",
    text: "Sources rarely publish them, so they are not in the model. A sea-view or garden unit can be worth well above its compound’s norm.",
  },
  {
    icon: Gavel,
    title: "Legal status",
    text: "Registration, contract type and outstanding dues are not published. Confirm them with the developer before paying anything.",
  },
  {
    icon: Banknote,
    title: "Transfer fees and deposits",
    text: "Developers charge different transfer fees, and maintenance deposits may or may not be paid. The cost calculator uses editable assumptions.",
  },
  {
    icon: Files,
    title: "Listings, not unique units",
    text: "The same unit can appear on several platforms or be listed twice by different brokers. Counts are listings.",
  },
  {
    icon: History,
    title: "History is still short",
    text: "Price trends, time on market and delivery postponements need repeated observation. They appear once there are eight weeks of history.",
  },
  {
    icon: Layers3,
    title: "Launch prices are list prices",
    text: "Developer launch prices come from the developers’ own current listings on Nawy. Negotiated discounts and private offers are not visible.",
  },
  {
    icon: FileQuestion,
    title: "Resale, with its evidence",
    text: "The resale signal comes from a source field, a dedicated resale catalogue, or a keyword. It is shown on every unit.",
  },
];

const deliveryOrder = ["ready", "under_1y", "1_2y", "2_3y", "3y_plus", "unknown"];

export default function Methodology({ overview, error, retry }: { overview: Overview | null; error: string; retry: () => void }) {
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} />
      </div>
    );
  if (!overview) return <Loading />;
  const { backtest, effects } = overview;
  const naive = backtest.naive_baseline;
  const types = Object.entries(effects.type).filter(([, value]) => Math.abs(value) > 0.001);
  return (
    <div className="method page-enter">
      <header className="method-hero">
        <div className="page method-hero-inner">
          <div>
            <span className="eyebrow">{t("Methodology")}</span>
            <h1 className="display">
              {t("How a fair value")} <em>{t("is built, and tested.")}</em>
            </h1>
            <p className="lede">
              {t(
                "Every fair value on Qayem comes from one published model, checked against units it has not seen. Here is the model, its accuracy, and what it cannot know.",
              )}
            </p>
            <a className="btn btn-brass" href="#accuracy">
              {t("See the accuracy")} <ArrowDown size={16} />
            </a>
          </div>
          <dl className="method-snapshot">
            <div>
              <dt>{t("Resale units")}</dt>
              <dd className="num">{number(overview.total_resale)}</dd>
            </div>
            <div>
              <dt>{t("Valued")}</dt>
              <dd className="num">{number(overview.valued_count)}</dd>
            </div>
            <div>
              <dt>{t("Model trained on")}</dt>
              <dd className="num">{number(backtest.trained_on)}</dd>
            </div>
            <div>
              <dt>{t("Observation window")}</dt>
              <dd className="num method-dates">
                {date(overview.first_observed)} → {date(overview.last_updated)}
              </dd>
            </div>
          </dl>
        </div>
      </header>

      <section className="page section" aria-labelledby="model-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">01{sep()}{t("The model")}</span>
            <h2 id="model-heading" className="display">
              {t("Compound first,")} <em>{t("then the unit.")}</em>
            </h2>
          </div>
          <p className="lede">
            {t(
              "Price per m² is modelled in cash-equivalent terms. Each unit starts from its property class across Egypt, then moves towards its district, its developer within that district, and its compound, each by as much as the number of listings there justifies.",
            )}
          </p>
        </div>
        <div className="formula-card">
          <code dir="ltr">
            log(cash EGP/m²) = class + district + developer + compound + type + finishing + delivery + plan + size
          </code>
          <p>
            {t(
              "A level with n listings moves n ÷ (n + {k}) of the way from its parent, so a compound with four listings moves halfway. Unit adjustments are fitted jointly with the levels.",
              { k: number(effects.shrinkage) },
            )}
          </p>
        </div>
        <div className="effects">
          <article>
            <h3>{t("Finishing")}</h3>
            <p className="muted">{t("Against a finished unit")}</p>
            <ul>
              {Object.entries(effects.finishing).map(([level, value]) => (
                <li key={level}>
                  <span>{titleCase(level)}</span>
                  <b className="num">{signed(value, 1)}</b>
                </li>
              ))}
            </ul>
          </article>
          <article>
            <h3>{t("Delivery")}</h3>
            <p className="muted">{t("Against a ready unit, after converting to cash")}</p>
            <ul>
              {deliveryOrder
                .filter((bucket) => bucket in effects.delivery)
                .map((bucket) => (
                  <li key={bucket}>
                    <span>{bucketLabel(bucket)}</span>
                    <b className="num">{signed(effects.delivery[bucket], 1)}</b>
                  </li>
                ))}
            </ul>
          </article>
          <article>
            <h3>{t("Payment plan")}</h3>
            <p className="muted">{t("Cash-equivalent price against a cash unit")}</p>
            <ul>
              {Object.entries(effects.plan).map(([bucket, value]) => (
                <li key={bucket}>
                  <span>{planLabel(bucket)}</span>
                  <b className="num">{signed(value, 1)}</b>
                </li>
              ))}
            </ul>
          </article>
          <article>
            <h3>{t("Unit type")}</h3>
            <p className="muted">{t("Against an apartment, chalet or villa in the same place")}</p>
            <ul>
              {types.map(([type, value]) => (
                <li key={type}>
                  <span>{titleCase(type)}</span>
                  <b className="num">{signed(value, 1)}</b>
                </li>
              ))}
            </ul>
          </article>
          <article>
            <h3>{t("Size")}</h3>
            <p className="muted">{t("Price per m² when the area doubles")}</p>
            <ul>
              {Object.entries(effects.area_doubling).map(([cls, value]) => (
                <li key={cls}>
                  <span>{classLabel(cls)}</span>
                  <b className="num">{signed(value, 1)}</b>
                </li>
              ))}
            </ul>
          </article>
        </div>
        <p className="fineprint">
          {t(
            "These effects are fitted from the data, not assumed. The payment-plan effect shows how buyers actually price long plans: less steeply than a flat discount rate. Listings more than 2.5× away from their district norm are excluded from fitting and flagged “check this listing”.",
          )}
        </p>
      </section>

      <section className="page section" id="accuracy" aria-labelledby="accuracy-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">02{sep()}{t("Accuracy")}</span>
            <h2 id="accuracy-heading" className="display">
              {t("Tested on units")} <em>{t("it has not seen.")}</em>
            </h2>
          </div>
          <p className="lede">
            {t(
              "Each of {n} listings is valued with itself removed from the data, and the prediction is compared with its cash-equivalent asking price. The ranges shown on every unit are the 10th to 90th percentile of these errors.",
              { n: number(backtest.evaluated) },
            )}
          </p>
        </div>
        <div className="ledger stack backtest">
          <table>
            <caption className="sr-only">{t("Backtest by evidence grade")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("Evidence")}</th>
                <th scope="col">{t("Units tested")}</th>
                <th scope="col">{t("Median error")}</th>
                <th scope="col">{t("Within ±10%")}</th>
                <th scope="col">{t("Within ±20%")}</th>
                <th scope="col">{t("80% range")}</th>
              </tr>
            </thead>
            <tbody>
              {backtest.grades.map((grade) => (
                <tr key={grade.grade}>
                  <th scope="row">
                    <GradeBadge grade={grade.grade} long />
                  </th>
                  <td data-label={t("Units tested")} className="num">{number(grade.count)}</td>
                  <td data-label={t("Median error")} className="num ledger-strong">{percent(grade.median_abs_error, 1)}</td>
                  <td data-label={t("Within ±10%")} className="num">{percent(grade.within_10pct)}</td>
                  <td data-label={t("Within ±20%")} className="num">{percent(grade.within_20pct)}</td>
                  <td data-label={t("80% range")} className="num">
                    {signed(grade.range_low_pct)} … {signed(grade.range_high_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="kpis">
          <article>
            <span>{t("District median per m² (the naive method)")}</span>
            <strong className="num">{percent(naive.median_abs_error, 1)}</strong>
            <small>{t("Median error on the same {n} units", { n: number(naive.evaluated) })}</small>
          </article>
          <article className="kpi-feature">
            <span>{t("Qayem model")}</span>
            <strong className="num">{percent(naive.model_median_abs_error, 1)}</strong>
            <small>{t("Median error on the same units")}</small>
          </article>
          <article>
            <span>{t("Not valued")}</span>
            <strong className="num">{number(overview.total_resale - overview.valued_count)}</strong>
            <small>{t("Too little evidence, or not a residential unit. We do not guess.")}</small>
          </article>
        </div>
      </section>

      <section className="page section" aria-labelledby="cash-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">03{sep()}{t("Cash equivalent")}</span>
            <h2 id="cash-heading" className="display">
              {t("A headline price")} <em>{t("is not a cash price.")}</em>
            </h2>
          </div>
          <p className="lede">
            {t(
              "What was paid at signing counts in full. The balance is spread over the remaining term in quarterly installments and discounted at {rate} a year, roughly what the same money earns in Egyptian deposits.",
              { rate: percent(overview.discount_rate) },
            )}
          </p>
        </div>
        <div className="formula-card">
          <code dir="ltr">cash today = paid at signing + Σ installment ÷ (1 + {overview.discount_rate})^years</code>
          <p>
            {t(
              "For the median installment listing the cash value is {cut} below the headline. When terms are not fully published the unit is valued but its price is not positioned: classified listings often show only what is due now.",
              { cut: percent(overview.plan_median_discount) },
            )}
          </p>
        </div>
        {overview.launch.compared > 0 && (
          <div className="formula-card launch-method">
            <h3>{t("Resale vs buying new")}</h3>
            <p>
              {t(
                "{n} current developer launch units in {c} compounds are compared with the model’s resale value for the same unit on the same plan. The median launch unit costs {spread} against resale, in today’s money.",
                { n: number(overview.launch.compared), c: number(overview.launch.compounds), spread: signed(overview.launch.median_spread) },
              )}
            </p>
            <p>
              {t(
                "Launch plans are long and back-loaded, so the comparison depends on how the model prices such plans. {n} resale units carry launch-like plans (85% or more still owed, seven or more years); the model values them with a median bias of {bias}.",
                { n: number(overview.launch.support.units), bias: signed(overview.launch.support.median_residual, 1) },
              )}
            </p>
          </div>
        )}
        <ul className="terms-mix">
          {(["plan", "cash", "partial", "unknown"] as const).map((terms) => (
            <li key={terms}>
              <b className="num">{number(overview.payment_terms[terms] ?? 0)}</b>
              <span>
                {t(
                  terms === "plan"
                    ? "Installment plans with known terms"
                    : terms === "cash"
                      ? "Cash"
                      : terms === "partial"
                        ? "Installments, term not published"
                        : "Payment terms not published",
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="page section" id="coverage" aria-labelledby="coverage-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">04{sep()}{t("Coverage")}</span>
            <h2 id="coverage-heading" className="display">
              {t("Where the evidence")} <em>{t("comes from.")}</em>
            </h2>
          </div>
          <ScopeNote scope={overview.scope} />
        </div>
        <div className="coverage-scroll">
          <table className="coverage">
            <caption className="sr-only">{t("Indexed records, resale listings and valued listings by source")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("Source")}</th>
                <th scope="col">{t("Indexed records")}</th>
                <th scope="col">{t("Identified resale")}</th>
                <th scope="col">{t("Positioned against fair value")}</th>
                <th scope="col">{t("Last observed")}</th>
                <th scope="col">{t("Collection status")}</th>
              </tr>
            </thead>
            <tbody>
              {overview.sources.map((source) => (
                <tr key={source.id}>
                  <th scope="row">
                    <span className="source-initial" aria-hidden="true">
                      {source.name.slice(0, 1)}
                    </span>
                    {source.name}
                  </th>
                  <td className="num">{number(source.count)}</td>
                  <td className="num">{number(source.resale_count)}</td>
                  <td>
                    <span className="coverage-bar">
                      <b className="num">{number(source.valued_count)}</b>
                      <span aria-hidden="true">
                        <i style={{ width: `${source.resale_count ? (source.valued_count / source.resale_count) * 100 : 0}%` }} />
                      </span>
                    </span>
                  </td>
                  <td className="num">{date(source.last_seen_at)}</td>
                  <td>
                    <span className={`status status-${source.status}`}>
                      <i />
                      {t(source.status === "completed" ? "Complete run" : source.status === "partial" ? "Partial run" : "Not recorded")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="fineprint">
          {t(
            "Included: active sale listings in EGP between EGP 100,000 and 200 million, 20–5,000 m², with a property type and a district or compound. Only identified resale listings are valued by default. A complete run covers its defined scope, not the whole market.",
          )}
        </p>
      </section>

      <section className="page section" aria-labelledby="limits-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">05{sep()}{t("Limits")}</span>
            <h2 id="limits-heading" className="display">
              {t("What a fair value")} <em>{t("cannot tell you.")}</em>
            </h2>
          </div>
        </div>
        <div className="definitions">
          {limits.map(({ icon: Icon, title, text }) => (
            <article key={title}>
              <Icon size={22} strokeWidth={1.6} />
              <h3>{t(title)}</h3>
              <p>{t(text)}</p>
            </article>
          ))}
        </div>
        {!overview.history_ready && (
          <p className="notice notice-soft">
            <CalendarClock size={17} />
            <span>
              {t(
                overview.observation_days === 1
                  ? "Qayem has observed this market for {n} day."
                  : "Qayem has observed this market for {n} days.",
                { n: number(overview.observation_days) },
              )}
            </span>
          </p>
        )}
      </section>
    </div>
  );
}

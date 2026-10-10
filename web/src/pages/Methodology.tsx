import { ArrowDown, Banknote, Building2, CalendarClock, FileQuestion, Files, Gavel, History, Landmark, Layers3, ScanLine, Truck } from "lucide-react";
import { date, number, percent, signed, sep } from "../lib";
import type { ReactNode } from "react";
import { t } from "../locale";
import type { Level, Overview } from "../types";
import { ErrorState, Loading } from "../components/States";
import { LevelBadge, ScopeNote } from "../components/Opportunity";

const limits = [
  {
    icon: ScanLine,
    title: "Contract prices, not sale prices",
    text: "AqarExit units are listed at the owner’s original contract price, and Egypt publishes no resale sale prices. So Qayem does not say what a unit is worth; it compares it with what can be bought instead.",
  },
  {
    icon: Layers3,
    title: "Developer prices are list prices",
    text: "Developer prices come from the developers’ own current listings on Nawy. Negotiated discounts and private offers are not visible.",
  },
  {
    icon: Truck,
    title: "Delivery is shown, not priced",
    text: "A resale unit that delivers years before the developer’s new units is worth more for it. Both delivery dates are shown; the difference is not priced into the gap.",
  },
  {
    icon: Building2,
    title: "Floor, view and orientation",
    text: "Sources rarely publish them. A sea-view or garden unit can rightly cost more than similar units in its compound.",
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
    text: "The same unit can be listed twice. Counts are listings.",
  },
  {
    icon: History,
    title: "History is still short",
    text: "Price trends, time on market and delivery postponements need repeated observation. They appear once there are eight weeks of history.",
  },
  {
    icon: FileQuestion,
    title: "Resale, with its evidence",
    text: "Every AqarExit unit is a contract transfer (تنازل), and AqarExit says whether it verified the contract and receipts. It is shown on every unit.",
  },
];

const levels: Level[] = ["strong", "good", "in_line", "mixed", "pricier", "check", "unrated"];

export default function Methodology({ overview, error, retry }: { overview: Overview | null; error: string; retry: () => void }) {
  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} />
      </div>
    );
  if (!overview) return <Loading />;
  const rules = overview.thresholds;
  const pct = (value: number) => percent(Math.abs(value));
  const levelRule: Record<Level, string> = {
    strong: t("At least {all} under every comparison that applies, and {one} under one of them.", { all: pct(rules.strong_all), one: pct(rules.strong_one) }),
    good: t("At least {all} under every comparison that applies, and {one} under one of them.", { all: pct(rules.good_all), one: pct(rules.good_one) }),
    in_line: t("Within the ranges above and below."),
    mixed: t("At least {one} under one comparison and {up} over the other.", { one: pct(rules.good_one), up: pct(rules.pricier) }),
    pricier: t("At least {up} over a comparison, as listed and in today’s money.", { up: pct(rules.pricier) }),
    check: t(
      "More than {dev} under the developer, {peers} under similar units, or {cheapest} under even the cheapest similar unit: verify it first. It may be a listing error or an unusually early contract.",
      { dev: pct(rules.check_developer), peers: pct(rules.check_peers), cheapest: pct(rules.check_cheapest) },
    ),
    unrated: t("No like-for-like developer price and fewer than {n} other similar units.", { n: number(overview.peers.min_similar) }),
  };
  const good = (overview.opportunities.strong ?? 0) + (overview.opportunities.good ?? 0);
  return (
    <div className="method page-enter">
      <header className="method-hero">
        <div className="page method-hero-inner">
          <div>
            <span className="eyebrow">{t("Methodology")}</span>
            <h1 className="display">
              {t("How an opportunity")} <em>{t("is judged.")}</em>
            </h1>
            <p className="lede">
              {t(
                "Qayem does not estimate a fair price. Egypt publishes no resale sale prices, and AqarExit lists each unit at its old contract price. Instead, every unit is compared with what could be bought instead today.",
              )}
            </p>
            <a className="btn btn-brass" href="#levels">
              {t("See the rules")} <ArrowDown size={16} />
            </a>
          </div>
          <dl className="method-snapshot">
            <div>
              <dt>{t("Resale units")}</dt>
              <dd className="num">{number(overview.total_resale)}</dd>
            </div>
            <div>
              <dt>{t("Compared")}</dt>
              <dd className="num">{number(overview.rated_count)}</dd>
            </div>
            <div>
              <dt>{t("Strong or good opportunities")}</dt>
              <dd className="num">{number(good)}</dd>
            </div>
            <div>
              <dt>{t("Observation window")}</dt>
              <dd className="num method-dates">
                {date(overview.first_observed)} – {date(overview.last_updated)}
              </dd>
            </div>
          </dl>
        </div>
      </header>

      <section className="page section" aria-labelledby="comparisons-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">01{sep()}{t("Two comparisons")}</span>
            <h2 id="comparisons-heading" className="display">
              {t("Against what you")} <em>{t("could buy instead.")}</em>
            </h2>
          </div>
          <p className="lede">
            {t(
              "Each comparison is made twice: on the listed price, and in today’s money. A gap counts only on the less favourable of the two, so neither a long remaining plan nor the discount rate can make a deal on its own.",
            )}
          </p>
        </div>
        <div className="definitions">
          <article>
            <Landmark size={22} strokeWidth={1.6} />
            <h3>{t("The developer today")}</h3>
            <p>
              {t(
                "The developer’s current units on Nawy in the same compound, of the same type and finishing, within 1.5× the size: the median of the nearest five, and at least two. {n} developer units in {c} compounds are matched; {u} resale units have a like-for-like developer price.",
                { n: number(overview.launch.matched), c: number(overview.launch.compounds), u: number(overview.launch.compared) },
              )}
            </p>
          </article>
          <article>
            <Building2 size={22} strokeWidth={1.6} />
            <h3>{t("Similar units now")}</h3>
            <p>
              {t(
                "The other resale units listed in the same compound, of the same type, within 1.5× the size, and of the same finishing when there are at least {n}. The unit is ranked against their median; {r} units have enough of them.",
                { n: number(overview.peers.min_similar), r: number(overview.peers.ranked) },
              )}
            </p>
          </article>
        </div>
        <div className="formula-card">
          <Formula
            label={t("How a gap is calculated")}
            term={t("Gap")}
            parts={[
              <span key="f">{t("the larger of")}</span>,
              <Group key="g">
                <span className="f-term">
                  <Frac top={t("Listed price per m²")} bottom={t("Comparison, listed")} />
                  <span className="f-op">−</span>
                  <span className="num">{number(1)}</span>
                </span>
                <span className="f-sep">{t("and")}</span>
                <span className="f-term">
                  <Frac top={t("Today’s-money price per m²")} bottom={t("Comparison, in today’s money")} />
                  <span className="f-op">−</span>
                  <span className="num">{number(1)}</span>
                </span>
              </Group>,
            ]}
          />
          <p>
            {t(
              "The median like-for-like resale unit sits {gap} against the developer’s price today. Since the sellers signed, developer list prices per m² have moved {annual} a year (median of {n} units).",
              {
                gap: signed(overview.launch.median_gap),
                annual: signed(overview.since_contract.median_annual, 1),
                n: number(overview.since_contract.units),
              },
            )}
          </p>
        </div>
      </section>

      <section className="page section" id="levels" aria-labelledby="levels-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">02{sep()}{t("Levels")}</span>
            <h2 id="levels-heading" className="display">
              {t("Every comparison")} <em>{t("has to agree.")}</em>
            </h2>
          </div>
          <p className="lede">
            {t(
              "The developer comparison counts only when the finishing matches: an unfinished unit is not a deal for being unfinished. Units are ranked by level, then those checked against both comparisons first, then by their average gap.",
            )}
          </p>
        </div>
        <div className="ledger-frame">
          <div className="ledger stack">
            <table>
              <caption className="sr-only">{t("Opportunity levels and their rules")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("Level")}</th>
                  <th scope="col">{t("Rule")}</th>
                  <th scope="col">{t("Units")}</th>
                </tr>
              </thead>
              <tbody>
                {levels.map((level) => (
                  <tr key={level}>
                    <th scope="row">
                      <LevelBadge level={level} />
                    </th>
                    <td data-label={t("Rule")}>{levelRule[level]}</td>
                    <td data-label={t("Units")} className="num ledger-strong">
                      {number(overview.opportunities[level] ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
          <Formula
            label={t("How today’s money is calculated")}
            term={t("Price in today’s money")}
            parts={[
              <span key="s">{t("Paid at signing")}</span>,
              <span key="sum" className="f-term">
                <span className="f-op">+</span>
                <span className="f-sum">Σ</span>
                <Frac
                  top={t("Each remaining installment")}
                  bottom={
                    <>
                      (<span className="num">{number(1)}</span> + <span className="num">{percent(overview.discount_rate)}</span>)
                      <sup>{t("t")}</sup>
                    </>
                  }
                />
              </span>,
            ]}
            note={t("t: years until that installment is due.")}
          />
          <p>
            {t(
              "For the median installment listing the cash value is {cut} below the headline. The developer’s plans are discounted the same way. Units whose terms are not fully published are not compared.",
              { cut: percent(overview.plan_median_discount) },
            )}
          </p>
        </div>
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
            <caption className="sr-only">{t("Indexed records, resale listings and compared listings by source")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("Source")}</th>
                <th scope="col">{t("Indexed records")}</th>
                <th scope="col">{t("Identified resale")}</th>
                <th scope="col">{t("Compared")}</th>
                <th scope="col">{t("Last observed")}</th>
                <th scope="col">{t("Collection status")}</th>
              </tr>
            </thead>
            <tbody>
              {overview.sources.map((source) => (
                <tr key={source.id}>
                  <th scope="row">
                    <span className="coverage-source">
                      <span className="source-initial" aria-hidden="true">
                        {t(source.name).slice(0, 1)}
                      </span>
                      {t(source.name)}
                    </span>
                  </th>
                  <td className="num" data-label={t("Indexed records")}>{number(source.count)}</td>
                  <td className="num" data-label={t("Identified resale")}>{number(source.resale_count)}</td>
                  <td data-label={t("Compared")}>
                    <span className="coverage-bar">
                      <b className="num">{number(source.rated_count)}</b>
                      <span aria-hidden="true">
                        <i style={{ width: `${source.resale_count ? (source.rated_count / source.resale_count) * 100 : 0}%` }} />
                      </span>
                    </span>
                  </td>
                  <td className="num" data-label={t("Last observed")}>{date(source.last_seen_at)}</td>
                  <td data-label={t("Collection status")}>
                    <span className={`status status-${source.status}`}>
                      <i />
                      {t(source.status === "completed" ? "Complete run" : source.status === "partial" ? "Partial run" : "Not recorded")}
                    </span>
                  </td>
                </tr>
              ))}
              {overview.benchmarks.map((source) => (
                <tr key={source.id}>
                  <th scope="row">
                    <span className="coverage-source">
                      <span className="source-initial" aria-hidden="true">
                        {t(source.name).slice(0, 1)}
                      </span>
                      {t(source.name)}
                    </span>
                  </th>
                  <td className="num" data-label={t("Indexed records")}>{number(source.count)}</td>
                  <td colSpan={2} data-label={t("Role")} className="muted">
                    {t("Price benchmark: the developers’ current prices, never counted as resale")}
                  </td>
                  <td className="num" data-label={t("Last observed")}>{date(source.last_seen_at)}</td>
                  <td data-label={t("Collection status")}>
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
            "Included: active sale listings in EGP between EGP 100,000 and 200 million, 20–5,000 m², with a property type and a district or compound. A complete run covers its defined scope, not the whole market.",
          )}
        </p>
      </section>

      <section className="page section" aria-labelledby="limits-heading">
        <div className="section-head">
          <div>
            <span className="eyebrow">05{sep()}{t("Limits")}</span>
            <h2 id="limits-heading" className="display">
              {t("What a comparison")} <em>{t("cannot tell you.")}</em>
            </h2>
          </div>
        </div>
        <div className="definitions">
          {limits
            .filter(({ title }) => overview.launch.units > 0 || title !== "Developer prices are list prices")
            .map(({ icon: Icon, title, text }) => (
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
                { n: number(overview.observation_days), count: overview.observation_days },
              )}
            </span>
          </p>
        )}
      </section>
    </div>
  );
}

/** A formula typeset in the interface language: stacked fractions, real exponents, the page's direction. */
function Formula({ label, term, parts, note }: { label: string; term: string; parts: ReactNode[]; note?: string }) {
  return (
    <figure className="formula" aria-label={label}>
      <div className="formula-line">
        <span className="f-lhs">
          <b>{term}</b>
          <span className="f-op">=</span>
        </span>
        {parts}
      </div>
      {note && <figcaption>{note}</figcaption>}
    </figure>
  );
}

function Frac({ top, bottom }: { top: ReactNode; bottom: ReactNode }) {
  return (
    <span className="f-frac">
      <span>{top}</span>
      <span>{bottom}</span>
    </span>
  );
}

function Group({ children }: { children: ReactNode }) {
  return (
    <span className="f-group">
      <span className="f-paren" aria-hidden="true">(</span>
      {children}
      <span className="f-paren" aria-hidden="true">)</span>
    </span>
  );
}

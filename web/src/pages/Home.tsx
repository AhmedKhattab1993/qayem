import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Banknote, Building2, Landmark, Link2, PlayCircle, Scale, Users, type LucideIcon } from "lucide-react";
import type { Overview, Page, Unit } from "../types";
import { date, number, percent, sep, signed, useApi, useCatalog, nameOf } from "../lib";
import { t } from "../locale";
import { ErrorState, Loading } from "../components/States";
import { DivergingBars, ScopeNote } from "../components/Opportunity";
import { UnitTable } from "../components/UnitTable";
import { Explainer, explainerLength, type ExplainerHandle } from "../components/Explainer";

const GROUP_SIZE = 5;

/** One ranking of the best opportunities, by a single comparison. */
function BestGroup({ id, icon: Icon, title, note, items, caption, to, more }: {
  id: string;
  icon: LucideIcon;
  title: string;
  note: string;
  items: Unit[];
  caption: string;
  to: string;
  more: string;
}) {
  if (!items.length) return null;
  return (
    <div className="best-group" role="group" aria-labelledby={id}>
      <div className="best-group-head">
        <h3 id={id}>
          <Icon size={20} /> {t(title)}
        </h3>
        <p>{t(note)}</p>
      </div>
      <UnitTable items={items} caption={caption} />
      <div className="section-foot best-group-foot">
        <Link className="link-arrow" to={to}>
          {t(more)} <ArrowUpRight size={16} className="flip-rtl" />
        </Link>
      </div>
    </div>
  );
}

export default function Home({ data, error, retry }: { data: Overview | null; error: string; retry: () => void }) {
  const navigate = useNavigate();
  const explainer = useRef<ExplainerHandle>(null);
  const catalog = useCatalog();
  // Two rankings, never one: "below the developer" and "below similar resale units" answer different questions.
  const belowDeveloper = useApi<Page<Unit>>(`/units?sort=launch_gap&page_size=${GROUP_SIZE}`);
  const belowPeers = useApi<Page<Unit>>(`/units?sort=peer_gap&page_size=${GROUP_SIZE}`);
  const [compound, setCompound] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = compound.trim();
    const match = catalog?.compounds.find((c) =>
      [c.name, c.name_ar].some((name) => name?.toLocaleLowerCase() === value.toLocaleLowerCase()),
    );
    navigate(match ? `/evaluate?compound=${encodeURIComponent(match.name)}` : value ? `/compounds?q=${encodeURIComponent(value)}` : "/evaluate");
  };
  const gaps = data?.developer_gaps ?? [];
  const spread = [...gaps.slice(0, 5), ...gaps.slice(-5)].filter(
    (item, index, all) => all.findIndex((other) => other.key === item.key) === index,
  );
  const good = data ? (data.opportunities.strong ?? 0) + (data.opportunities.good ?? 0) : 0;

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-grid" aria-hidden="true" />
        <div className="page hero-inner">
          <div className="hero-copy page-enter">
            <span className="hero-live">
              <span className="live-dot" />
              {t("Resale opportunity index")}
              {sep()}
              {data ? t("observed {date}", { date: date(data.last_updated) }) : t("loading…")}
            </span>
            <h1 className="display">
              {t("Is it really")}
              <br />
              <em>{t("a good deal?")}</em>
            </h1>
            <p className="hero-lede">
              {t(
                "Qayem compares every resale unit with what you could buy instead today: the developer’s own current price and the similar units listed in the same compound, both in today’s money.",
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
                {catalog?.compounds.map((c) => <option key={c.key} value={nameOf(c)} />)}
              </datalist>
              <button type="submit" className="btn btn-brass">
                {t("Compare a unit")} <ArrowRight size={16} className="flip-rtl" />
              </button>
            </form>
            <div className="hero-alts">
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
                <dt>{t("Resale units compared")}</dt>
                <dd className="num">{number(data.rated_count)}</dd>
                <dd className="hero-stat-note num">{t("of {n} listed", { n: number(data.total_resale) })}</dd>
              </div>
              <div>
                <dt>{t("Strong or good opportunities")}</dt>
                <dd className="num">
                  <Link to="/units">{number(good)}</Link>
                </dd>
                <dd className="hero-stat-note">
                  <Link to="/units">
                    {t("See them, best first")} <ArrowRight size={13} className="flip-rtl" />
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
          {((belowDeveloper.data?.items.length ?? 0) > 0 || (belowPeers.data?.items.length ?? 0) > 0) && (
            <section className="page section" aria-labelledby="best-heading">
              <div className="section-head">
                <div>
                  <span className="eyebrow">{t("Best opportunities now")}</span>
                  <h2 id="best-heading" className="display">
                    {t("Cheaper than")} <em>{t("what you could buy instead.")}</em>
                  </h2>
                </div>
                <p className="lede">
                  {t(
                    "Two different comparisons, ranked separately. A unit cheaper than both the developer and similar resale units is marked “Cheaper on both”.",
                  )}
                </p>
              </div>
              <BestGroup
                id="best-developer"
                icon={Landmark}
                title="Cheaper than the developer today"
                note="Below what the developer asks today for a unit of the same type, finishing and similar size in the same compound. Mostly older contracts: developer prices have risen since the seller signed."
                items={belowDeveloper.data?.items ?? []}
                caption="Resale units furthest below the developer’s price today"
                to="/units?sort=launch_gap"
                more="All units, furthest below the developer"
              />
              <BestGroup
                id="best-peers"
                icon={Users}
                title="Cheaper than other resale units"
                note="Below the typical price of at least four similar resale units listed in the same compound, as listed and in today’s money."
                items={belowPeers.data?.items ?? []}
                caption="Resale units furthest below similar units in their compound"
                to="/units?sort=peer_gap"
                more="All units, furthest below similar units"
              />
            </section>
          )}

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
                    "{days} days of observation. Comparisons use listed contract prices and developer list prices: there is no fair price, and trends wait for eight weeks of history.",
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

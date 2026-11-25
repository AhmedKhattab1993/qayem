import { ArrowUpRight } from "lucide-react";
import { date, number, safeExternalUrl } from "../lib";
import { t } from "../locale";
import type { MarketSignal, Overview } from "../types";

/** The economy around the prices: the dollar, gold, inflation, money from abroad, mortgages and rents. */
const SHOWN: { name: string; label: string; digits?: number; suffix?: string }[] = [
  { name: "usdt_egp_p2p", label: "Dollar on the P2P market (EGP)", digits: 2 },
  { name: "gold_21k", label: "Gold, 21 karat (EGP a gram)" },
  { name: "capmas_inflation_annual", label: "Inflation, year on year (CAPMAS)", digits: 1, suffix: "%" },
  { name: "cbe_bop_workers_remittances", label: "Remittances in the quarter (US$ million)" },
  { name: "cbe_bop_fdi_in_egypt_net", label: "Foreign direct investment in the quarter (US$ million)" },
  { name: "fra_mortgage_finance_month", label: "Mortgage finance granted in the month (EGP million)" },
];
const EVENT_KINDS = new Set(["news", "land_offer", "housing_offer", "mortgage_terms", "nuca_notice", "fra_statistics", "rent_index"]);

function Figure({ signal, label, digits, suffix }: { signal: MarketSignal; label: string; digits?: number; suffix?: string }) {
  return (
    <li>
      <span className="field-label">{t(label)}</span>
      <b className="num">
        {number(signal.value, digits ?? 0)}
        {suffix ?? ""}
      </b>
      <small className="num">
        {signal.period} · {signal.source}
      </small>
    </li>
  );
}

export function MarketSignals({ overview }: { overview: Overview | null }) {
  const signals = overview?.signals;
  if (!signals) return null;
  const figures = SHOWN.flatMap((item) => (signals.latest[item.name] ? [{ ...item, signal: signals.latest[item.name] }] : []));
  const official = overview?.rates?.egp_per?.usd;
  const p2p = signals.latest.usdt_egp_p2p?.value;
  // City-wide rent indices: «rent_rent_per_m2_month:<city>:<city>».
  const rents = Object.entries(signals.latest).flatMap(([name, signal]) => {
    const [kind, city, place] = name.split(":");
    if (kind !== "rent_rent_per_m2_month" || city !== place) return [];
    const town = t(city.charAt(0).toUpperCase() + city.slice(1));
    return [{ signal, label: t("Rent per m² a month in {city} (EGP)", { city: town }) }];
  });
  const events = signals.events.filter((e) => EVENT_KINDS.has(e.kind)).slice(0, 6);
  if (!figures.length && !events.length) return null;
  return (
    <section className="section-tight" aria-labelledby="index-signals">
      <span className="eyebrow">{t("Around the prices")}</span>
      <h2 id="index-signals" className="display section-title">
        {t("The economy this month")}
      </h2>
      {figures.length > 0 && (
        <ul className="signal-figures">
          {figures.map((item) => (
            <Figure key={item.name} signal={item.signal} label={item.label} digits={item.digits} suffix={item.suffix} />
          ))}
          {rents.map((rent) => (
            <Figure key={rent.label} signal={rent.signal} label={rent.label} />
          ))}
        </ul>
      )}
      {official && p2p && (
        <p className="fineprint num">
          {t("The Central Bank's rate is {official} EGP a dollar; on the P2P market a dollar costs {p2p}.", {
            official: number(official, 2),
            p2p: number(p2p, 2),
          })}
        </p>
      )}
      {events.length > 0 && (
        <ul className="index-changes signal-events">
          {events.map((event) => {
            const href = safeExternalUrl(event.url);
            return (
              <li key={event.key}>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    <b dir="auto">{event.title}</b>
                  </a>
                ) : (
                  <b dir="auto">{event.title}</b>
                )}
                <small>{date(event.day)}</small>
                <small dir="auto">
                  {event.source}
                  {event.summary ? ` · ${event.summary}` : ""}
                  {href && <ArrowUpRight size={12} aria-hidden="true" />}
                </small>
              </li>
            );
          })}
        </ul>
      )}
      <p className="fineprint">
        {t("Figures from CAPMAS, the Central Bank of Egypt, the FRA, Marsad Omran, iSagha and Binance P2P, each with its period. Qayem reads them nightly and keeps only numbers it finds written in the source.")}
      </p>
    </section>
  );
}

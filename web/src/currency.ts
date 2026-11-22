/** The display currency: prices are stored in EGP and converted at the Central Bank of Egypt's rate of the day. */
import { createContext, useContext } from "react";
import type { Rates } from "./types";

export type Currency = "EGP" | "USD" | "SAR" | "AED";
export const CURRENCIES: Currency[] = ["EGP", "USD", "SAR", "AED"];

const KEY = "qayem:currency";
let chosen: Currency = (() => {
  try {
    const saved = localStorage.getItem(KEY) as Currency | null;
    return saved && CURRENCIES.includes(saved) ? saved : "EGP";
  } catch {
    return "EGP";
  }
})();
let rates: Rates | null = null;

/** The rates from /api/overview; without them every price stays in EGP. */
export function setRates(next: Rates | null | undefined) {
  rates = next ?? null;
}
export const getRates = () => rates;

/** EGP per one unit of the currency, or null when it cannot be converted. */
export const rateOf = (currency: Currency) =>
  currency === "EGP" ? 1 : (rates?.egp_per?.[currency.toLowerCase()] ?? null);

/** The currency prices are shown in now: the reader's choice when a rate exists for it, else EGP. */
export const getCurrency = (): Currency => (chosen !== "EGP" && rateOf(chosen) ? chosen : "EGP");
/** The reader's saved choice, even before the rates have loaded. */
export const chosenCurrency = () => chosen;

export function setCurrency(next: Currency) {
  if (next === chosen) return;
  chosen = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // The choice still applies for this visit.
  }
}

/** An EGP amount in the display currency. */
export const convert = (egp: number) => {
  const rate = rateOf(getCurrency());
  return rate ? egp / rate : egp;
};

/** The switch's state, for controls outside the header (the map's toolbar). */
export const CurrencyContext = createContext<{ currency: Currency; currencies: Currency[]; change: (next: Currency) => void }>({
  currency: "EGP",
  currencies: [],
  change: () => {},
});
export const useCurrency = () => useContext(CurrencyContext);

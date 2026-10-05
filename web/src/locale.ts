import { createElement, Fragment, type ReactNode } from "react";
import { ar } from "./ar";

export type Language = "ar" | "en";
type Vars = Record<string, string | number | null | undefined>;

let language: Language = (() => {
  try {
    return localStorage.getItem("qayem:language") === "en" ? "en" : "ar";
  } catch {
    return "ar";
  }
})();

export const getLanguage = () => language;
export const isArabic = () => language === "ar";

const interpolate = (text: string, vars?: Vars) =>
  vars ? text.replace(/\{(\w+)\}/g, (match, key) => (vars[key] != null ? String(vars[key]) : match)) : text;

const arLower = Object.fromEntries(Object.entries(ar).map(([key, value]) => [key.toLowerCase(), value]));

/** English singulars for counted copy (see `count` below). */
const enOne: Record<string, string> = {
  "{n} listings": "{n} listing",
  "{n} listings · {change}": "{n} listing · {change}",
  "{n} units": "{n} unit",
  "{n} compounds": "{n} compound",
  "{n} developers": "{n} developer",
  "All {n} compounds": "{n} compound",
  "All {n} photos": "{n} photo",
  "{n} districts": "{n} district",
  "{n} sources": "{n} source",
  "{n} years": "{n} year",
  "Left, over {n} years": "Left, over {n} year",
  "{n} further compounds have too few listings for a premium.": "{n} further compound has too few listings for a premium.",
  "{n} further compounds have no like-for-like developer price.": "{n} further compound has no like-for-like developer price.",
  "{n} units compared": "{n} unit compared",
  "{n} opportunities": "{n} opportunity",
  "{n} strong or good opportunities": "{n} strong or good opportunity",
};
const arPlural = new Intl.PluralRules("ar");

/** Translate an English source string. Unknown strings fall back to English.
 * Pass a numeric `count` for counted copy: English uses its singular for 1, Arabic picks
 * "<key>|one", "<key>|two" or "<key>|few" (3–10) from ar.ts when present. */
export function t(text: string, vars?: Vars) {
  const count = typeof vars?.count === "number" ? vars.count : undefined;
  if (language === "en") return interpolate(count === 1 ? (enOne[text] ?? text) : text, vars);
  const plural = count == null ? undefined : ar[`${text}|${arPlural.select(count)}`];
  return interpolate(plural ?? ar[text] ?? arLower[text.toLowerCase()] ?? text, vars);
}

/** Like t(), but placeholders may be elements, e.g. a <bdi> around a source name. */
export function tx(text: string, vars: Record<string, ReactNode>) {
  const template = language === "en" ? text : (ar[text] ?? arLower[text.toLowerCase()] ?? text);
  const parts = template.split(/(\{\w+\})/).map((part) => {
    const key = /^\{(\w+)\}$/.exec(part)?.[1];
    return key && key in vars ? vars[key] : part;
  });
  return createElement(Fragment, null, ...parts);
}

export function setLanguage(next: Language) {
  language = next;
  document.documentElement.lang = next;
  document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
  document
    .querySelector('meta[name="description"]')
    ?.setAttribute(
      "content",
      t("Qayem weighs Egypt's resale property market: every listing scored, sourced, and priced against its peers."),
    );
  try {
    localStorage.setItem("qayem:language", next);
  } catch {
    // The choice still applies for this visit.
  }
}

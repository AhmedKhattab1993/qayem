import { ar } from "./ar";

export type Language = "ar" | "en";
type Vars = Record<string, string | number>;

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
  vars ? text.replace(/\{(\w+)\}/g, (match, key) => (key in vars ? String(vars[key]) : match)) : text;

const arLower = Object.fromEntries(Object.entries(ar).map(([key, value]) => [key.toLowerCase(), value]));

/** Translate an English source string. Unknown strings fall back to English. */
export function t(text: string, vars?: Vars) {
  if (language === "en") return interpolate(text, vars);
  return interpolate(ar[text] ?? arLower[text.toLowerCase()] ?? text, vars);
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

import { money, nameOf, number, place, sep, titleCase, year } from "./lib";
import { t } from "./locale";
import { levelText } from "./components/Opportunity";
import type { Catalog, Level } from "./types";

/** The Units filters a saved search keeps: what is searched for, not how the list is sorted or paged. */
export const SEARCH_KEYS = [
  "q",
  "compound",
  "price_max",
  "cash_max",
  "signing_max",
  "bedrooms_min",
  "area_min",
  "area_max",
  "delivery",
  "district",
  "developer",
  "property_type",
  "level",
  "terms",
  "launch",
];

/** One spelling per search, so the same filters in another order are the same saved search. */
export function searchQuery(params: URLSearchParams) {
  const next = new URLSearchParams();
  for (const key of SEARCH_KEYS) {
    const value = params.get(key);
    if (value) next.set(key, value);
  }
  return next.toString();
}

const termsText: Record<string, string> = {
  cash: "Cash",
  plan: "Installment plan",
  partial: "Plan, term unknown",
  unknown: "Terms unknown",
};

/** A saved search in words, in the interface language. */
export function describeSearch(query: string, catalog: Catalog | null) {
  const params = new URLSearchParams(query);
  const get = (key: string) => params.get(key);
  const amount = (key: string, label: string) => get(key) && t(label, { amount: money(Number(get(key)), true) });
  const compound = catalog?.compounds.find((c) => c.key === get("compound"));
  const developer = catalog?.developers.find((d) => d.key === get("developer"));
  const district = catalog?.districts.find((d) => d.key === get("district"));
  const [min, max] = [get("area_min"), get("area_max")];
  const parts = [
    get("q") && `“${get("q")}”`,
    get("property_type") && titleCase(get("property_type")),
    compound ? nameOf(compound) : get("compound"),
    district ? place(district.name) : get("district"),
    developer ? nameOf(developer) : get("developer"),
    get("bedrooms_min") && t("{n}+ bedrooms", { n: number(Number(get("bedrooms_min"))) }),
    min && max
      ? t("{min}–{max} m²", { min: number(Number(min)), max: number(Number(max)) })
      : min
        ? t("{n} m² or more", { n: number(Number(min)) })
        : max && t("Under {n} m²", { n: number(Number(max)) }),
    amount("price_max", "Asking up to {amount}"),
    amount("cash_max", "Cash today up to {amount}"),
    amount("signing_max", "Up to {amount} at signing"),
    get("delivery") &&
      (get("delivery") === "ready" ? t("Ready now") : t("By {year}", { year: year(get("delivery")) })),
    get("level") && t(levelText[get("level") as Level] ?? get("level")!),
    get("terms") && t(termsText[get("terms")!] ?? get("terms")!),
    get("launch") && t("Developer selling similar units"),
  ];
  return parts.filter(Boolean).join(sep()) || t("All units");
}

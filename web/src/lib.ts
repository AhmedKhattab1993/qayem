import { useEffect, useState } from "react";
import { getLanguage, t } from "./locale";
import type { Catalog } from "./types";

const locale = () => (getLanguage() === "ar" ? "ar-EG" : "en-GB");

export const number = (value: number | null | undefined, digits = 0) =>
  value == null ? "—" : new Intl.NumberFormat(locale(), { maximumFractionDigits: digits }).format(value);

export const compact = (value: number | null | undefined) =>
  value == null
    ? "—"
    : new Intl.NumberFormat(locale(), { notation: "compact", maximumFractionDigits: 1 }).format(value);

export const money = (value: number | null | undefined, short = false) =>
  value == null
    ? "—"
    : getLanguage() === "ar"
      ? `${short ? compact(value) : number(value)} ${t("EGP")}`
      : `${t("EGP")} ${short ? compact(value) : number(value)}`;

export const percent = (value: number | null | undefined, digits = 0) =>
  value == null ? "—" : `${number(value * 100, digits)}${getLanguage() === "ar" ? "٪" : "%"}`;

/** A signed share: +12% / −8%. */
export const signed = (value: number | null | undefined, digits = 0) => {
  if (value == null) return "—";
  const rounded = Number((value * 100).toFixed(digits));
  if (rounded === 0) return percent(0);
  return `${rounded > 0 ? "+" : "−"}${percent(Math.abs(value), digits)}`;
};

/** List separator. A middle dot reads as the Arabic zero (٠), so Arabic uses a comma. */
export const sep = () => (getLanguage() === "ar" ? "، " : " · ");

export const titleCase = (value: string | null | undefined) => {
  if (!value || value === "-") return t("Not provided");
  const label = value.replace(/[_-]/g, " ").replace(/\s+/g, " ").trim().replace(/\b\w/g, (c) => c.toUpperCase());
  return t(label);
};

const parse = (value: string) => new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);

export const date = (value: string | null | undefined, style: "day" | "month" = "day") => {
  if (!value) return t("Not available");
  const parsed = parse(value.length === 10 ? `${value}T00:00:00Z` : value);
  return Number.isNaN(parsed.getTime())
    ? t("Not available")
    : parsed.toLocaleDateString(locale(), {
        ...(style === "day" ? { day: "numeric" } : {}),
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      });
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, { signal });
  if (!response.ok) {
    let message = response.status === 404 ? "This page is not available." : "We could not load the data. Please try again.";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* retain helpful fallback */
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

/** Fetch on mount and whenever `path` changes; `null` path skips. */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{ data: T | null; error: string; path: string | null }>({
    data: null,
    error: "",
    path: null,
  });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState((current) => ({ data: current.path === path ? current.data : null, error: "", path }));
    api<T>(path, controller.signal)
      .then((data) => setState({ data, error: "", path }))
      .catch((cause) => cause.name !== "AbortError" && setState({ data: null, error: cause.message, path }));
    return () => controller.abort();
  }, [path, attempt]);
  return {
    data: state.path === path ? state.data : null,
    error: state.path === path ? state.error : "",
    retry: () => setAttempt((n) => n + 1),
  };
}

let catalogPromise: Promise<Catalog> | null = null;
/** Compounds, developers and districts for search and forms; fetched once per visit. */
export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => {
    catalogPromise ??= api<Catalog>("/catalog").catch((error) => {
      catalogPromise = null;
      throw error;
    });
    let live = true;
    catalogPromise.then((result) => live && setCatalog(result)).catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  return catalog;
}

export function safeExternalUrl(value: string | null | undefined): string | undefined {
  try {
    const url = new URL(value || "");
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export const classLabel = (value: string | null | undefined) =>
  t(value === "house" ? "Villas & houses" : value === "chalet" ? "Chalets" : value === "apartment" ? "Apartments" : "Other");

const bucketText: Record<string, string> = {
  ready: "Ready",
  under_1y: "Within a year",
  "1_2y": "In 1–2 years",
  "2_3y": "In 2–3 years",
  "3y_plus": "In 3+ years",
  unknown: "Not published",
};
const planText: Record<string, string> = {
  cash: "Cash",
  under_3y: "Under 3 years left",
  "3_6y": "3–6 years left",
  "6_9y": "6–9 years left",
  "9y_plus": "9+ years left",
  unknown: "Term not published",
};
export const planLabel = (bucket: string) => t(planText[bucket] ?? bucket);

/** A calendar year, without thousands grouping. */
export const year = (value: number | string | null | undefined) =>
  value == null ? "—" : new Intl.NumberFormat(locale(), { useGrouping: false }).format(Number(value));

export const bucketLabel = (bucket: string) => t(bucketText[bucket] ?? bucket);

export const deliveryLabel = (bucket: string, years?: number | null) =>
  bucket === "ready"
    ? t("Ready")
    : bucket === "unknown"
      ? t("Not published")
      : years != null
        ? t("In {n} years", { n: number(years, 1) })
        : titleCase(bucket);

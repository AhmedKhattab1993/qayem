/** First-party measurement: which pages people read and what they do there, sent to Qayem's own API.
 * No cookies and no third parties. A random ID in this browser counts returning visitors once. */
import { getLanguage } from "./locale";

const UTM = ["utm_source", "utm_medium", "utm_campaign"] as const;
export type Utm = Partial<Record<(typeof UTM)[number], string>>;

function stored(storage: () => Storage, key: string, make: () => string) {
  try {
    const value = storage().getItem(key);
    if (value) return value;
    const next = make();
    storage().setItem(key, next);
    return next;
  } catch {
    return make();
  }
}

let visitorId: string | null = null;
export const visitor = () =>
  (visitorId ??= stored(() => localStorage, "qayem:visitor", () =>
    `v-${(crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`).slice(0, 36)}`,
  ));

/** Where this visit came from: the landing page's campaign tags, kept for the visit. */
export function utm(): Utm {
  try {
    const saved = sessionStorage.getItem("qayem:utm");
    if (saved) return JSON.parse(saved) as Utm;
  } catch {
    /* fall through */
  }
  const params = new URLSearchParams(window.location.search);
  const tags: Utm = {};
  for (const key of UTM) {
    const value = params.get(key);
    if (value) tags[key] = value.slice(0, 80);
  }
  try {
    sessionStorage.setItem("qayem:utm", JSON.stringify(tags));
  } catch {
    /* this visit only */
  }
  return tags;
}

let landingReferrer: string | null = document.referrer || null;

export type EventType =
  | "pageview"
  | "outbound_click"
  | "evaluate_run"
  | "share_click"
  | "cta_click"
  | "lead_open"
  | "alert_open"
  | "sheet_view"
  | "lookup";

export function track(
  type: EventType,
  data: { entity?: string; unit_id?: number; meta?: Record<string, string | number | boolean> } = {},
) {
  try {
    const body = JSON.stringify({
      type,
      path: window.location.pathname,
      visitor: visitor(),
      lang: getLanguage(),
      referrer: type === "pageview" ? landingReferrer : null,
      ...utm(),
      ...data,
    });
    if (type === "pageview") landingReferrer = null; // the referrer belongs to the landing page only
    const blob = new Blob([body], { type: "application/json" });
    if (!navigator.sendBeacon?.("/api/events", blob))
      void fetch("/api/events", { method: "POST", body, headers: { "Content-Type": "application/json" }, keepalive: true }).catch(
        () => {},
      );
  } catch {
    /* measurement never interrupts the page */
  }
}

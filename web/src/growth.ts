/** Lead capture and alerts: Qayem's own API, with the anti-spam checks it asks for. */
import { useEffect, useState } from "react";
import { getLanguage } from "./locale";
import { utm, visitor } from "./track";

export interface GrowthConfig {
  leads: boolean;
  turnstile_site_key: string | null;
  email_alerts: boolean;
}

let configPromise: Promise<GrowthConfig> | null = null;
export function useGrowthConfig() {
  const [config, setConfig] = useState<GrowthConfig | null>(null);
  useEffect(() => {
    configPromise ??= fetch("/api/config")
      .then((response) => (response.ok ? (response.json() as Promise<GrowthConfig>) : Promise.reject()))
      .catch(() => {
        configPromise = null;
        return { leads: false, turnstile_site_key: null, email_alerts: false };
      });
    let live = true;
    configPromise.then((value) => live && setConfig(value));
    return () => {
      live = false;
    };
  }, []);
  return config;
}

/** The API's reasons, in words for the form. */
const reasons: Record<string, string> = {
  invalid_contact: "Enter a WhatsApp number with its country code, or an e-mail address.",
  verification_failed: "We could not confirm you are not a robot. Please try again.",
  rate_limited: "Too many requests from this connection today. Please try again tomorrow.",
  too_many_alerts: "This contact already has the most alerts we send. Remove one first.",
  unavailable: "Requests are not open yet. Please try again later.",
  invalid: "Something in the form is not valid. Please check it.",
};

export class SubmitError extends Error {}

export async function submit(path: "/leads" | "/alerts", body: Record<string, unknown>) {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, ...utm(), visitor: visitor(), lang: getLanguage(), path: window.location.pathname }),
    });
  } catch {
    throw new SubmitError("We could not send it. Check your connection and try again.");
  }
  if (response.ok) return (await response.json()) as { ok: boolean; existing?: boolean };
  let code = "";
  try {
    code = (await response.json()).detail;
  } catch {
    /* keep the generic reason */
  }
  throw new SubmitError(reasons[code] ?? "We could not send it. Please try again.");
}

declare global {
  interface Window {
    turnstile?: {
      render: (element: HTMLElement, options: Record<string, unknown>) => string;
      reset: (id?: string) => void;
      remove: (id?: string) => void;
    };
  }
}

let turnstileScript: Promise<void> | null = null;
/** Cloudflare Turnstile, loaded only when a form that needs it is on screen. */
export function loadTurnstile() {
  turnstileScript ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      turnstileScript = null;
      reject(new Error("Turnstile unavailable"));
    };
    document.head.appendChild(script);
  });
  return turnstileScript;
}

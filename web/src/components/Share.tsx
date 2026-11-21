import { Link } from "react-router-dom";
import { FileText, MessageCircle, Share2 } from "lucide-react";
import { money, nameOf, percent, place } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { track } from "../track";
import type { Unit } from "../types";
import { levelText } from "./Opportunity";
import { unitName } from "./UnitTable";

/** A shared link names where it was shared, so the visits it brings are counted. */
export function sharedUrl(path: string, medium: string) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("utm_source", medium);
  url.searchParams.set("utm_medium", "share");
  return url.href;
}

/** The unit's verdict in one line, in the interface language: what a family chat needs to see. */
export function unitShareText(unit: Unit) {
  const where = nameOf(unit.compound) ?? place(unit.district) ?? "";
  const verdict =
    unit.launch?.same_finishing
      ? t(unit.launch.gap < 0 ? "{gap} below the developer today" : "{gap} above the developer today", { gap: percent(Math.abs(unit.launch.gap)) })
      : unit.peers
        ? t(unit.peers.gap < 0 ? "{gap} below similar units" : "{gap} above similar units", { gap: percent(Math.abs(unit.peers.gap)) })
        : t(levelText[unit.opportunity.level]);
  return t("{unit} in {place}: {verdict}. {price}, checked on Qayem.", {
    unit: unitName(unit).replace(/ /g, " "),
    place: where,
    verdict,
    price: money(unit.price, true),
  });
}

export function ShareBar({ text, path, unitId, sheet = true }: { text: string; path: string; unitId?: number; sheet?: boolean }) {
  const { toast } = useStore();
  const whatsapp = `https://wa.me/?text=${encodeURIComponent(`${text}\n${sharedUrl(path, "whatsapp")}`)}`;
  const native = async () => {
    track("share_click", { unit_id: unitId, meta: { channel: "native" } });
    const url = sharedUrl(path, "link");
    try {
      if (navigator.share) return await navigator.share({ text, url });
      await navigator.clipboard.writeText(`${text}\n${url}`);
      toast("Link copied");
    } catch (error) {
      if ((error as Error).name !== "AbortError") toast("Copy the link from the address bar to share this unit.");
    }
  };
  return (
    <span className="share-bar">
      <a
        className="btn btn-sm btn-whatsapp"
        href={whatsapp}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => track("share_click", { unit_id: unitId, meta: { channel: "whatsapp" } })}
      >
        <MessageCircle size={15} /> {t("Send on WhatsApp")}
      </a>
      <button type="button" className="btn btn-sm" onClick={native}>
        <Share2 size={15} /> {t("Share")}
      </button>
      {sheet && unitId != null && (
        <Link className="btn btn-sm" to={`/sheet/${unitId}`} onClick={() => track("cta_click", { unit_id: unitId, meta: { cta: "deal_sheet" } })}>
          <FileText size={15} /> {t("Deal sheet")}
        </Link>
      )}
    </span>
  );
}

import { MessageCircle, Share2 } from "lucide-react";
import { t } from "../locale";
import { useStore } from "../store";
import { track } from "../track";

/** A shared link names where it was shared, so the visits it brings are counted. */
export function sharedUrl(path: string, medium: string) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("utm_source", medium);
  url.searchParams.set("utm_medium", "share");
  return url.href;
}

export function ShareBar({ text, path }: { text: string; path: string }) {
  const { toast } = useStore();
  const whatsapp = `https://wa.me/?text=${encodeURIComponent(`${text}\n${sharedUrl(path, "whatsapp")}`)}`;
  const native = async () => {
    track("share_click", { meta: { channel: "native" } });
    const url = sharedUrl(path, "link");
    try {
      if (navigator.share) return await navigator.share({ text, url });
      await navigator.clipboard.writeText(`${text}\n${url}`);
      toast("Link copied");
    } catch (error) {
      if ((error as Error).name !== "AbortError") toast("Copy the link from the address bar to share this comparison.");
    }
  };
  return (
    <span className="share-bar">
      <a
        className="btn btn-sm btn-whatsapp"
        href={whatsapp}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => track("share_click", { meta: { channel: "whatsapp" } })}
      >
        <MessageCircle size={15} /> {t("Send on WhatsApp")}
      </a>
      <button type="button" className="btn btn-sm" onClick={native}>
        <Share2 size={15} /> {t("Share")}
      </button>
    </span>
  );
}

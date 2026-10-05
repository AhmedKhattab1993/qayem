import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { flushSync } from "react-dom";
import { Link } from "react-router-dom";
import { Play, RotateCcw, Scale } from "lucide-react";
import { number, scrollBehavior } from "../lib";
import { getLanguage, t } from "../locale";

// The pilot explainer, encoded by scripts/encode-explainer.sh into web/public/media. Bump VERSION with the files.
const VERSION = "v4";
const SECONDS = 111;
const media = (name: string) => `/media/explainer-${VERSION}-${name}`;

export const explainerLength = () => `${number(Math.floor(SECONDS / 60))}:${number(SECONDS % 60).padStart(2, number(0))}`;

export interface ExplainerHandle {
  /** Scroll to the player and start it. Call from a click handler: phones only start sound on a tap. */
  play: () => void;
}

/**
 * A poster until asked, so the page loads no video at all. The phone-sized file is picked on narrow
 * screens; nothing autoplays and nothing loops.
 */
export function Explainer({ ref }: { ref?: Ref<ExplainerHandle> }) {
  const [state, setState] = useState<"poster" | "playing" | "ended">("poster");
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);

  const start = () => {
    // Mount the video within the tap itself, so the browser lets it play with sound.
    flushSync(() => setState("playing"));
    const player = video.current;
    if (!player) return;
    if (player.ended) player.currentTime = 0;
    player.play().catch(() => undefined); // blocked: the controls are there to start it
    player.focus({ preventScroll: true });
  };
  useImperativeHandle(ref, () => ({
    play: () => {
      start();
      box.current?.scrollIntoView({ block: "center", behavior: scrollBehavior() });
    },
  }));

  const inArabic = getLanguage() !== "ar";
  return (
    <div className={`explainer is-${state}`} ref={box} id="explainer">
      {state !== "poster" && (
        <video
          ref={video}
          controls
          playsInline
          preload="auto"
          poster={media("poster-1280.webp")}
          onEnded={() => setState("ended")}
          aria-label={t("How Qayem works, a short film")}
        >
          <source src={media("720.mp4")} type="video/mp4" media="(max-width: 900px)" />
          <source src={media("1080.mp4")} type="video/mp4" />
        </video>
      )}
      {state === "poster" && (
        <button type="button" className="explainer-poster" onClick={start}>
          <img
            src={media("poster-1280.webp")}
            srcSet={`${media("poster-640.webp")} 640w, ${media("poster-1280.webp")} 1280w`}
            sizes="(max-width: 1100px) 100vw, 1060px"
            width={1280}
            height={720}
            loading="lazy"
            decoding="async"
            alt=""
          />
          <span className="explainer-play" aria-hidden="true">
            <Play size={26} fill="currentColor" />
          </span>
          <span className="explainer-label">
            <strong>{t("Watch how Qayem works")}</strong>
            <span className="num">
              {explainerLength()}
              {inArabic && <> · {t("In Arabic")}</>}
            </span>
          </span>
        </button>
      )}
      {state === "ended" && (
        <div className="explainer-end">
          <Link className="btn btn-brass" to="/evaluate">
            <Scale size={16} /> {t("Compare a unit")}
          </Link>
          <button type="button" className="btn explainer-again" onClick={start}>
            <RotateCcw size={16} /> {t("Watch again")}
          </button>
        </div>
      )}
    </div>
  );
}

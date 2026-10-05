import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Expand, ImageOff, X } from "lucide-react";
import { number } from "../lib";
import { t } from "../locale";

/** The listing's photos as the source published them: a grid on wide screens, a swipeable strip on phones,
 * and a full-screen viewer. Photos load from the source; one that fails to load is dropped. */
export function Gallery({ images, title, source }: { images: string[]; title: string; source: string }) {
  const [failed, setFailed] = useState<string[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const photos = images.filter((url) => !failed.includes(url));
  const drop = (url: string) => setFailed((current) => [...current, url]);
  if (!photos.length) return null;
  const alt = (index: number) => t("Photo {n} of {total}: {title}", { n: number(index + 1), total: number(photos.length), title });
  return (
    <section className={`gallery gallery-${Math.min(photos.length, 5)}`} aria-label={t("Photos")}>
      <div className="gallery-track">
        {photos.slice(0, 5).map((url, index) => (
          <button key={url} type="button" className="gallery-item" onClick={() => setOpen(index)} aria-label={t("Open photo {n}", { n: number(index + 1) })}>
            <img
              src={url}
              alt={alt(index)}
              loading={index === 0 ? "eager" : "lazy"}
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => drop(url)}
            />
            {index === 4 && photos.length > 5 && <span className="gallery-more num">+{number(photos.length - 5)}</span>}
          </button>
        ))}
      </div>
      <div className="gallery-foot">
        <span className="muted">{t("Photos published by {source}", { source })}</span>
        <button type="button" className="link-arrow" onClick={() => setOpen(0)}>
          <Expand size={15} /> {t("All {n} photos", { n: number(photos.length), count: photos.length })}
        </button>
      </div>
      {open != null && <Viewer photos={photos} start={open} alt={alt} onClose={() => setOpen(null)} onFail={drop} />}
    </section>
  );
}

function Viewer({
  photos,
  start,
  alt,
  onClose,
  onFail,
}: {
  photos: string[];
  start: number;
  alt: (index: number) => string;
  onClose: () => void;
  onFail: (url: string) => void;
}) {
  const [index, setIndex] = useState(Math.min(start, photos.length - 1));
  const close = useRef<HTMLButtonElement>(null);
  const touch = useRef<number | null>(null);
  const rtl = document.documentElement.dir === "rtl";
  const go = useCallback((step: number) => setIndex((i) => (i + step + photos.length) % photos.length), [photos.length]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      // Arrow keys follow the screen: in Arabic the next photo is to the left.
      else if (event.key === "ArrowRight") go(rtl ? -1 : 1);
      else if (event.key === "ArrowLeft") go(rtl ? 1 : -1);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [go, onClose, rtl]);
  if (!photos.length) return null;
  const url = photos[Math.min(index, photos.length - 1)];
  return (
    <div
      className="viewer"
      role="dialog"
      aria-modal="true"
      aria-label={t("Photos")}
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
      onTouchStart={(event) => (touch.current = event.touches[0].clientX)}
      onTouchEnd={(event) => {
        if (touch.current == null) return;
        const dx = event.changedTouches[0].clientX - touch.current;
        touch.current = null;
        if (Math.abs(dx) > 40) go((dx < 0) !== rtl ? 1 : -1);
      }}
    >
      <div className="viewer-bar">
        <span className="num">
          {number(index + 1)} / {number(photos.length)}
        </span>
        <button ref={close} type="button" className="viewer-close" onClick={onClose} aria-label={t("Close photos")}>
          <X size={22} />
        </button>
      </div>
      <img key={url} src={url} alt={alt(index)} referrerPolicy="no-referrer" onError={() => onFail(url)} />
      {photos.length > 1 && (
        <>
          <button type="button" className="viewer-nav viewer-prev" onClick={() => go(-1)} aria-label={t("Previous photo")}>
            <ChevronLeft size={26} className="flip-rtl" />
          </button>
          <button type="button" className="viewer-nav viewer-next" onClick={() => go(1)} aria-label={t("Next photo")}>
            <ChevronRight size={26} className="flip-rtl" />
          </button>
        </>
      )}
    </div>
  );
}

/** A small photo for lists; a quiet placeholder when the source published none or it fails to load. */
export function Thumb({ url }: { url: string | null | undefined }) {
  const [broken, setBroken] = useState(false);
  return (
    <span className="thumb" aria-hidden="true">
      {url && !broken ? (
        <img src={url} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
      ) : (
        <ImageOff size={16} />
      )}
    </span>
  );
}

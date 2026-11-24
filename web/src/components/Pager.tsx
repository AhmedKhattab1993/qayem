import { ChevronLeft, ChevronRight } from "lucide-react";
import { number, scrollBehavior } from "../lib";
import { t } from "../locale";

/** After a page change, bring the top of the list (the element with id="results") back into view. */
export const scrollToResults = () =>
  requestAnimationFrame(() => document.getElementById("results")?.scrollIntoView({ block: "start", behavior: scrollBehavior() }));

export function Pager({
  page,
  pages,
  total,
  pageSize,
  onPage,
  noun = "compounds",
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  noun?: string;
}) {
  if (pages <= 1) return null;
  const start = (page - 1) * pageSize + 1;
  const around = Array.from({ length: Math.min(5, pages) }, (_, i) => Math.min(Math.max(1, page - 2), Math.max(1, pages - 4)) + i);
  const first = around[0];
  const last = around[around.length - 1];
  const numbers: (number | "…")[] = [
    ...(first > 1 ? [1, ...(first > 2 ? ["…" as const] : [])] : []),
    ...around,
    ...(last < pages ? [...(last < pages - 1 ? ["…" as const] : []), pages] : []),
  ];
  return (
    <div className="pager">
      <span className="muted num">
        {t("{start}–{end} of {total} " + noun, {
          start: number(start),
          end: number(Math.min(page * pageSize, total)),
          total: number(total),
        })}
      </span>
      <nav aria-label={t("Pages")}>
        <button onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label={t("Previous page")}>
          <ChevronLeft size={16} className="flip-rtl" />
        </button>
        {numbers.map((n, index) =>
          n === "…" ? (
            <span key={`gap-${index}`} className="pager-gap" aria-hidden="true">
              …
            </span>
          ) : (
            <button
              key={n}
              className={n === page ? "is-current num" : "num"}
              aria-current={n === page ? "page" : undefined}
              onClick={() => onPage(n)}
            >
              {number(n)}
            </button>
          ),
        )}
        <button onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label={t("Next page")}>
          <ChevronRight size={16} className="flip-rtl" />
        </button>
      </nav>
    </div>
  );
}

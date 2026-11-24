import { Link } from "react-router-dom";
import { getLanguage, t } from "../locale";

/**
 * The mark: the ق of قيّم drawn in square Kufic, the lettering of Cairo's stone inscriptions,
 * on a grid where every cell is one square metre. Its eye is a single square metre; its two
 * dots are the two prices the guide always reads together, resale and new.
 */
export function Mark({ size = 34, bare = false }: { size?: number; bare?: boolean }) {
  return (
    <svg className={`mark${bare ? " mark-bare" : ""}`} viewBox="0 0 48 48" width={size} height={size} aria-hidden="true">
      {!bare && <rect className="mark-tile" width="48" height="48" rx="5" />}
      <path className="mark-glyph" fillRule="evenodd" d="M24 16.5h15v25H9v-15h5v10h20v-5H24zM29 21.5v5h5v-5z" />
      <path className="mark-dots" d="M24 6.5h5v5h-5zM34 6.5h5v5h-5z" />
    </svg>
  );
}

export function Brand() {
  const arabic = getLanguage() === "ar";
  return (
    <Link to="/" className="brand" aria-label={t("Qayem home")}>
      <Mark />
      <span className="brand-word" lang={arabic ? "ar" : "en"}>
        {arabic ? "قيّم" : "Qayem"}
      </span>
    </Link>
  );
}

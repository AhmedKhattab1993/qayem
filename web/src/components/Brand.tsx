import { Link } from "react-router-dom";
import { t } from "../locale";

/** The mark: a balance, beam tipped, with a brass pivot. */
export function Mark({ size = 34 }: { size?: number }) {
  return (
    <svg className="mark" viewBox="0 0 40 40" width={size} height={size} aria-hidden="true">
      <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="11" fill="currentColor" opacity="0.08" />
      <g fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M8 13.5 32 11.5M20 12.5V32M14 32h12" />
        <path d="M8 13.5 4.5 22h7ZM32 11.5 28.5 20h7Z" />
      </g>
      <path d="M4.5 22a3.5 3.2 0 0 0 7 0ZM28.5 20a3.5 3.2 0 0 0 7 0Z" fill="currentColor" />
      <circle cx="20" cy="12.4" r="2.9" fill="var(--mark-dot, #e3bb66)" />
    </svg>
  );
}

export function Brand() {
  return (
    <Link to="/" className="brand" aria-label={t("Qayem home")}>
      <Mark />
      <span className="brand-word">
        <span lang="ar">قيّم</span>
        <span className="brand-latin" lang="en">
          qayem
        </span>
      </span>
    </Link>
  );
}

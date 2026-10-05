import { AlertCircle, ArrowRight, Compass } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Mark } from "./Brand";
import { t } from "../locale";

export function Loading({ label = "Weighing the market…" }: { label?: string }) {
  return (
    <div className="state state-loading" role="status">
      <span className="loading-scale">
        <Mark size={44} />
      </span>
      <p>{t(label)}</p>
    </div>
  );
}

export function ErrorState({ message, retry, missing }: { message: string; retry?: () => void; missing?: boolean }) {
  if (missing)
    return (
      <div className="state" role="alert">
        <span className="state-icon">
          <Compass size={26} />
        </span>
        <h2>{t("A little off the map")}</h2>
        <p>{t(message)}</p>
        <Link to="/evaluate" className="btn btn-ink">
          {t("Compare a unit")} <ArrowRight size={16} className="flip-rtl" />
        </Link>
      </div>
    );
  return (
    <div className="state" role="alert">
      <span className="state-icon">
        <AlertCircle size={26} />
      </span>
      <h2>{t("Let’s try that again")}</h2>
      <p>{t(message)}</p>
      {retry && (
        <button className="btn btn-ink" onClick={retry}>
          {t("Try again")} <ArrowRight size={16} className="flip-rtl" />
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  text,
  action,
  icon,
}: {
  title: string;
  text: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="state">
      <span className="state-icon">{icon ?? <Compass size={26} />}</span>
      <h2>{title}</h2>
      <p>{text}</p>
      {action}
    </div>
  );
}

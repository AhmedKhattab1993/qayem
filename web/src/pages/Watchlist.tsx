import { Link } from "react-router-dom";
import { Bookmark, Building2, Landmark, X } from "lucide-react";
import { classLabel, money, number, signed } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { usePinned } from "../entities";
import type { Overview } from "../types";
import { EmptyState } from "../components/States";
import { GradeBadge } from "../components/Valuation";
import { HistoryPending } from "../components/Entity";

export default function Watchlist({ overview }: { overview: Overview | null }) {
  const { watch, toggleWatch } = useStore();
  const { get, retry } = usePinned(watch);
  return (
    <div className="watchlist page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Watchlist")}</span>
          <h1 className="display">
            {t("The compounds")} <em>{t("you care about.")}</em>
          </h1>
          <p className="lede">
            {t("Kept in this browser only. No account, no enquiries sent to anyone.")}
          </p>
        </div>
      </header>
      <div className="page">
        <HistoryPending overview={overview} />
        {watch.length === 0 ? (
          <EmptyState
            icon={<Bookmark size={26} />}
            title={t("Nothing on your watchlist yet.")}
            text={t("Open a compound or developer and choose Watch.")}
            action={
              <Link className="btn btn-ink" to="/compounds">
                <Building2 size={16} /> {t("Browse compounds")}
              </Link>
            }
          />
        ) : (
          <ul className="watch-list">
            {watch.map((item) => {
              const entry = get(item);
              const path = `/${item.kind === "compound" ? "compounds" : "developers"}/${encodeURIComponent(item.key)}`;
              return (
                <li key={`${item.kind}-${item.key}`}>
                  <span className="watch-icon">{item.kind === "compound" ? <Building2 size={18} /> : <Landmark size={18} />}</span>
                  <div className="watch-body">
                    <Link to={path} dir="auto">
                      <strong>{item.name}</strong>
                    </Link>
                    {entry.status === "ready" ? (
                      entry.kind === "compound" ? (
                        <span className="watch-meta">
                          {entry.data.compound.classes
                            .filter((c) => c.reference_ppm)
                            .map((c) => (
                              <span key={c.class} className="num">
                                {classLabel(c.class)} {money(c.reference_ppm, true)}/{t("m²")} <GradeBadge grade={c.grade} />
                              </span>
                            ))}
                          <span className="num">{t("{n} listings", { n: number(entry.data.compound.units) })}</span>
                          <span className="num">
                            {t("vs district")} {signed(entry.data.compound.premium_vs_district)}
                          </span>
                        </span>
                      ) : (
                        <span className="watch-meta">
                          <span className="num">
                            {t("vs district")} {signed(entry.data.premium_vs_district)}
                          </span>
                          <span className="num">{t("{n} listings", { n: number(entry.data.units) })}</span>
                          <span className="num">{t("{n} compounds", { n: number(entry.data.compounds.length) })}</span>
                        </span>
                      )
                    ) : entry.status === "error" ? (
                      <button className="link-arrow" onClick={retry}>
                        {t("Unavailable · retry")}
                      </button>
                    ) : (
                      <span className="muted">…</span>
                    )}
                  </div>
                  <button
                    className="btn btn-sm btn-icon btn-ghost"
                    aria-label={t("Remove {name} from your watchlist", { name: item.name })}
                    onClick={() => toggleWatch(item)}
                  >
                    <X size={16} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

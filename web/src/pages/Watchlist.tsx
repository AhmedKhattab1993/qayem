import { Link } from "react-router-dom";
import { Bookmark, Building2, Landmark, X } from "lucide-react";
import { classLabel, money, number, signed, tone } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { pinnedName, pinnedPath, usePinned } from "../entities";
import type { Overview } from "../types";
import { EmptyState } from "../components/States";

export default function Watchlist(_props: { overview: Overview | null }) {
  const { watch, toggleWatch } = useStore();
  const { get, retry } = usePinned(watch);
  return (
    <div className="watchlist page-enter">
      <header className="page-head">
        <div className="page">
          <span className="eyebrow">{t("Watchlist")}</span>
          <h1 className="display">
            {t("The compounds and developers")} <em>{t("you care about.")}</em>
          </h1>
          <p className="lede">
            {t("Kept in this browser only. No account, no enquiries sent to anyone. Open a compound and ask for an alert, and we message you when its prices move.")}
          </p>
        </div>
      </header>
      <div className="page">
        {watch.length === 0 ? (
          <EmptyState
            icon={<Bookmark size={26} />}
            title={t("Nothing on your watchlist yet.")}
            text={t("Open a compound or developer and choose Watch.")}
            action={
              <div className="entity-actions">
                <Link className="btn btn-primary" to="/compounds">
                  <Building2 size={16} /> {t("Browse compounds")}
                </Link>
              </div>
            }
          />
        ) : (
          <section className="watch-section">
          <ul className="watch-list">
            {watch.map((item) => {
              const entry = get(item);
              const path = pinnedPath(item);
              return (
                <li key={`${item.kind}-${item.key}`}>
                  <span className="watch-icon">
                    {item.kind === "compound" ? <Building2 size={18} /> : <Landmark size={18} />}
                  </span>
                  <div className="watch-body">
                    <Link to={path} dir="auto">
                      <strong>{pinnedName(item, entry)}</strong>
                    </Link>
                    {entry.status === "ready" ? (
                      entry.kind === "compound" ? (
                        <span className="watch-meta">
                          {entry.data.compound.classes
                            .filter((c) => c.median_asking_ppm)
                            .map((c) => (
                              <span key={c.class} className="num">
                                {classLabel(c.class)} {money(c.median_asking_ppm, true)}/{t("m²")}
                              </span>
                            ))}
                          <span className="num">{t("{n} listings", { n: number(entry.data.compound.units), count: entry.data.compound.units })}</span>
                          {entry.data.compound.launch?.median_gap != null && (
                            <span className={`num ${tone(entry.data.compound.launch.median_gap)}`}>
                              {t("vs developer")} {signed(entry.data.compound.launch.median_gap)}
                            </span>
                          )}
                          <span className="num">{t("{n} opportunities", { n: number(entry.data.compound.good_count), count: entry.data.compound.good_count })}</span>
                        </span>
                      ) : (
                        <span className="watch-meta">
                          {entry.data.launch?.median_gap != null && (
                            <span className={`num ${tone(entry.data.launch.median_gap)}`}>
                              {t("vs developer")} {signed(entry.data.launch.median_gap)}
                            </span>
                          )}
                          <span className="num">{t("{n} opportunities", { n: number(entry.data.good_count), count: entry.data.good_count })}</span>
                          <span className="num">{t("{n} listings", { n: number(entry.data.units), count: entry.data.units })}</span>
                          <span className="num">{t("{n} compounds", { n: number(entry.data.compounds.length), count: entry.data.compounds.length })}</span>
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
                    aria-label={t("Remove {name} from your watchlist", { name: pinnedName(item, entry) })}
                    onClick={() => toggleWatch(item)}
                  >
                    <X size={16} />
                  </button>
                </li>
              );
            })}
          </ul>
          </section>
        )}
      </div>
    </div>
  );
}

import { Link } from "react-router-dom";
import { Bookmark, Building2, Home, Landmark, Rows3, X } from "lucide-react";
import { classLabel, money, nameOf, number, place, signed, tone } from "../lib";
import { t } from "../locale";
import { useStore } from "../store";
import { pinnedName, pinnedPath, usePinned } from "../entities";
import { LevelBadge } from "../components/Opportunity";
import { NameList } from "../components/Names";
import { termsLabel } from "../components/UnitTable";
import { Thumb } from "../components/Gallery";
import type { Overview } from "../types";
import { EmptyState } from "../components/States";
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
            {t("The units and compounds")} <em>{t("you care about.")}</em>
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
            text={t("Save a unit, or open a compound or developer and choose Watch.")}
            action={
              <div className="entity-actions">
                <Link className="btn btn-ink" to="/units">
                  <Rows3 size={16} /> {t("Browse units")}
                </Link>
                <Link className="btn" to="/compounds">
                  <Building2 size={16} /> {t("Browse compounds")}
                </Link>
              </div>
            }
          />
        ) : (
          <ul className="watch-list">
            {watch.map((item) => {
              const entry = get(item);
              const path = pinnedPath(item);
              return (
                <li key={`${item.kind}-${item.key}`}>
                  {item.kind === "unit" && entry.status === "ready" && entry.kind === "unit" ? (
                    <Thumb url={entry.data.unit.photo} />
                  ) : (
                    <span className="watch-icon">
                      {item.kind === "compound" ? <Building2 size={18} /> : item.kind === "unit" ? <Home size={18} /> : <Landmark size={18} />}
                    </span>
                  )}
                  <div className="watch-body">
                    <Link to={path} dir="auto">
                      <strong>{pinnedName(item, entry)}</strong>
                    </Link>
                    {entry.status === "ready" ? (
                      entry.kind === "unit" ? (
                        <span className="watch-meta">
                          <span className="num">
                            <NameList items={[nameOf(entry.data.unit.compound), place(entry.data.unit.district)]} />
                          </span>
                          <b className="num">{money(entry.data.unit.price, true)}</b>
                          <span className="num">{termsLabel(entry.data.unit)}</span>
                          <LevelBadge level={entry.data.unit.opportunity.level} />
                        </span>
                      ) : entry.kind === "compound" ? (
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
        )}
      </div>
    </div>
  );
}

import { Link } from "react-router-dom";
import { BellRing, Bookmark, Building2, Check, Home, Landmark, Plus, Rows3, X } from "lucide-react";
import { classLabel, money, nameOf, number, place, signed, tone, useApi, useCatalog } from "../lib";
import { t } from "../locale";
import { isPinned, useStore, type SavedSearch } from "../store";
import { describeSearch } from "../searches";
import { pinnedName, pinnedPath, usePinned } from "../entities";
import { LevelBadge } from "../components/Opportunity";
import { NameList } from "../components/Names";
import { termsLabel } from "../components/UnitTable";
import { Thumb } from "../components/Gallery";
import type { Overview, Page, Unit } from "../types";
import { EmptyState } from "../components/States";
import { HistoryPending } from "../components/Entity";

/** A saved search: how many units match now, and how many were indexed since it was last opened. */
function SearchRow({ search }: { search: SavedSearch }) {
  const { toggleSearch, markSeen } = useStore();
  const catalog = useCatalog();
  const and = search.query ? "&" : "";
  const now = useApi<Page<Unit>>(`/units?${search.query}${and}sort=newest&page_size=1`);
  const fresh = useApi<Page<Unit>>(`/units?${search.query}${and}newer_than=${search.seen}&page_size=1`);
  const label = describeSearch(search.query, catalog);
  const newest = now.data?.items[0]?.id;
  const count = fresh.data?.total ?? 0;
  return (
    <li>
      <span className={`watch-icon${count ? " is-fresh" : ""}`}>
        <BellRing size={18} />
      </span>
      <div className="watch-body">
        <Link to={`/units?${search.query}`} onClick={() => newest && markSeen(search.query, newest)}>
          <strong>{label}</strong>
        </Link>
        <span className="watch-meta">
          {now.data ? (
            <span className="num">{t("{n} units", { n: number(now.data.total), count: now.data.total })}</span>
          ) : now.error ? (
            <button className="link-arrow" onClick={now.retry}>
              {t("Unavailable · retry")}
            </button>
          ) : (
            <span className="muted">…</span>
          )}
          {count > 0 && (
            <b className="fresh-tag num">{t("{n} new since you last looked", { n: number(count), count })}</b>
          )}
        </span>
      </div>
      <button
        className="btn btn-sm btn-icon btn-ghost"
        aria-label={t("Remove the saved search: {name}", { name: label })}
        onClick={() => toggleSearch(search.query, 0)}
      >
        <X size={16} />
      </button>
    </li>
  );
}

export default function Watchlist({ overview }: { overview: Overview | null }) {
  const { watch, toggleWatch, searches, compare, toggleCompare } = useStore();
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
        {searches.length > 0 && (
          <section className="watch-section" aria-labelledby="searches-heading">
            <h2 id="searches-heading">{t("Saved searches")}</h2>
            <p className="muted">{t("New listings that match appear here the next time you visit. Nothing is sent to you.")}</p>
            <ul className="watch-list">
              {searches.map((search) => (
                <SearchRow key={search.query} search={search} />
              ))}
            </ul>
          </section>
        )}
        {watch.length === 0 ? (
          <EmptyState
            icon={<Bookmark size={26} />}
            title={t("Nothing on your watchlist yet.")}
            text={t("Save a unit or a search, or open a compound or developer and choose Watch.")}
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
          <section className="watch-section" aria-labelledby={searches.length > 0 ? "saved-heading" : undefined}>
          {searches.length > 0 && <h2 id="saved-heading">{t("Units, compounds and developers")}</h2>}
          <ul className="watch-list" aria-labelledby={searches.length > 0 ? "saved-heading" : undefined}>
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
                  {item.kind === "unit" && (
                    <button
                      className={`btn btn-sm${isPinned(compare, "unit", item.key) ? " btn-ink" : ""}`}
                      aria-pressed={isPinned(compare, "unit", item.key)}
                      onClick={() => toggleCompare(item)}
                    >
                      {isPinned(compare, "unit", item.key) ? <Check size={15} /> : <Plus size={15} />}
                      <span className="watch-compare-label">{t(isPinned(compare, "unit", item.key) ? "In comparison" : "Compare")}</span>
                    </button>
                  )}
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

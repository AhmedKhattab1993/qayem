import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  Bookmark,
  Building2,
  Calculator,
  CornerDownLeft,
  Landmark,
  Languages,
  MapPin,
  Rows3,
  Scale,
  Search,
} from "lucide-react";
import { number, useCatalog, sep, nameOf, place } from "../lib";
import { getLanguage, t } from "../locale";

type Item = { id: string; group: string; label: string; meta?: string; icon: ReactNode; run: () => void };

export function CommandPalette({ onClose, onToggleLanguage }: { onClose: () => void; onToggleLanguage: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const catalog = useCatalog();
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    input.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLocaleLowerCase();
    const matches = (...values: (string | null)[]) =>
      !q || values.some((value) => value && value.toLocaleLowerCase().includes(q));
    const go = (path: string) => () => {
      navigate(path);
      onClose();
    };
    const result: Item[] = [];
    for (const compound of catalog?.compounds.filter((c) => matches(c.name, c.name_ar, c.developer, c.developer_ar)).slice(0, q ? 6 : 4) ?? [])
      result.push({
        id: `compound-${compound.key}`,
        group: "Compounds",
        label: nameOf(compound)!,
        meta: [nameOf(compound.developer ? { name: compound.developer, name_ar: compound.developer_ar } : null), place(compound.district)].filter(Boolean).join(sep()),
        icon: <Building2 size={17} />,
        run: go(`/compounds/${encodeURIComponent(compound.key)}`),
      });
    for (const developer of catalog?.developers.filter((d) => matches(d.name, d.name_ar)).slice(0, q ? 4 : 3) ?? [])
      result.push({
        id: `developer-${developer.key}`,
        group: "Developers",
        label: nameOf(developer)!,
        meta: t("{n} listings", { n: number(developer.units), count: developer.units }),
        icon: <Landmark size={17} />,
        run: go(`/developers/${encodeURIComponent(developer.key)}`),
      });
    for (const district of catalog?.districts.filter((d) => matches(d.name, place(d.name)!)).slice(0, q ? 4 : 3) ?? [])
      result.push({
        id: `district-${district.key}`,
        group: "Districts",
        label: place(district.name)!,
        meta: t("{n} listings", { n: number(district.units), count: district.units }),
        icon: <MapPin size={17} />,
        run: go(`/compounds?district=${encodeURIComponent(district.key)}`),
      });
    const pages: [string, string, ReactNode][] = [
      ["/evaluate", "Compare a unit", <Calculator size={17} />],
      ["/compounds", "Compounds", <Building2 size={17} />],
      ["/developers", "Developers", <Landmark size={17} />],
      ["/units", "Units", <Rows3 size={17} />],
      ["/compare", "Compare", <Scale size={17} />],
      ["/watchlist", "Watchlist", <Bookmark size={17} />],
      ["/methodology", "Methodology", <ArrowUpRight size={17} />],
    ];
    for (const [path, label, icon] of pages)
      if (matches(label, t(label))) result.push({ id: `page-${path}`, group: "Go to", label: t(label), icon, run: go(path) });
    if (q)
      result.push({
        id: "search",
        group: "Search",
        label: t("Units matching “{q}”", { q: query.trim() }),
        icon: <Search size={17} />,
        run: go(`/units?q=${encodeURIComponent(query.trim())}`),
      });
    if (matches("language", "english", "arabic", "العربية", "اللغة"))
      result.push({
        id: "language",
        group: "Preferences",
        label: getLanguage() === "ar" ? "English" : "العربية",
        icon: <Languages size={17} />,
        run: () => {
          onToggleLanguage();
          onClose();
        },
      });
    return result;
  }, [query, catalog, navigate, onClose, onToggleLanguage]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (index + 1) % Math.max(1, items.length));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (index - 1 + items.length) % Math.max(1, items.length));
    } else if (event.key === "Enter") {
      event.preventDefault();
      items[active]?.run();
    } else if (event.key === "Tab") {
      event.preventDefault();
    }
  };

  let lastGroup = "";
  return (
    <div className="palette-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label={t("Search Qayem")} onKeyDown={onKey}>
        <div className="palette-input">
          <Search size={20} />
          <input
            ref={input}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("A compound, developer, district, or page…")}
            aria-label={t("Search Qayem")}
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-results"
            aria-activedescendant={items[active] ? `palette-${items[active].id}` : undefined}
            maxLength={200}
          />
          <button className="kbd" onClick={onClose} aria-label={t("Close search")}>
            Esc
          </button>
        </div>
        <ul className="palette-results" id="palette-results" role="listbox" ref={list}>
          {items.map((item, index) => {
            const heading = item.group !== lastGroup ? item.group : "";
            lastGroup = item.group;
            return (
              <li key={item.id} role="presentation">
                {heading && <span className="palette-group">{t(heading)}</span>}
                <button
                  id={`palette-${item.id}`}
                  role="option"
                  aria-selected={index === active}
                  data-index={index}
                  className={index === active ? "is-active" : ""}
                  onMouseMove={() => setActive(index)}
                  onClick={item.run}
                  tabIndex={-1}
                >
                  <span className="palette-icon">{item.icon}</span>
                  <span className="palette-label" dir="auto">
                    {item.label}
                  </span>
                  {item.meta && <span className="palette-meta num">{item.meta}</span>}
                  <CornerDownLeft size={15} className="palette-enter" />
                </button>
              </li>
            );
          })}
          {!items.length && <li className="palette-empty">{t("Nothing matches that yet.")}</li>}
        </ul>
        <div className="palette-foot">
          <span>
            <span className="kbd">↑</span>
            <span className="kbd">↓</span> {t("to move")}
          </span>
          <span>
            <span className="kbd">↵</span> {t("to open")}
          </span>
        </div>
      </div>
    </div>
  );
}

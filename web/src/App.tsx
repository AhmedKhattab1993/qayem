import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ArrowRight, Bookmark, Building2, Calculator, Check, Compass, Landmark, Rows3, Scale, Search, X } from "lucide-react";
import Home from "./pages/Home";
import Evaluate from "./pages/Evaluate";
import Units from "./pages/Units";
import UnitPage from "./pages/Unit";
import Compounds from "./pages/Compounds";
import CompoundPage from "./pages/Compound";
import Developers from "./pages/Developers";
import DeveloperPage from "./pages/Developer";
import Compare from "./pages/Compare";
import Watchlist from "./pages/Watchlist";
import Methodology from "./pages/Methodology";
import { CommandPalette } from "./components/CommandPalette";
import { Brand, Mark } from "./components/Brand";
import { useStore } from "./store";
import { api, date, number } from "./lib";
import { getLanguage, setLanguage, t, type Language } from "./locale";
import type { Overview } from "./types";

const nav = [
  { to: "/evaluate", label: "Evaluate a unit", short: "Evaluate", icon: Calculator },
  { to: "/compounds", label: "Compounds", short: "Compounds", icon: Building2 },
  { to: "/developers", label: "Developers", short: "Developers", icon: Landmark },
  { to: "/units", label: "Units", short: "Units", icon: Rows3 },
  { to: "/methodology", label: "Methodology", short: "Methodology", icon: Compass },
];
const titles: [RegExp, string][] = [
  [/^\/$/, "Resale fair value"],
  [/^\/evaluate/, "Evaluate a unit"],
  [/^\/units\/\d+/, "Unit valuation"],
  [/^\/units/, "Units"],
  [/^\/compounds\/.+/, "Compound"],
  [/^\/compounds/, "Compounds"],
  [/^\/developers\/.+/, "Developer"],
  [/^\/developers/, "Developers"],
  [/^\/compare/, "Compare"],
  [/^\/watchlist/, "Watchlist"],
  [/^\/methodology/, "Methodology"],
];

export default function App() {
  const { watch, compare, message, toast } = useStore();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [language, setCurrentLanguage] = useState<Language>(getLanguage);
  const [palette, setPalette] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  setLanguage(language);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<Overview>("/overview", controller.signal)
      .then(setOverview)
      .catch((cause) => cause.name !== "AbortError" && setError(cause.message));
    return () => controller.abort();
  }, [retryKey]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [location.pathname]);
  useEffect(() => {
    const title = titles.find(([pattern]) => pattern.test(location.pathname))?.[1] ?? "Off the map";
    document.title = `${t(title)} — ${t("Qayem")}`;
  }, [location.pathname, language]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => toast(""), 4200);
    return () => clearTimeout(timer);
  }, [message, toast]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const typing = (event.target as HTMLElement)?.closest?.("input, textarea, select, [contenteditable]");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((open) => !open);
      } else if (event.key === "/" && !typing) {
        event.preventDefault();
        setPalette(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const toggleLanguage = useCallback(() => setCurrentLanguage((current) => (current === "ar" ? "en" : "ar")), []);
  const closePalette = useCallback(() => setPalette(false), []);
  const onDark = location.pathname === "/" && !scrolled;
  const counts: Record<string, number> = { "/watchlist": watch.length, "/compare": compare.length };
  const retry = () => setRetryKey((k) => k + 1);

  return (
    <>
      <a className="skip-link" href="#main">
        {t("Skip to content")}
      </a>
      <header className={`nav${onDark ? " nav-dark" : ""}${scrolled ? " nav-scrolled" : ""}`}>
        <div className="nav-inner">
          <Brand />
          <nav className="nav-links" aria-label={t("Main navigation")}>
            {nav.map(({ to, label }) => (
              <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "is-active" : "")}>
                {t(label)}
              </NavLink>
            ))}
          </nav>
          <div className="nav-tools">
            <button className="nav-search" onClick={() => setPalette(true)} aria-label={t("Search Qayem")}>
              <Search size={16} />
              <span>{t("Search")}</span>
              <span className="kbd">⌘K</span>
            </button>
            {(
              [
                ["/watchlist", "Watchlist", Bookmark],
                ["/compare", "Compare", Scale],
              ] as const
            ).map(([to, label, Icon]) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `nav-icon${isActive ? " is-active" : ""}`}
                aria-label={`${t(label)}${counts[to] ? ` (${number(counts[to])})` : ""}`}
                title={t(label)}
              >
                <Icon size={18} />
                {counts[to] > 0 && <span className="nav-badge num">{number(counts[to])}</span>}
              </NavLink>
            ))}
            <button
              type="button"
              className="nav-lang"
              lang={language === "ar" ? "en" : "ar"}
              aria-label={language === "ar" ? "Switch to English" : "التبديل إلى العربية"}
              onClick={toggleLanguage}
            >
              {language === "ar" ? "EN" : "ع"}
            </button>
          </div>
        </div>
      </header>

      <main id="main" key={language}>
        <Routes>
          <Route path="/" element={<Home data={overview} error={error} retry={retry} />} />
          <Route path="/evaluate" element={<Evaluate />} />
          <Route path="/units" element={<Units />} />
          <Route path="/units/:id" element={<UnitPage />} />
          <Route path="/compounds" element={<Compounds />} />
          <Route path="/compounds/:key" element={<CompoundPage overview={overview} />} />
          <Route path="/developers" element={<Developers />} />
          <Route path="/developers/:key" element={<DeveloperPage overview={overview} />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/watchlist" element={<Watchlist overview={overview} />} />
          <Route path="/methodology" element={<Methodology overview={overview} error={error} retry={retry} />} />
          <Route
            path="*"
            element={
              <div className="page lost page-enter">
                <span className="lost-compass" aria-hidden="true">
                  <Compass size={54} strokeWidth={1.1} />
                </span>
                <h1 className="display">{t("A little off the map")}</h1>
                <p>{t("That page isn’t here.")}</p>
                <Link to="/evaluate" className="btn btn-ink">
                  {t("Evaluate a unit")} <ArrowRight size={16} className="flip-rtl" />
                </Link>
              </div>
            }
          />
        </Routes>
      </main>

      <footer className="footer" key={`f-${language}`}>
        <div className="page footer-inner">
          <div className="footer-brand">
            <Mark size={46} />
            <p className="display">
              {t("What is it")} <em>{t("really worth?")}</em>
            </p>
            <span>{t("A fair-value layer for Egypt’s resale property market.")}</span>
          </div>
          <nav className="footer-links" aria-label={t("Footer")}>
            {[...nav, { to: "/watchlist", label: "Watchlist" }, { to: "/compare", label: "Compare" }].map((item) => (
              <Link key={item.to} to={item.to}>
                {t(item.label)}
              </Link>
            ))}
          </nav>
          <div className="footer-meta">
            <span className="live-dot" />
            <span>
              {t("Last observed")} <b className="num">{overview ? date(overview.last_updated) : "—"}</b>
            </span>
            <p>
              {t(
                "Fair values are estimates built from published asking prices, not appraisals or completed sales. Confirm every detail with the seller and the developer.",
              )}
            </p>
          </div>
        </div>
        <div className="footer-word" aria-hidden="true">
          قيّم
        </div>
      </footer>

      <nav className="tabbar" aria-label={t("Quick navigation")} key={`t-${language}`}>
        {[...nav.slice(0, 4), { to: "/watchlist", short: "Watchlist", icon: Bookmark }].map(({ to, short, icon: Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "is-active" : "")}>
            <span className="tabbar-icon">
              <Icon size={20} />
              {counts[to] > 0 && <span className="nav-badge num">{number(counts[to])}</span>}
            </span>
            {t(short)}
          </NavLink>
        ))}
      </nav>

      {message && (
        <div className="toast" role="status">
          <Check size={16} />
          <span>{t(message)}</span>
          <button aria-label={t("Dismiss notification")} onClick={() => toast("")}>
            <X size={14} />
          </button>
        </div>
      )}

      {palette && <CommandPalette onClose={closePalette} onToggleLanguage={toggleLanguage} />}
    </>
  );
}

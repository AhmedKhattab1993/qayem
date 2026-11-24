import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ArrowRight, BarChart3, Bookmark, BookOpen, Building2, Check, Map as MapIcon, Menu, Ruler, Scale, Search, X } from "lucide-react";
import Home from "./pages/Home";
import Evaluate from "./pages/Evaluate";
import Compounds from "./pages/Compounds";
import CompoundPage from "./pages/Compound";
import Developers from "./pages/Developers";
import DeveloperPage from "./pages/Developer";
import Compare from "./pages/Compare";
import Watchlist from "./pages/Watchlist";
import Methodology from "./pages/Methodology";
import DistrictPage from "./pages/District";
import Districts from "./pages/Districts";
import Privacy from "./pages/Privacy";
import { Loading } from "./components/States";
import { CURRENCIES, CurrencyContext, chosenCurrency, getCurrency, rateOf, setCurrency, setRates, type Currency } from "./currency";
import { track } from "./track";
import { keepsServerHead, serverTitle } from "./head";
import { CommandPalette } from "./components/CommandPalette";
import { Brand } from "./components/Brand";
import { useStore } from "./store";
import { api, date, number } from "./lib";
import { getLanguage, setLanguage, t, type Language } from "./locale";
import type { Overview } from "./types";

// The newer pages load on first visit, so the main bundle stays the size it was.
const MapPage = lazy(() => import("./pages/Map"));
const IndexPage = lazy(() => import("./pages/Index"));
const Articles = lazy(() => import("./pages/Articles").then((m) => ({ default: m.Articles })));
const ArticlePage = lazy(() => import("./pages/Articles").then((m) => ({ default: m.ArticlePage })));
const Terms = lazy(() => import("./pages/Terms").then((m) => ({ default: m.Terms })));
const Corrections = lazy(() => import("./pages/Terms").then((m) => ({ default: m.Corrections })));
const DealCheck = lazy(() => import("./pages/DealCheck"));

const nav = [
  { to: "/map", label: "Price map", short: "Map", icon: MapIcon },
  { to: "/districts", label: "Price guide", short: "Guide", icon: Building2 },
  { to: "/index", label: "Qayem Index", short: "Index", icon: BarChart3 },
  { to: "/articles", label: "Articles", short: "Articles", icon: BookOpen },
];
/** The guide is one section with three doors: a district, a compound or a developer. */
const guidePaths = ["/districts", "/compounds", "/developers"];
const footerGroups: { title: string; links: { to: string; label: string }[] }[] = [
  {
    title: "Prices",
    links: [
      { to: "/map", label: "Price map" },
      { to: "/districts", label: "Districts" },
      { to: "/compounds", label: "Compounds" },
      { to: "/developers", label: "Developers" },
    ],
  },
  {
    title: "Tools",
    links: [
      { to: "/evaluate", label: "Check a price" },
      { to: "/deal-check", label: "Free deal check" },
      { to: "/compare", label: "Compare" },
      { to: "/watchlist", label: "Watchlist" },
    ],
  },
  {
    title: "Read",
    links: [
      { to: "/index", label: "Qayem Index" },
      { to: "/articles", label: "Articles" },
      { to: "/methodology", label: "Methodology" },
    ],
  },
  {
    title: "About Qayem",
    links: [
      { to: "/terms", label: "Terms of use" },
      { to: "/corrections", label: "Corrections and takedowns" },
      { to: "/privacy", label: "Privacy" },
    ],
  },
];
const titles: [RegExp, string][] = [
  [/^\/$/, "Egypt property price guide"],
  [/^\/evaluate/, "Check a price"],
  [/^\/compounds\/.+/, "Compound"],
  [/^\/compounds/, "Compounds"],
  [/^\/developers\/.+/, "Developer"],
  [/^\/developers/, "Developers"],
  [/^\/compare/, "Compare"],
  [/^\/watchlist/, "Watchlist"],
  [/^\/methodology/, "Methodology"],
  [/^\/districts\/.+/, "District"],
  [/^\/districts/, "Districts"],
  [/^\/privacy/, "Privacy"],
  [/^\/map/, "Price map"],
  [/^\/index/, "Qayem Index"],
  [/^\/articles\/.+/, "Article"],
  [/^\/articles/, "Articles"],
  [/^\/terms/, "Terms of use"],
  [/^\/corrections/, "Corrections and takedowns"],
  [/^\/deal-check/, "Free deal check"],
];

export default function App() {
  const { watch, compare, message, toast } = useStore();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [language, setCurrentLanguage] = useState<Language>(getLanguage);
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [currency, setCurrentCurrency] = useState<Currency>(chosenCurrency);
  const location = useLocation();
  setLanguage(language);
  // Money is formatted by plain functions: they read the rates and the choice from the currency module.
  setRates(overview?.rates);
  setCurrency(currency);
  const shown = getCurrency();
  const currencies = CURRENCIES.filter((code) => rateOf(code));

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
    setMenu(false);
    track("pageview");
  }, [location.pathname]);
  useEffect(() => {
    const title = titles.find(([pattern]) => pattern.test(location.pathname))?.[1] ?? "Off the map";
    document.title = keepsServerHead(language) ? serverTitle : `${t(title)} — ${t("Qayem")}`;
  }, [location.pathname, language]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.classList.toggle("menu-open", menu);
    return () => document.body.classList.remove("menu-open");
  }, [menu]);

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
      } else if (event.key === "Escape") {
        setMenu(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const toggleLanguage = useCallback(() => setCurrentLanguage((current) => (current === "ar" ? "en" : "ar")), []);
  const changeCurrency = useCallback((next: Currency) => setCurrentCurrency(next), []);
  const closePalette = useCallback(() => setPalette(false), []);
  const onHero = location.pathname === "/" && !scrolled && !menu;
  const counts: Record<string, number> = { "/watchlist": watch.length, "/compare": compare.length };
  const retry = () => setRetryKey((k) => k + 1);
  const inGuide = guidePaths.some((path) => location.pathname.startsWith(path));
  const active = (to: string, isActive: boolean) => (isActive || (to === "/districts" && inGuide) ? "is-active" : "");
  const currencySwitch = (className: string) =>
    currencies.length > 1 && (
      <label className={className} title={t("Show prices in")}>
        <span className="sr-only">{t("Show prices in")}</span>
        <select value={shown} onChange={(event) => changeCurrency(event.target.value as Currency)}>
          {currencies.map((code) => (
            <option key={code} value={code}>
              {t(code)}
            </option>
          ))}
        </select>
      </label>
    );

  return (
    <CurrencyContext.Provider value={{ currency: shown, currencies, change: changeCurrency }}>
      <a className="skip-link" href="#main">
        {t("Skip to content")}
      </a>
      <header className={`nav${onHero ? " nav-on-hero" : ""}${scrolled ? " nav-scrolled" : ""}`}>
        <div className="nav-inner">
          <Brand />
          <nav className="nav-links" aria-label={t("Main navigation")}>
            {nav.map(({ to, label }) => (
              <NavLink key={to} to={to} className={({ isActive }) => active(to, isActive)}>
                {t(label)}
              </NavLink>
            ))}
          </nav>
          <div className="nav-tools">
            <button className="nav-search" onClick={() => setPalette(true)} aria-label={t("Search Qayem")}>
              <Search size={16} />
              <span>{t("Search a district or compound")}</span>
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
                className={({ isActive }) => `nav-icon nav-wide${isActive ? " is-active" : ""}`}
                aria-label={`${t(label)}${counts[to] ? ` (${number(counts[to])})` : ""}`}
                title={t(label)}
              >
                <Icon size={18} />
                {counts[to] > 0 && <span className="nav-badge num">{number(counts[to])}</span>}
              </NavLink>
            ))}
            {currencySwitch("nav-currency nav-wide")}
            <button
              type="button"
              className="nav-lang"
              lang={language === "ar" ? "en" : "ar"}
              aria-label={language === "ar" ? "Switch to English" : "التبديل إلى العربية"}
              onClick={toggleLanguage}
            >
              {language === "ar" ? "EN" : "ع"}
            </button>
            <Link to="/evaluate" className="btn btn-sm btn-primary nav-cta nav-wide">
              <Ruler size={15} /> {t("Check a price")}
            </Link>
            <button
              type="button"
              className="nav-icon nav-menu"
              aria-expanded={menu}
              aria-controls="site-menu"
              aria-label={t(menu ? "Close menu" : "Open menu")}
              onClick={() => setMenu((open) => !open)}
            >
              {menu ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>

      {menu && (
        <div className="menu" id="site-menu" key={`m-${language}`}>
          <nav className="page menu-inner" aria-label={t("All pages")}>
            <Link to="/evaluate" className="btn btn-primary btn-block">
              <Ruler size={16} /> {t("Check a price")}
            </Link>
            {footerGroups.map((group) => (
              <div key={group.title} className="menu-group">
                <span className="eyebrow">{t(group.title)}</span>
                <ul>
                  {group.links.map((item) => (
                    <li key={item.to}>
                      <Link to={item.to} onClick={() => setMenu(false)}>
                        {t(item.label)}
                        <ArrowRight size={16} className="flip-rtl" />
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {currencies.length > 1 && (
              <div className="menu-group">
                <span className="eyebrow">{t("Show prices in")}</span>
                <div className="segmented" role="group" aria-label={t("Show prices in")}>
                  {currencies.map((code) => (
                    <button key={code} type="button" aria-pressed={shown === code} onClick={() => changeCurrency(code)}>
                      {t(code)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </nav>
        </div>
      )}

      {shown !== "EGP" && overview?.rates && (
        <div className="rate-bar" role="status">
          <p className="page num">
            {t("Prices in {currency} at the Central Bank of Egypt rate of {day}: 1 {currency} = {rate}.", {
              currency: t(shown),
              day: date(overview.rates.day),
              rate: `${number(rateOf(shown), 2)} ${t("EGP")}`,
            })}{" "}
            <button type="button" className="link-button" onClick={() => changeCurrency("EGP")}>
              {t("Show in EGP")}
            </button>
          </p>
        </div>
      )}

      <main id="main" key={language}>
        <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Home data={overview} error={error} retry={retry} />} />
          <Route path="/evaluate" element={<Evaluate />} />
          <Route path="/compounds" element={<Compounds />} />
          <Route path="/compounds/:key" element={<CompoundPage overview={overview} />} />
          <Route path="/developers" element={<Developers />} />
          <Route path="/developers/:key" element={<DeveloperPage overview={overview} />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/watchlist" element={<Watchlist overview={overview} />} />
          <Route path="/methodology" element={<Methodology overview={overview} error={error} retry={retry} />} />
          <Route path="/districts" element={<Districts />} />
          <Route path="/districts/:key" element={<DistrictPage overview={overview} />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/map" element={<MapPage overview={overview} />} />
          <Route path="/index" element={<IndexPage overview={overview} />} />
          <Route path="/index/:month" element={<IndexPage overview={overview} />} />
          <Route path="/articles" element={<Articles />} />
          <Route path="/articles/:slug" element={<ArticlePage />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/corrections" element={<Corrections />} />
          <Route path="/deal-check" element={<DealCheck />} />
          <Route
            path="*"
            element={
              <div className="page lost page-enter">
                <span className="lost-tiles" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                  <i />
                </span>
                <h1 className="display">{t("A little off the map")}</h1>
                <p>{t("That page isn’t here.")}</p>
                <Link to="/map" className="btn btn-primary">
                  {t("Open the price map")} <ArrowRight size={16} className="flip-rtl" />
                </Link>
              </div>
            }
          />
        </Routes>
        </Suspense>
      </main>

      <footer className="footer" key={`f-${language}`}>
        <div className="footer-ramp" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
          <i />
          <i />
        </div>
        <div className="page footer-inner">
          <div className="footer-brand">
            <Brand />
            <p className="display">{t("The price of a square metre, anywhere in Egypt.")}</p>
            <span>{t("Egypt’s property price guide: asking prices per m² by district and compound, and resale against the developer.")}</span>
          </div>
          <nav className="footer-links" aria-label={t("Footer")}>
            {footerGroups.map((group) => (
              <div key={group.title}>
                <span className="footer-title">{t(group.title)}</span>
                {group.links.map((item) => (
                  <Link key={item.to} to={item.to}>
                    {t(item.label)}
                  </Link>
                ))}
              </div>
            ))}
          </nav>
        </div>
        <div className="page footer-meta">
          <span className="footer-observed">
            <span className="live-dot" />
            {t("Last observed")} <b className="num">{overview ? date(overview.last_updated) : "—"}</b>
          </span>
          <p>
            {t(
              "Comparisons use published listing and developer list prices, not appraisals or completed sales. Confirm every detail with the seller and the developer.",
            )}
          </p>
        </div>
      </footer>

      <nav className="tabbar" aria-label={t("Quick navigation")} key={`t-${language}`}>
        {(
          [
            ["/map", "Map", MapIcon],
            ["/districts", "Guide", Building2],
            ["/evaluate", "Check", Ruler],
            ["/index", "Index", BarChart3],
            ["/watchlist", "Saved", Bookmark],
          ] as const
        ).map(([to, short, Icon]) => (
          <NavLink key={to} to={to} className={({ isActive }) => `${active(to, isActive)}${to === "/evaluate" ? " tabbar-main" : ""}`}>
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

      {palette && (
        <CommandPalette
          onClose={closePalette}
          onToggleLanguage={toggleLanguage}
          currencies={currencies.length > 1 ? currencies : []}
          currency={shown}
          onCurrency={changeCurrency}
        />
      )}
    </CurrencyContext.Provider>
  );
}

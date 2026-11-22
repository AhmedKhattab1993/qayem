import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, List, Map as MapIcon, X } from "lucide-react";
import { classLabel, money, monthLabel, nameOf, number, periodLabel, signed, tone, useApi } from "../lib";
import { getLanguage, t } from "../locale";
import { useCurrency } from "../currency";
import { ErrorState, Loading } from "../components/States";
import { ConfidenceBadge, NoSalePrices, RateNote, confidenceRules, resaleVsNewText } from "../components/Guide";
import type { MapFeature, MapHexFeature } from "../components/MapCanvas";
import { GAP_BREAKS, GAP_COLOURS, NO_DATA, PRICE_COLOURS, colourFor, priceBreaks, rowFor, valueOf, type Measure } from "../mapScale";
import type { GuideRow, MapData, MapDistrict, Overview, PropertyClass } from "../types";

const MapCanvas = lazy(() => import("../components/MapCanvas"));
type Outlines = GeoJSON.FeatureCollection<GeoJSON.Geometry, Record<string, unknown>>;
const CLASSES: PropertyClass[] = ["apartment", "house", "chalet"];
const DELIVERIES = ["", "ready", "under_2y", "later"] as const;
const BEDROOMS = ["", "1", "2", "3", "4+"] as const;
const BUDGETS = [
  { value: "", label: "Any budget" },
  { value: "5000000", label: "Up to 5M EGP" },
  { value: "10000000", label: "Up to 10M EGP" },
  { value: "15000000", label: "Up to 15M EGP" },
  { value: "25000000", label: "Up to 25M EGP" },
] as const;

function districtRow(district: MapDistrict, cls: PropertyClass, delivery: string): GuideRow | null {
  const base = rowFor(district.classes, null, cls);
  if (!delivery) return base;
  const sub = district.deliveries?.[cls]?.[delivery];
  if (!sub) return null;
  return {
    class: cls,
    count: sub.count,
    confidence: sub.confidence,
    single_source: sub.confidence === "indicative",
    median_ppm: sub.median_ppm,
    p25_ppm: sub.p25_ppm,
    p75_ppm: sub.p75_ppm,
    median_cash_ppm: null,
    median_price: sub.median_price,
    resale_vs_new: sub.resale_vs_new,
    sources: base?.sources ?? [],
    developer_ppm: base?.developer_ppm ?? null,
  };
}

/** The district outlines are a static file; without it the map shows a dot per district. */
function useOutlines() {
  const [outlines, setOutlines] = useState<Outlines | null>(null);
  useEffect(() => {
    let live = true;
    fetch("/map/districts.geojson")
      .then((response) => (response.ok && response.headers.get("content-type")?.includes("json") !== false ? response.json() : null))
      .then((value) => live && value?.type === "FeatureCollection" && setOutlines(value))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  return outlines;
}

function Legend({ measure, breaks }: { measure: Measure; breaks: number[] }) {
  const colours = measure === "price" ? PRICE_COLOURS.slice(0, breaks.length + 1) : GAP_COLOURS;
  const cuts = measure === "price" ? breaks : GAP_BREAKS;
  const label = (index: number) =>
    measure === "price"
      ? index === 0
        ? t("under {value}", { value: money(cuts[0], true) })
        : index >= cuts.length
          ? t("{value} and over", { value: money(cuts[cuts.length - 1], true) })
          : `${money(cuts[index - 1], true)} – ${money(cuts[index], true)}`
      : index === 0
        ? t("resale {value} or more cheaper", { value: signed(cuts[0]) })
        : index >= cuts.length
          ? t("resale {value} or more dearer", { value: signed(cuts[cuts.length - 1]) })
          : `${signed(cuts[index - 1])} – ${signed(cuts[index])}`;
  return (
    <div className="map-legend" aria-label={t("Legend")}>
      <strong>{t(measure === "price" ? "Asking price per m²" : "Resale vs buying new")}</strong>
      <ul>
        {colours.map((colour, index) => (
          <li key={colour} className="num">
            <i style={{ background: colour }} aria-hidden="true" />
            {label(index)}
          </li>
        ))}
        <li>
          <i style={{ background: NO_DATA }} aria-hidden="true" />
          {t("Too few listings")}
        </li>
      </ul>
    </div>
  );
}

type Selection = { kind: "district" | "compound"; key: string };

function SummaryCard({
  name,
  row,
  to,
  onClose,
  meta,
}: {
  name: string;
  row: GuideRow | null;
  to: string;
  onClose: () => void;
  meta?: string;
}) {
  const gap = resaleVsNewText(row?.resale_vs_new);
  return (
    <aside className="map-card" aria-live="polite" aria-label={name}>
      <div className="map-card-head">
        <div>
          <h2 dir="auto">{name}</h2>
          {meta && <small>{meta}</small>}
        </div>
        <button type="button" className="btn btn-sm btn-icon btn-ghost" onClick={onClose} aria-label={t("Close")}>
          <X size={16} />
        </button>
      </div>
      {row ? (
        <>
          <p className="map-card-figure num">
            <strong>{money(row.median_ppm)}</strong> <small>/ {t("m²")}</small>
          </p>
          <p className="muted">{t("Median asking price, {kind}", { kind: classLabel(row.class) })}</p>
          <dl className="map-card-facts">
            <div>
              <dt>{t("Middle half / m²")}</dt>
              <dd className="num">
                {money(row.p25_ppm, true)} – {money(row.p75_ppm, true)}
              </dd>
            </div>
            <div>
              <dt>{t("Listings")}</dt>
              <dd className="num">{number(row.count)}</dd>
            </div>
            <div>
              <dt>{t("Confidence")}</dt>
              <dd>
                <ConfidenceBadge confidence={row.confidence} />
              </dd>
            </div>
            {row.resale_vs_new != null && (
              <div>
                <dt>{t("Resale vs new")}</dt>
                <dd className={`num ${tone(row.resale_vs_new)}`}>{signed(row.resale_vs_new)}</dd>
              </div>
            )}
          </dl>
          {gap && <p className="fineprint">{gap}</p>}
        </>
      ) : (
        <p className="muted">{t("Too few listings of this type here to publish a figure.")}</p>
      )}
      <Link className="btn btn-sm btn-ink" to={to}>
        {t("Open the price guide")} <ArrowUpRight size={15} className="flip-rtl" />
      </Link>
    </aside>
  );
}

export default function MapPage({ overview }: { overview: Overview | null }) {
  const [params, setParams] = useSearchParams();
  const { data, error, retry } = useApi<MapData>("/map");
  const outlines = useOutlines();
  const { currency, currencies, change } = useCurrency();
  const cls = (CLASSES as string[]).includes(params.get("type") ?? "") ? (params.get("type") as PropertyClass) : "apartment";
  const measure: Measure = params.get("show") === "gap" ? "gap" : "price";
  const delivery = (DELIVERIES as readonly string[]).includes(params.get("delivery") ?? "") ? (params.get("delivery") ?? "") : "";
  const beds = (BEDROOMS as readonly string[]).includes(params.get("beds") ?? "") ? (params.get("beds") ?? "") : "";
  const budget = Number(params.get("budget") ?? "") || 0;
  const showGrid = params.get("grid") !== "0";
  const focus = params.get("focus");
  const [selected, setSelected] = useState<Selection | null>(focus ? { kind: "district", key: focus } : null);
  const [view, setView] = useState<"map" | "list">("map");
  const [mapProblem, setMapProblem] = useState<"" | "tiles" | "webgl">("");
  const language = getLanguage();

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) value ? next.set(key, value) : next.delete(key);
    setParams(next, { replace: true });
  };

  const districts = useMemo(() => {
    const all = data?.districts ?? [];
    const filtered = all.filter((d) => {
      const row = districtRow(d, cls, delivery);
      if (beds && !(d.bedrooms?.[beds] ?? 0)) return false;
      if (budget && (!row || row.median_price > budget)) return false;
      return true;
    });
    return [...filtered].sort(
      (a, b) => (districtRow(b, cls, delivery)?.count ?? 0) - (districtRow(a, cls, delivery)?.count ?? 0) || b.listings - a.listings,
    );
  }, [data, cls, delivery, beds, budget]);

  const compounds = useMemo(() => {
    const all = data?.compounds ?? [];
    return all.filter((c) => {
      if (c.lat == null || c.lon == null) return false;
      const row = rowFor(c.classes ?? (c.headline ? [c.headline] : []), c.headline, cls);
      if (beds && !(c.bedrooms?.[beds] ?? 0)) return false;
      if (delivery === "ready" && (c.ready_share ?? 0) < 0.25) return false;
      if (budget && (!row || row.median_price > budget)) return false;
      return true;
    });
  }, [data, cls, delivery, beds, budget]);

  const breaks = useMemo(
    () =>
      priceBreaks([
        ...districts.map((d) => districtRow(d, cls, delivery)?.median_ppm ?? NaN),
        ...compounds.map((c) => rowFor(c.classes ?? (c.headline ? [c.headline] : []), c.headline, cls)?.median_ppm ?? NaN),
      ]),
    [districts, compounds, cls, delivery],
  );
  const features = useMemo<MapFeature[]>(() => {
    if (!data) return [];
    const short = (value: number | null) =>
      value == null ? "" : measure === "price" ? money(value, true) : signed(value);
    return [
      ...districts.map((d) => {
        const value = valueOf(districtRow(d, cls, delivery), measure);
        const name = nameOf(d)!;
        return {
          key: d.key,
          kind: "district" as const,
          label: value == null ? name : `${name}\n${short(value)}`,
          colour: colourFor(value, measure, breaks),
          lat: d.lat,
          lon: d.lon,
        };
      }),
      ...compounds.map((c) => {
        const row = rowFor(c.classes ?? (c.headline ? [c.headline] : []), c.headline, cls);
        return {
          key: c.key,
          kind: "compound" as const,
          label: nameOf(c)!,
          colour: colourFor(valueOf(row, measure), measure, breaks),
          lat: c.lat,
          lon: c.lon,
          size: c.listings,
        };
      }),
    ];
    // The currency changes the labels' figures.
  }, [data, districts, compounds, cls, delivery, measure, breaks, currency, language]);

  const hexFeatures = useMemo<MapHexFeature[]>(() => {
    if (!data?.hexes || measure !== "price" || !showGrid) return [];
    return data.hexes
      .filter((h) => h.class === cls)
      .map((h) => ({
        id: h.id,
        colour: colourFor(h.median_ppm, "price", breaks),
        count: h.count,
        median_ppm: h.median_ppm,
        ring: h.ring,
      }));
  }, [data, cls, measure, showGrid, breaks]);

  const card = useMemo(() => {
    if (!selected || !data) return null;
    if (selected.kind === "district") {
      const district = data.districts.find((d) => d.key === selected.key);
      if (!district) return null;
      return {
        name: nameOf(district)!,
        row: districtRow(district, cls, delivery),
        to: `/districts/${encodeURIComponent(district.key)}`,
        meta: t("{n} listings", { n: number(district.listings), count: district.listings }),
      };
    }
    const compound = data.compounds.find((c) => c.key === selected.key);
    if (!compound) return null;
    const district = data.districts.find((d) => d.key === compound.district);
    return {
      name: nameOf(compound)!,
      row: rowFor(compound.classes ?? (compound.headline ? [compound.headline] : []), compound.headline, cls),
      to: `/compounds/${encodeURIComponent(compound.key)}`,
      meta: district ? nameOf(district) : undefined,
    };
  }, [selected, data, cls, delivery, currency, language]);

  if (error)
    return (
      <div className="page">
        <ErrorState message={error} retry={retry} />
      </div>
    );
  if (!data) return <Loading />;
  const month = monthLabel(data.month);
  const top = districts.find((d) => rowFor(d.classes, null, cls));
  const topRow = top ? rowFor(top.classes, null, cls) : null;

  return (
    <div className="map-page page-enter">
      <header className="page-head map-head">
        <div className="page">
          <span className="eyebrow">{t("Price map")}</span>
          <h1 className="display">{t("Egypt’s asking prices, district by district")}</h1>
          <p className="lede">
            {top && topRow
              ? t("{month}: asking prices per m² from {n} listings across {d} districts. In {place}, the busiest market, {kind} ask about {ppm} per m².", {
                  month,
                  n: number(data.districts.reduce((sum, d) => sum + d.listings, 0)),
                  d: number(data.districts.length),
                  place: nameOf(top),
                  kind: classLabel(topRow.class),
                  ppm: money(topRow.median_ppm),
                })
              : t("{month}: asking prices per m² by district and compound.", { month })}
          </p>
          <div className="map-toolbar" role="group" aria-label={t("Map filters")}>
            <div className="segmented" role="group" aria-label={t("Unit type")}>
              {CLASSES.map((value) => (
                <button key={value} type="button" aria-pressed={cls === value} onClick={() => update({ type: value === "apartment" ? "" : value })}>
                  {classLabel(value)}
                </button>
              ))}
            </div>
            <div className="segmented" role="group" aria-label={t("Colour by")}>
              <button type="button" aria-pressed={measure === "price"} onClick={() => update({ show: "" })}>
                {t("Price per m²")}
              </button>
              <button type="button" aria-pressed={measure === "gap"} onClick={() => update({ show: "gap" })}>
                {t("Resale vs new")}
              </button>
            </div>
            <label className="map-select">
              <span className="sr-only">{t("Delivery")}</span>
              <select aria-label={t("Delivery")} value={delivery} onChange={(event) => update({ delivery: event.target.value })}>
                <option value="">{t("Any delivery")}</option>
                <option value="ready">{t("Ready now")}</option>
                <option value="under_2y">{t("Within 2 years")}</option>
                <option value="later">{t("In 2 years or more")}</option>
              </select>
            </label>
            <label className="map-select">
              <span className="sr-only">{t("Bedrooms")}</span>
              <select aria-label={t("Bedrooms")} value={beds} onChange={(event) => update({ beds: event.target.value })}>
                <option value="">{t("Any bedrooms")}</option>
                <option value="1">{t("1 bedroom")}</option>
                <option value="2">{t("2 bedrooms")}</option>
                <option value="3">{t("3 bedrooms")}</option>
                <option value="4+">{t("4+ bedrooms")}</option>
              </select>
            </label>
            <label className="map-select">
              <span className="sr-only">{t("Budget")}</span>
              <select aria-label={t("Budget")} value={budget ? String(budget) : ""} onChange={(event) => update({ budget: event.target.value })}>
                {BUDGETS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {t(item.label)}
                  </option>
                ))}
              </select>
            </label>
            {measure === "price" && (data.hexes?.length ?? 0) > 0 && (
              <button
                type="button"
                className="btn btn-sm"
                aria-pressed={showGrid}
                onClick={() => update({ grid: showGrid ? "0" : "" })}
              >
                {t(showGrid ? "Price grid: on" : "Price grid: off")}
              </button>
            )}
            {currencies.length > 1 && (
              <div className="segmented map-currency" role="group" aria-label={t("Show prices in")}>
                {currencies.map((code) => (
                  <button key={code} type="button" aria-pressed={currency === code} onClick={() => change(code)}>
                    {t(code)}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              className="btn btn-sm map-view-toggle"
              aria-pressed={view === "list"}
              onClick={() => setView((current) => (current === "map" ? "list" : "map"))}
            >
              {view === "map" ? <List size={15} /> : <MapIcon size={15} />} {t(view === "map" ? "Show the list" : "Show the map")}
            </button>
          </div>
        </div>
      </header>

      <section className={`map-shell${view === "list" ? " is-list" : ""}`} aria-label={t("Price map")}>
        {mapProblem === "webgl" ? (
          <p className="map-fallback">{t("This browser cannot draw the map. The same figures are in the table below.")}</p>
        ) : (
          <Suspense fallback={<div className="map-canvas map-loading" aria-hidden="true" />}>
            <MapCanvas
              features={features}
              outlines={outlines}
              hexes={hexFeatures}
              language={language}
              selected={selected?.kind === "district" ? selected.key : null}
              focus={focus}
              label={t("Map of asking prices per m² by district")}
              onSelect={(kind, key) => setSelected({ kind, key })}
              onError={(problem) => setMapProblem((current) => (current === "webgl" ? current : problem))}
            />
          </Suspense>
        )}
        {mapProblem === "tiles" && (
          <p className="map-warning" role="status">
            {t("The background map did not load. The districts and their figures are still shown.")}
          </p>
        )}
        <Legend measure={measure} breaks={breaks} />
        {card && <SummaryCard {...card} onClose={() => setSelected(null)} />}
        <p className="map-credit" dir="ltr">
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            © OpenStreetMap contributors
          </a>{" "}
          ·{" "}
          <a href="https://protomaps.com" target="_blank" rel="noreferrer">
            Protomaps
          </a>{" "}
          · MapLibre
        </p>
      </section>

      <div className="page">
        <section className="section-tight" id="map-table" aria-labelledby="map-table-heading">
          <div className="section-row">
            <div>
              <span className="eyebrow">{t("The same figures, as a table")}</span>
              <h2 id="map-table-heading" className="display">
                {t("{kind}: asking price per m² by district, {month}", { kind: classLabel(cls), month })}
              </h2>
            </div>
            <Link className="link-arrow" to="/index">
              {t("The Qayem Index")} <ArrowUpRight size={16} className="flip-rtl" />
            </Link>
          </div>
          <div className="ledger-frame">
            <div className="ledger stack row-link guide-ledger">
              <table>
                <caption className="sr-only">{t("Asking prices per m² by district")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("District")}</th>
                    <th scope="col">{t("Asking / m²")}</th>
                    <th scope="col">{t("Middle half / m²")}</th>
                    <th scope="col">{t("Typical price")}</th>
                    <th scope="col">{t("Resale vs new")}</th>
                    <th scope="col">{t("Listings")}</th>
                    <th scope="col">{t("Confidence")}</th>
                  </tr>
                </thead>
                <tbody>
                  {districts.map((district) => {
                    const row = districtRow(district, cls, delivery);
                    return (
                      <tr key={district.key}>
                        <th scope="row">
                          <Link className="ledger-title" to={`/districts/${encodeURIComponent(district.key)}`}>
                            <strong dir="auto">{nameOf(district)}</strong>
                            <small className="num">{t("{n} listings", { n: number(district.listings), count: district.listings })}</small>
                          </Link>
                        </th>
                        <td data-label={t("Asking / m²")} className="num ledger-strong">
                          {money(row?.median_ppm, true)}
                        </td>
                        <td data-label={t("Middle half / m²")} className="num">
                          {row ? `${money(row.p25_ppm, true)} – ${money(row.p75_ppm, true)}` : "—"}
                        </td>
                        <td data-label={t("Typical price")} className="num">
                          {money(row?.median_price, true)}
                        </td>
                        <td data-label={t("Resale vs new")} className={`num ${tone(row?.resale_vs_new)}`}>
                          {signed(row?.resale_vs_new)}
                        </td>
                        <td data-label={t("Listings")} className="num">
                          {number(row?.count ?? 0)}
                        </td>
                        <td data-label={t("Confidence")}>{row ? <ConfidenceBadge confidence={row.confidence} /> : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <p className="fineprint">
            {t("Asking prices of listings seen {period}, duplicates removed. Resale vs new compares resale listings with the developer’s current price for the same type, in today’s money.", {
              period: periodLabel(data.period),
            })}{" "}
            {confidenceRules(overview?.guide?.rules)}
          </p>
          <NoSalePrices />
          <RateNote />
        </section>
      </div>
    </div>
  );
}

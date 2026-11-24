/** The price map itself: MapLibre GL with the Protomaps basemap from one PMTiles file, and Qayem's layers.
 * Loaded only on the map page (React.lazy), so the library never weighs on other pages. */
import { useEffect, useRef } from "react";
import maplibregl, { type GeoJSONSource, type LayerSpecification, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { layers as basemapLayers, namedFlavor } from "@protomaps/basemaps";

/** @mapbox/mapbox-gl-rtl-text 0.3.0, copied into public/map (the package exports only its ES module). */
const RTL_PLUGIN = "/map/mapbox-gl-rtl-text-0.3.0.js";

export interface MapFeature {
  key: string;
  kind: "district" | "compound";
  label: string;
  colour: string;
  lat: number;
  lon: number;
  /** Compounds: listings, for the dot's size. */
  size?: number;
}

/** The glyph ranges kept in public/map/fonts: Latin and Arabic (see its README). */
const GLYPH_RANGES = new Set(["0-255", "256-511", "8192-8447", "1536-1791", "64256-64511", "64512-64767", "64768-65023", "65024-65279"]);

let protocolAdded = false;
function setup() {
  if (!protocolAdded) {
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    // Labels across the border use other scripts (Hebrew, Tifinagh…): those ranges get no glyphs instead of a 404.
    maplibregl.addProtocol("qayem-glyphs", async (params, abort) => {
      const match = /^qayem-glyphs:\/\/(.+)\/(\d+-\d+)$/.exec(params.url);
      if (!match || !GLYPH_RANGES.has(match[2])) return { data: new ArrayBuffer(0) };
      const response = await fetch(`/map/fonts/${match[1]}/${match[2]}.pbf`, { signal: abort.signal });
      return { data: response.ok ? await response.arrayBuffer() : new ArrayBuffer(0) };
    });
    protocolAdded = true;
  }
  // Arabic labels need shaping; the plugin is fetched only when a right-to-left label appears.
  if (maplibregl.getRTLTextPluginStatus() === "unavailable") maplibregl.setRTLTextPlugin(RTL_PLUGIN, true).catch(() => {});
}

/** The white basemap (the price colours are the only colour on the map), trimmed to what needs no sprite sheet and only the two self-hosted fonts. */
function baseStyle(language: "ar" | "en"): StyleSpecification {
  const origin = window.location.origin;
  const skip = new Set(["pois", "roads_shields", "roads_oneway", "address_label"]);
  const layers = basemapLayers("protomaps", namedFlavor("white"), { lang: language })
    .filter((layer) => !skip.has(layer.id))
    .map((layer) => {
      const copy = JSON.parse(JSON.stringify(layer).split('"Noto Sans Italic"').join('"Noto Sans Regular"')) as LayerSpecification;
      if (copy.type === "symbol" && copy.layout && "icon-image" in copy.layout) delete copy.layout["icon-image"];
      // The sea is the palest lapis, so the coast reads at a glance.
      if (copy.id === "water" && copy.type === "fill") copy.paint = { ...copy.paint, "fill-color": "#dde4f3" };
      return copy;
    });
  return {
    version: 8,
    glyphs: "qayem-glyphs://{fontstack}/{range}",
    sources: {
      protomaps: { type: "vector", url: `pmtiles://${origin}/tiles/egypt.pmtiles` },
    },
    layers,
  };
}

/** Where the figures are: mostly Cairo and the north coast, so not all of Egypt's desert. */
function boundsOf(features: MapFeature[]): [[number, number], [number, number]] {
  const places = features.filter((f) => f.kind === "district");
  if (!places.length)
    return [
      [24.7, 22],
      [36.9, 31.7],
    ];
  const lons = places.map((f) => f.lon);
  const lats = places.map((f) => f.lat);
  return [
    [Math.min(...lons) - 0.3, Math.min(...lats) - 0.3],
    [Math.max(...lons) + 0.3, Math.max(...lats) + 0.3],
  ];
}

type Collection = GeoJSON.FeatureCollection<GeoJSON.Geometry, Record<string, unknown>>;

function districtShapes(outlines: Collection | null, features: MapFeature[]): Collection {
  const byKey = new Map(features.filter((f) => f.kind === "district").map((f) => [f.key, f]));
  return {
    type: "FeatureCollection",
    features: (outlines?.features ?? []).flatMap((shape) => {
      const key = String(shape.properties?.key ?? shape.id ?? "");
      const feature = byKey.get(key);
      return feature ? [{ ...shape, id: undefined, properties: { key, colour: feature.colour, label: feature.label } }] : [];
    }),
  };
}

const points = (features: MapFeature[], kind: MapFeature["kind"], outlines: Collection | null = null): Collection => {
  const shaped = new Set((outlines?.features ?? []).map((shape) => String(shape.properties?.key ?? shape.id ?? "")));
  return {
    type: "FeatureCollection",
    features: features
      .filter((f) => f.kind === kind)
      .map((f) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [f.lon, f.lat] },
        properties: { key: f.key, colour: f.colour, label: f.label, size: f.size ?? 0, shape: shaped.has(f.key) },
      })),
  };
};

export interface MapHexFeature {
  id: string;
  colour: string;
  count: number;
  median_ppm: number;
  ring: [number, number][];
}

function hexShapes(hexes: MapHexFeature[]): Collection {
  return {
    type: "FeatureCollection",
    features: hexes.map((h) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [h.ring] },
      properties: { id: h.id, colour: h.colour, count: h.count, median_ppm: h.median_ppm },
    })),
  };
}

export default function MapCanvas({
  features,
  outlines,
  hexes = [],
  language,
  selected,
  focus,
  label,
  onSelect,
  onError,
}: {
  features: MapFeature[];
  outlines: Collection | null;
  hexes?: MapHexFeature[];
  language: "ar" | "en";
  selected: string | null;
  focus: string | null;
  label: string;
  onSelect: (kind: MapFeature["kind"], key: string) => void;
  onError: (problem: "tiles" | "webgl") => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const latest = useRef({ features, outlines, hexes, onSelect, onError });
  latest.current = { features, outlines, hexes, onSelect, onError };

  useEffect(() => {
    if (!box.current) return;
    setup();
    let instance: maplibregl.Map;
    try {
      instance = new maplibregl.Map({
        container: box.current,
        style: baseStyle(language),
        bounds: boundsOf(features),
        fitBoundsOptions: { padding: 24 },
        maxBounds: [
          [20, 18],
          [40, 34],
        ],
        minZoom: 4,
        maxZoom: 15,
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
        cooperativeGestures: false,
      });
    } catch {
      onError("webgl");
      return;
    }
    map.current = instance;
    instance.touchZoomRotate.disableRotation();
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), language === "ar" ? "bottom-left" : "bottom-right");
    // A listener on "error" keeps MapLibre from logging; a missing tile file must not break the page.
    instance.on("error", (event) => {
      const message = String((event as { error?: Error }).error?.message ?? "");
      if (/pmtiles|tiles|magic|fetch|404|glyph|range/i.test(message) || (event as { sourceId?: string }).sourceId === "protomaps") {
        latest.current.onError("tiles");
        // Without the basemap, a plain stone ground reads better than the basemap's grey.
        if (instance.getLayer("background")) instance.setPaintProperty("background", "background-color", "#eceef3");
      }
    });
    instance.on("load", () => {
      const { features: current, outlines: shapes, hexes: cells } = latest.current;
      instance.addSource("districts", { type: "geojson", data: districtShapes(shapes, current) });
      instance.addSource("hexes", { type: "geojson", data: hexShapes(cells) });
      instance.addSource("district-points", { type: "geojson", data: points(current, "district", shapes) });
      instance.addSource("compounds", { type: "geojson", data: points(current, "compound") });
      instance.addLayer({
        id: "district-fill",
        type: "fill",
        source: "districts",
        paint: { "fill-color": ["get", "colour"], "fill-opacity": 0.62 },
      });
      instance.addLayer({
        id: "hex-fill",
        type: "fill",
        source: "hexes",
        minzoom: 9,
        paint: { "fill-color": ["get", "colour"], "fill-opacity": 0.58 },
      });
      instance.addLayer({
        id: "hex-line",
        type: "line",
        source: "hexes",
        minzoom: 9,
        paint: { "line-color": "#ffffff", "line-opacity": 0.65, "line-width": 1 },
      });
      instance.addLayer({
        id: "district-line",
        type: "line",
        source: "districts",
        paint: { "line-color": "#132a8f", "line-opacity": 0.45, "line-width": 1 },
      });
      instance.addLayer({
        id: "district-selected",
        type: "line",
        source: "districts",
        filter: ["==", ["get", "key"], ""],
        paint: { "line-color": "#0b1020", "line-width": 2.5 },
      });
      // At country zoom an outline is a speck, so every district is also a dot; closer in, only those without one.
      const dotOpacity = (full: number) =>
        ["interpolate", ["linear"], ["zoom"], 7, full, 9, ["case", ["get", "shape"], 0, full]] as unknown as number;
      instance.addLayer({
        id: "district-dot",
        type: "circle",
        source: "district-points",
        maxzoom: 12,
        paint: {
          "circle-color": ["get", "colour"],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 5, 9, 8],
          "circle-stroke-color": "#0b1020",
          "circle-stroke-width": 1,
          "circle-opacity": dotOpacity(0.95),
          "circle-stroke-opacity": dotOpacity(0.7),
        },
      });
      instance.addLayer({
        id: "compound-dot",
        type: "circle",
        source: "compounds",
        minzoom: 8,
        paint: {
          "circle-color": ["get", "colour"],
          "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "size"]], 0, 4, 10, 8, 30, 16],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      instance.addLayer({
        id: "district-label",
        type: "symbol",
        source: "district-points",
        maxzoom: 11,
        layout: {
          "text-field": ["get", "label"],
          "text-font": ["Noto Sans Medium"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 5, 11, 10, 14],
          "text-max-width": 9,
          "text-allow-overlap": false,
        },
        paint: { "text-color": "#0b1020", "text-halo-color": "#ffffff", "text-halo-width": 1.6 },
      });
      instance.addLayer({
        id: "compound-label",
        type: "symbol",
        source: "compounds",
        minzoom: 11,
        layout: { "text-field": ["get", "label"], "text-font": ["Noto Sans Regular"], "text-size": 12, "text-offset": [0, 1.3] },
        paint: { "text-color": "#2a3149", "text-halo-color": "#ffffff", "text-halo-width": 1.4 },
      });
      for (const layer of ["district-fill", "district-dot", "compound-dot"]) {
        instance.on("mouseenter", layer, () => (instance.getCanvas().style.cursor = "pointer"));
        instance.on("mouseleave", layer, () => (instance.getCanvas().style.cursor = ""));
      }
      instance.on("click", (event) => {
        const hit = instance.queryRenderedFeatures(event.point, { layers: ["compound-dot", "district-dot", "district-fill"] })[0];
        const key = hit?.properties?.key;
        if (key) latest.current.onSelect(hit.layer.id === "compound-dot" ? "compound" : "district", String(key));
      });
      ready.current = true;
      instance.fire("qayem:data");
    });
    return () => {
      ready.current = false;
      map.current = null;
      instance.remove();
    };
    // The language changes the basemap's labels: a new map is simpler than restyling.
  }, [language]);

  // New colours (class, measure or currency changed) go to the same sources.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      (instance.getSource("districts") as GeoJSONSource | undefined)?.setData(districtShapes(outlines, features));
      (instance.getSource("hexes") as GeoJSONSource | undefined)?.setData(hexShapes(hexes));
      (instance.getSource("district-points") as GeoJSONSource | undefined)?.setData(points(features, "district", outlines));
      (instance.getSource("compounds") as GeoJSONSource | undefined)?.setData(points(features, "compound"));
    };
    if (ready.current) apply();
    else instance.once("qayem:data", apply);
  }, [features, outlines, hexes]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => instance.setFilter("district-selected", ["==", ["get", "key"], selected ?? ""]);
    if (ready.current) apply();
    else instance.once("qayem:data", apply);
  }, [selected]);

  useEffect(() => {
    const instance = map.current;
    const target = focus ? features.find((f) => f.key === focus) : null;
    if (!instance || !target) return;
    instance.jumpTo({ center: [target.lon, target.lat], zoom: target.kind === "compound" ? 13 : 10 });
    // Only when the focus itself changes, not on every recolouring.
  }, [focus]);

  return <div ref={box} className="map-canvas" role="region" aria-label={label} />;
}

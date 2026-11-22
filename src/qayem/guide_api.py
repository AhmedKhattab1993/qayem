"""Published shapes of the price guide: per-district segments, the guide summary, the map and the CSV.

The local API (web.py) builds them from the snapshot on request; the cloud export (cloud_export.py)
stores the same documents in D1, so both serve identical JSON.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import io
import json
import math
from pathlib import Path
from statistics import median

from . import guide, market

PLACES = Path(__file__).resolve().parent / "data" / "compound_places.json"
HEX_KM = 1.6  # ~1.6 km hex radius (~H3 res 7): shows price grid only where a cell has ≥5 listings
HEX_MIN_LISTINGS = 5


def load_places() -> dict[str, dict]:
    try:
        return json.loads(PLACES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def segments_by_district(snapshot) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for segment in snapshot.guide.get("segments", []):
        entry = out.setdefault(segment["district"], {"district": segment["district"], "period": snapshot.guide["period"],
                                                     "segments": []})
        entry["segments"].append(segment)
    return out


def summary(snapshot) -> dict:
    """Every district's headline figure, for the guide's landing page and the home page."""
    districts = []
    for key, entry in snapshot.districts.items():
        head = (entry.get("guide") or {}).get("headline")
        if not head:
            continue
        districts.append({"key": key, "name": entry["name"], "name_ar": entry.get("name_ar"), "region": entry.get("region"),
                          "listings": entry.get("listings", 0), "units": entry["units"],
                          "headline": guide._index_row(head)})
    districts.sort(key=lambda d: -d["listings"])
    return {"period": snapshot.guide.get("period"), "counts": snapshot.guide.get("counts"),
            "rules": snapshot.guide.get("rules"), "index_month": snapshot.index.get("month"),
            "regions": {key: {"name": names[0], "name_ar": names[1]} for key, names in market.REGION_NAMES.items()},
            "districts": districts, "moves": snapshot.moves[:20]}


def _hex_bin(lat: float, lon: float, radius_km: float = HEX_KM) -> tuple[int, int]:
    """Snap a WGS84 point to a flat-top axial hexagonal grid (q, r) in local km coordinates."""
    km_y = lat * 111.32
    km_x = lon * 111.32 * math.cos(math.radians(30.0))  # Egypt's central latitude
    q = (2 / 3 * km_x) / radius_km
    r = (-1 / 3 * km_x + math.sqrt(3) / 3 * km_y) / radius_km
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return int(rq), int(rr)


def _hex_polygon(q: int, r: int, radius_km: float = HEX_KM) -> tuple[float, float, list[list[float]]]:
    """Center (lat, lon) and closed GeoJSON ring for axial hex (q, r)."""
    cos30 = math.cos(math.radians(30.0))
    cx = radius_km * 1.5 * q
    cy = radius_km * math.sqrt(3) * (r + q / 2)
    ring = []
    for corner in range(7):
        angle = math.radians(60 * (corner % 6))
        px = cx + radius_km * math.cos(angle)
        py = cy + radius_km * math.sin(angle)
        ring.append([round(px / (111.32 * cos30), 5), round(py / 111.32, 5)])
    return round(cy / 111.32, 5), round(cx / (111.32 * cos30), 5), ring


def _bedrooms_by(items: list[dict], key_fn) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in items:
        key = key_fn(item)
        beds = item.get("bedrooms")
        if key and beds is not None:
            bucket = "4+" if beds >= 4 else str(beds)
            counts[key][bucket] += 1
    return {k: dict(v) for k, v in counts.items()}


def map_payload(snapshot, places: dict[str, dict] | None = None) -> dict:
    """Districts, compounds and ~1.6 km price hexagons (≥5 listings only) with figures and filters.
    District outlines are a static file (/map/districts.geojson); this carries what changes nightly."""
    places = load_places() if places is None else places
    district_beds = _bedrooms_by(snapshot.default, lambda r: guide.slug(r["district"]))
    compound_beds = _bedrooms_by(snapshot.default, lambda r: r.get("compound_key") or "")
    districts = []
    for key, entry in snapshot.districts.items():
        place = market.BY_KEY.get(key)
        head = (entry.get("guide") or {}).get("headline")
        if not place or not head:
            continue
        segs = entry["guide"]["segments"]
        classes = [guide._index_row(s) for s in segs
                   if s["compound"] == "*" and s["size"] == "*" and s["delivery"] == "*" and s.get("finishing", "*") == "*"]
        deliveries = {}
        for s in segs:
            if s["compound"] == "*" and s["size"] == "*" and s["delivery"] != "*" and s.get("finishing", "*") == "*":
                deliveries.setdefault(s["class"], {})[s["delivery"]] = {
                    "median_ppm": s["median_ppm"], "median_price": s["median_price"], "count": s["count"],
                    "p25_ppm": s["p25_ppm"], "p75_ppm": s["p75_ppm"], "confidence": s["confidence"],
                    "resale_vs_new": s["resale_vs_new"],
                }
        districts.append({"key": key, "name": entry["name"], "name_ar": entry.get("name_ar"), "region": place.region,
                          "region_name": market.REGION_NAMES[place.region][0],
                          "region_name_ar": market.REGION_NAMES[place.region][1], "lat": place.lat, "lon": place.lon,
                          "listings": entry.get("listings", 0), "units": entry["units"],
                          "headline": guide._index_row(head), "classes": classes, "deliveries": deliveries,
                          "bedrooms": district_beds.get(key, {})})
    compounds = []
    hex_cells: dict[tuple[int, int, str], list[float]] = defaultdict(list)
    for key, entry in snapshot.compounds.items():
        point = places.get(key)
        head = (entry.get("guide") or {}).get("headline")
        if not point or not head:
            continue
        segs = entry["guide"]["segments"]
        c_classes = [guide._index_row(s) for s in segs
                     if s["size"] == "*" and s["delivery"] == "*" and s.get("finishing", "*") == "*"]
        compounds.append({"key": key, "name": entry["name"], "name_ar": entry.get("name_ar"),
                          "district": entry["district_key"], "lat": point["lat"], "lon": point["lon"],
                          "units": entry["units"], "listings": head["count"], "headline": guide._index_row(head),
                          "classes": c_classes, "ready_share": entry.get("ready_share"),
                          "bedrooms": compound_beds.get(key, {}),
                          "developer": (entry.get("developer") or {}).get("name")})
    # Price grid (hexagons with ≥5 listings, never interpolating sparse areas).
    for item in snapshot.default:
        ckey = item.get("compound_key")
        cls = item.get("class")
        point = places.get(ckey) if ckey else None
        if point and cls:
            q, r = _hex_bin(point["lat"], point["lon"])
            hex_cells[(q, r, cls)].append(item["price_per_m2"])
    hexes = []
    for (q, r, cls), ppms in hex_cells.items():
        if len(ppms) < HEX_MIN_LISTINGS:
            continue
        lat, lon, ring = _hex_polygon(q, r)
        hexes.append({"id": f"{q}:{r}:{cls}", "class": cls, "count": len(ppms),
                      "median_ppm": round(median(ppms), -2), "lat": lat, "lon": lon, "ring": ring})
    hexes.sort(key=lambda h: -h["count"])
    return {"period": snapshot.guide.get("period"), "month": snapshot.index.get("month"),
            "districts": sorted(districts, key=lambda d: -d["listings"]),
            "compounds": sorted(compounds, key=lambda c: -c["listings"]),
            "hexes": hexes,
            "attribution": "© OpenStreetMap contributors", "placed_compounds": len(compounds),
            "compounds_with_figures": sum(1 for c in snapshot.compounds.values() if (c.get("guide") or {}).get("headline"))}


def csv_text(edition: dict) -> str:
    stream = io.StringIO()
    stream.write(f"# {edition['name']} — {edition['label']} (as of {edition['as_of']}). Licence: {edition['licence']}; "
                 f"attribution: {edition['attribution']}. Asking and contract prices from public listings; "
                 f"aggregates only. Method: https://qayem.ai/methodology\n")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(guide.csv_rows(edition))
    return stream.getvalue()

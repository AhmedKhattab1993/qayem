"""Build the map's geography from OpenStreetMap, cached in the repository.

    .venv/bin/python scripts/build-map-data.py districts   # outlines of the market districts (Nominatim)
    .venv/bin/python scripts/build-map-data.py places      # named residential areas in Egypt (Overpass)
    .venv/bin/python scripts/build-map-data.py compounds   # each compound's point: OSM places first, then Nominatim

Writes `web/public/map/districts.geojson` and `src/qayem/data/compound_places.json`.
Data © OpenStreetMap contributors (ODbL); the map credits it. Requests are paced at one per
second with a descriptive User-Agent, as the Nominatim usage policy asks, and every answer is
cached so a rerun only asks for what is missing.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qayem import market  # noqa: E402
from qayem.valuation import fold  # noqa: E402

UA = "Qayem-map-builder/1.0 (+https://qayem.ai)"
CACHE = ROOT / ".artifacts" / "map" / "cache"
DISTRICTS = ROOT / "web" / "public" / "map" / "districts.geojson"
PLACES = ROOT / ".artifacts" / "map" / "osm_places.json"
COMPOUNDS = ROOT / "src" / "qayem" / "data" / "compound_places.json"
client = httpx.Client(timeout=120, headers={"User-Agent": UA, "Accept-Language": "en"})
_last = [0.0]


def polite_get(url: str, params: dict) -> httpx.Response:
    wait = 1.1 - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    response = client.get(url, params=params)
    response.raise_for_status()
    return response


def nominatim(query: str, polygon: bool = False) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (fold(query)[:80] + ("-poly" if polygon else "") + ".json")
    if key.exists():
        return json.loads(key.read_text())
    params = {"q": query, "format": "jsonv2", "limit": 3, "countrycodes": "eg"}
    if polygon:
        params |= {"polygon_geojson": 1, "polygon_threshold": 0.003}
    result = polite_get("https://nominatim.openstreetmap.org/search", params).json()
    key.write_text(json.dumps(result, ensure_ascii=False))
    return result


def km(a_lat, a_lon, b_lat, b_lon) -> float:
    return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(b_lat - a_lat) / 2) ** 2 + math.cos(math.radians(a_lat))
                                          * math.cos(math.radians(b_lat)) * math.sin(math.radians(b_lon - a_lon) / 2) ** 2))


def districts() -> None:
    features = []
    for district in market.DISTRICTS:
        geometry, source = None, "qayem"
        for query in (f"{district.name}, Egypt", f"{district.name_ar}, مصر"):
            for hit in nominatim(query, polygon=True):
                shape = hit.get("geojson") or {}
                south, north, west, east = map(float, hit["boundingbox"])
                near = km(district.lat, district.lon, float(hit["lat"]), float(hit["lon"])) < 40
                if shape.get("type") in ("Polygon", "MultiPolygon") and near and north - south < 1.2 and east - west < 1.5:
                    geometry, source = shape, f"osm:{hit['osm_type']}/{hit['osm_id']}"
                    break
            if geometry:
                break
        if geometry is None:  # no outline in OSM: a small circle around Qayem's own centroid
            radius = 0.03 if district.in_compounds else 0.05
            geometry = {"type": "Polygon", "coordinates": [[
                [round(district.lon + radius * 1.15 * math.cos(a / 24 * 2 * math.pi), 5),
                 round(district.lat + radius * math.sin(a / 24 * 2 * math.pi), 5)] for a in range(25)]]}
        features.append({"type": "Feature", "id": district.key, "geometry": geometry,
                         "properties": {"key": district.key, "name": district.name, "name_ar": district.name_ar,
                                        "region": district.region, "source": source}})
        print(district.key, source)
    DISTRICTS.parent.mkdir(parents=True, exist_ok=True)
    DISTRICTS.write_text(json.dumps({"type": "FeatureCollection", "attribution": "© OpenStreetMap contributors (ODbL)",
                                     "features": features}, ensure_ascii=False, separators=(",", ":")))


def places() -> None:
    """Named residential areas, neighbourhoods and gated compounds across Egypt's populated regions."""
    boxes = ["29.7,30.7,30.35,32.0", "30.6,27.0,31.4,30.2", "29.3,32.2,29.8,32.7", "26.6,33.5,27.6,34.0",
             "27.8,34.2,28.1,34.45", "30.9,31.0,31.6,32.4", "30.4,31.1,30.9,31.6"]
    found: dict[str, dict] = {}
    for box in boxes:
        query = (f'[out:json][timeout:180];(way["name"]["landuse"="residential"]({box});'
                 f'relation["name"]["landuse"="residential"]({box});way["name"]["place"~"neighbourhood|suburb|quarter"]({box});'
                 f'node["name"]["place"~"neighbourhood|suburb|quarter"]({box});way["name"]["residential"="gated"]({box}););out center tags;')
        for attempt in range(4):
            response = client.post("https://overpass-api.de/api/interpreter", data={"data": query})
            if response.status_code < 500 and response.status_code != 429:
                break
            time.sleep(30 * (attempt + 1))
        response.raise_for_status()
        for element in response.json()["elements"]:
            center = element.get("center") or {"lat": element.get("lat"), "lon": element.get("lon")}
            if center.get("lat") is None:
                continue
            tags = element.get("tags", {})
            found[f"{element['type']}/{element['id']}"] = {
                "name": tags.get("name"), "name_en": tags.get("name:en"), "name_ar": tags.get("name:ar"),
                "lat": round(center["lat"], 5), "lon": round(center["lon"], 5)}
        print(box, len(found))
        time.sleep(5)
    PLACES.parent.mkdir(parents=True, exist_ok=True)
    PLACES.write_text(json.dumps(found, ensure_ascii=False))


GENERIC = {"compound", "residence", "residences", "city", "the", "new", "park", "gardens", "hills", "phase",
           "resort", "village", "bay", "coast", "cairo", "october", "zayed", "sokhna", "capital"}
STRIP_WORDS = ("compound", "كمبوند", "قرية", "منتجع", "new cairo", "sheikh zayed", "6th of october",
               "north coast", "ain sokhna", "new capital", "mostakbal city", "october", "ras el hekma")


def _clean_name(value: str) -> str:
    text = value.split("(")[0].strip()
    folded = fold(text)
    for word in STRIP_WORDS:
        folded = folded.replace(fold(word), " ")
    return " ".join(folded.split())


def compounds(max_nominatim: int = 80) -> None:
    from qayem.config import crawled_sources, market_sources
    from qayem.website_data import Catalog
    database = os.environ.get("QAYEM_DB", str(ROOT / ".artifacts" / "development" / "qayem.db"))
    snapshot = Catalog(database, 0, crawled_sources(), market_sources()).snapshot()
    osm = json.loads(PLACES.read_text()) if PLACES.exists() else {}
    names: dict[str, list[tuple[str, dict]]] = {}
    for ref, place in osm.items():
        for name in {place["name"], place["name_en"], place["name_ar"]} - {None}:
            for variant in (fold(name.replace("Compound", "").replace("كمبوند", "")), _clean_name(name)):
                if len(variant) >= 4 and variant not in GENERIC:
                    names.setdefault(variant, []).append((ref, place))
    saved = json.loads(COMPOUNDS.read_text()) if COMPOUNDS.exists() else {}
    # Highest-volume compounds (especially those with published guide headlines) first.
    ranked = sorted(
        snapshot.compounds.items(),
        key=lambda kv: (0 if (kv[1].get("guide") or {}).get("headline") else 1, -kv[1]["units"]),
    )
    searched = 0
    for key, compound in ranked:
        has_head = bool((compound.get("guide") or {}).get("headline"))
        if key in saved or (compound["units"] < 3 and not has_head):
            continue
        district = (market.BY_KEY.get(compound.get("district_key") or "")
                    or market.resolve(compound.get("district"), compound.get("name")))
        if district is None:
            continue
        hit = None
        wanted = [w for w in {
            fold(compound["name"] or ""),
            _clean_name(compound["name"] or ""),
            fold(compound.get("name_ar") or ""),
            _clean_name(compound.get("name_ar") or ""),
        } if len(w) >= 4 and w not in GENERIC]
        radius = 55 if district.key in ("north-coast", "ain-sokhna", "hurghada") else 35
        for name in wanted:
            best = None
            for ref, place in names.get(name, []):
                dist = km(district.lat, district.lon, place["lat"], place["lon"])
                if dist < radius and (best is None or dist < best[0]):
                    best = (dist, ref, place)
            if best:
                _, ref, place = best
                hit = {"lat": place["lat"], "lon": place["lon"], "source": f"osm:{ref}", "match": "name"}
                break
        if hit is None:  # «Mivida» in «Emaar Mivida Compound»: one name contains the other, near the district
            near = [(km(district.lat, district.lon, place["lat"], place["lon"]), ref, place)
                    for folded, entries in names.items() for ref, place in entries
                    if any(len(w) >= 5 and (w in folded or (len(folded) >= 6 and folded in w)) for w in wanted)]
            near = sorted(item for item in near if item[0] < (35 if district.key in ("north-coast", "ain-sokhna") else 22))
            if near:
                _, ref, place = near[0]
                hit = {"lat": place["lat"], "lon": place["lon"], "source": f"osm:{ref}", "match": "contains"}
        if hit is None and (has_head or compound["units"] >= 10) and searched < max_nominatim:
            searched += 1
            base_name = compound["name"].split("(")[0].strip()
            queries = [f"{base_name}, {district.name}, Egypt", f"{base_name} compound, Egypt"]
            if compound.get("name_ar"):
                queries.append(f"{compound['name_ar']}, {district.name_ar}")
            for query in queries:
                try:
                    results = nominatim(query)
                except httpx.HTTPError:
                    continue
                for result in results:
                    lat, lon = float(result["lat"]), float(result["lon"])
                    if km(district.lat, district.lon, lat, lon) < radius and result.get("addresstype") not in (
                            "city", "state", "county", "town", "village", "road"):
                        hit = {"lat": round(lat, 5), "lon": round(lon, 5),
                               "source": f"osm:{result['osm_type']}/{result['osm_id']}", "match": "search"}
                        break
                if hit:
                    break
        if hit:
            saved[key] = {**hit, "name": compound["name"], "district": district.key}
            print(key, hit["match"])
    COMPOUNDS.parent.mkdir(parents=True, exist_ok=True)
    COMPOUNDS.write_text(json.dumps(dict(sorted(saved.items())), ensure_ascii=False, indent=0))
    with_head = sum(1 for c in snapshot.compounds.values() if (c.get("guide") or {}).get("headline"))
    placed_head = sum(1 for k, c in snapshot.compounds.items() if k in saved and (c.get("guide") or {}).get("headline"))
    print("placed", len(saved), "total;", placed_head, "of", with_head, "with guide figures")


if __name__ == "__main__":
    {"districts": districts, "places": places, "compounds": compounds}[sys.argv[1]]()

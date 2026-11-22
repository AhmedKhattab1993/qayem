"""Published shapes of the price guide: per-district segments, the guide summary, the map and the CSV.

The local API (web.py) builds them from the snapshot on request; the cloud export (cloud_export.py)
stores the same documents in D1, so both serve identical JSON.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from . import guide, market

PLACES = Path(__file__).resolve().parent / "data" / "compound_places.json"


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


def map_payload(snapshot, places: dict[str, dict] | None = None) -> dict:
    """Districts and compounds with their figures and positions. Outlines are a static file
    (/map/districts.geojson); this carries what changes nightly."""
    places = load_places() if places is None else places
    districts = []
    for key, entry in snapshot.districts.items():
        place = market.BY_KEY.get(key)
        head = (entry.get("guide") or {}).get("headline")
        if not place or not head:
            continue
        classes = [guide._index_row(s) for s in entry["guide"]["segments"]
                   if s["compound"] == "*" and s["size"] == "*" and s["delivery"] == "*"]
        districts.append({"key": key, "name": entry["name"], "name_ar": entry.get("name_ar"), "region": place.region,
                          "region_name": market.REGION_NAMES[place.region][0],
                          "region_name_ar": market.REGION_NAMES[place.region][1], "lat": place.lat, "lon": place.lon, "listings": entry.get("listings", 0),
                          "units": entry["units"], "headline": guide._index_row(head), "classes": classes})
    compounds = []
    for key, entry in snapshot.compounds.items():
        point = places.get(key)
        head = (entry.get("guide") or {}).get("headline")
        if not point or not head:
            continue
        compounds.append({"key": key, "name": entry["name"], "name_ar": entry.get("name_ar"),
                          "district": entry["district_key"], "lat": point["lat"], "lon": point["lon"],
                          "units": entry["units"], "listings": head["count"], "headline": guide._index_row(head),
                          "developer": (entry.get("developer") or {}).get("name")})
    return {"period": snapshot.guide.get("period"), "month": snapshot.index.get("month"),
            "districts": sorted(districts, key=lambda d: -d["listings"]),
            "compounds": sorted(compounds, key=lambda c: -c["listings"]),
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

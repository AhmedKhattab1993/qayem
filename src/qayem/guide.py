"""The price guide: market prices per district, compound and segment, from every source in use.

    collect → normalize → resolve names → dedupe → classify → segment → aggregate → label → publish

Rows arrive normalized and with market districts resolved (website_data.py, market.py). Here the
same unit listed on several sites is counted once, each listing is classified, listings are grouped
into segments, and a segment is published only with enough listings and sources behind it, labelled
with its period, count, source mix and a confidence level (docs/STRATEGY.md, 5.3). The monthly Qayem
Index is one named, dated set of these figures.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta
import math
import re
from statistics import median

from . import market
from .valuation import fold, slug

WINDOW_DAYS = 30  # a figure covers the listings observed in the last 30 days
METHOD_VERSION = "2026-11"
# Publication rule: at least 5 listings from at least 2 sources, or 10 from one source ("single source").
MIN_MULTI, MIN_SINGLE = 5, 10
HIGH_MIN = 20  # "high" also needs 20 listings and no source above 80% of them
HIGH_MAX_SHARE = 0.8
DEVELOPER_MIN = 3  # developer listings needed for a "resale against new" figure
# Cross-source duplicates: the same compound or district and type, area within 2%, price within 3%,
# seen within 30 days of each other.
DUP_AREA, DUP_PRICE, DUP_DAYS = 0.02, 0.03, 30
# Which copy of a duplicated unit is kept: the source with the most structured record.
SOURCE_PRIORITY = {"aqarexit": 0, "nawy": 1, "aqarmap": 2, "opensooq": 3, "semsar": 4, "gpm": 5,
                   "coldwellbanker": 6}
SIZE_BANDS = {"apartment": (100, 150, 200), "chalet": (90, 130), "house": (250, 400)}
DELIVERY = {"ready": "ready", "under_1y": "under_2y", "1_2y": "under_2y", "2_3y": "later", "3y_plus": "later"}
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December")
MONTHS_AR = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر",
             "نوفمبر", "ديسمبر")


def size_band(cls: str | None, area: float) -> str | None:
    bounds = SIZE_BANDS.get(cls or "")
    if not bounds:
        return None
    for low, high in zip((0, *bounds), bounds):
        if area < high:
            return f"{low}-{high}" if low else f"<{high}"
    return f"{bounds[-1]}+"


def delivery_group(item: dict) -> str | None:
    return DELIVERY.get((item.get("delivery") or {}).get("bucket") or "")


def classify(item: dict) -> dict:
    """Market (resale, contract transfer or developer sale), seller, payment terms and data quality."""
    source, url = item["source"], item.get("source_url") or ""
    if source in ("nawy_primary",) or re.search(r"/listing/\d+-projects-", url):
        kind, seller = "developer", "developer"
    elif source == "aqarexit":
        kind, seller = "transfer", "owner"
    else:
        kind = "resale"
        seller = "broker" if source in ("nawy", "gpm", "coldwellbanker") else "unknown"
    quality = []
    if item.get("price_is_down_payment"):
        quality.append("down_payment_as_price")
    return {"market": kind, "seller": seller, "terms": item["payment"]["terms"], "quality": quality}


def fresh(items: list[dict], today: date, days: int = WINDOW_DAYS) -> list[dict]:
    start = (today - timedelta(days=days)).isoformat()
    return [item for item in items if (item.get("last_seen_at") or "")[:10] >= start]


def dedupe(items: list[dict]) -> tuple[list[dict], int]:
    """One copy of each unit listed on several sources; the others name the copy kept.

    Returns the kept listings and how many duplicates were dropped. Only listings from different
    sources are matched: two identical units of one development on one site are two units.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in items:
        groups[(item.get("compound_key") or slug(item.get("district")), item.get("class") or item["property_type"])].append(item)
    dropped = 0
    for group in groups.values():
        group.sort(key=lambda r: (SOURCE_PRIORITY.get(r["source"], 9), r["price"], r["id"]))
        kept: list[dict] = []
        prices: list[float] = []  # kept prices, sorted, with their listings
        by_price: list[dict] = []
        for item in group:
            low = item["price"] * (1 - DUP_PRICE)
            match = None
            for other in by_price[bisect_left(prices, low):]:
                if other["price"] > item["price"] * (1 + DUP_PRICE):
                    break
                if (other["source"] != item["source"] and abs(other["area_m2"] / item["area_m2"] - 1) <= DUP_AREA
                        and _days_apart(other, item) <= DUP_DAYS):
                    match = other
                    break
            if match is not None:
                item["duplicate_of"] = match["id"]
                match.setdefault("copies", []).append({"source": item["source"], "id": item["id"]})
                dropped += 1
                continue
            index = bisect_right(prices, item["price"])  # equal prices keep their order: the first copy matches first
            prices.insert(index, item["price"])
            by_price.insert(index, item)
            kept.append(item)
    return [item for item in items if "duplicate_of" not in item], dropped


SUSPECT_LOW, SUSPECT_HIGH = 0.3, 3.5  # price per m² this far from its district's median: a typo or a down payment


def plausible(items: list[dict]) -> tuple[list[dict], int]:
    """Listings whose price per m² is believable for their district and class; the rest are dropped
    as suspect (a down payment listed as the price, a missing zero, a whole building)."""
    groups: dict[tuple, list[float]] = defaultdict(list)
    for item in items:
        groups[(slug(item["district"]), item["class"])].append(item["price_per_m2"])
    medians = {key: median(values) for key, values in groups.items() if len(values) >= MIN_MULTI}
    kept = []
    for item in items:
        typical = medians.get((slug(item["district"]), item["class"]))
        if typical and not SUSPECT_LOW <= item["price_per_m2"] / typical <= SUSPECT_HIGH:
            item.setdefault("market", {}).setdefault("quality", []).append("suspect_price")
            continue
        kept.append(item)
    return kept, len(items) - len(kept)


def _days_apart(a: dict, b: dict) -> int:
    if not a.get("last_seen_at") or not b.get("last_seen_at"):
        return 0
    return abs((date.fromisoformat(a["last_seen_at"][:10]) - date.fromisoformat(b["last_seen_at"][:10])).days)


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _round(value: float | None, digits: int = -1) -> float | None:
    return None if value is None else round(value, digits)


def _cash_ppm(item: dict) -> float | None:
    cash = item["payment"]["cash_equivalent"]
    return cash / item["area_m2"] if cash else None


def source_mix(items: list[dict]) -> list[dict]:
    counts = Counter(item["source"] for item in items)
    total = sum(counts.values())
    from .website_data import SOURCE_NAMES
    return [{"id": s, "name": SOURCE_NAMES.get(s, s.title()), "count": n, "share": round(n / total, 4)}
            for s, n in counts.most_common()]


def confidence(items: list[dict]) -> str | None:
    """high / medium / indicative, or None when the segment is too thin to publish."""
    counts = Counter(item["source"] for item in items)
    total = sum(counts.values())
    if len(counts) >= 2 and total >= MIN_MULTI:
        top = counts.most_common(1)[0][1] / total
        return "high" if total >= HIGH_MIN and top <= HIGH_MAX_SHARE else "medium"
    if total >= MIN_SINGLE:
        return "indicative"
    return None


def stats(items: list[dict], developer: list[dict]) -> dict | None:
    level = confidence(items)
    if level is None:
        return None
    ppm = [r["price_per_m2"] for r in items]
    prices = [r["price"] for r in items]
    cash = [p for r in items if (p := _cash_ppm(r))]
    plans = [r for r in items if r["payment"]["terms"] == "plan"]
    known = [r for r in items if r["payment"]["terms"] in ("plan", "cash")]
    out = {
        "count": len(items), "sources": source_mix(items), "single_source": len({r["source"] for r in items}) == 1,
        "confidence": level, "median_ppm": _round(median(ppm), -2), "p25_ppm": _round(_quantile(ppm, 0.25), -2),
        "p75_ppm": _round(_quantile(ppm, 0.75), -2), "median_cash_ppm": _round(median(cash), -2) if cash else None,
        "median_price": _round(median(prices), -4), "p25_price": _round(_quantile(prices, 0.25), -4),
        "p75_price": _round(_quantile(prices, 0.75), -4), "median_area": round(median(r["area_m2"] for r in items)),
        "plan_share": round(len(plans) / len(known), 4) if known else None,
        "price_cuts": sum(1 for r in items if (r.get("price_change") or {}).get("change", 0) < 0),
        "developer": None, "resale_vs_new": None, "list_price_gap": None,
    }
    if len(developer) >= DEVELOPER_MIN:
        dev_ppm = median(u["price_per_m2"] for u in developer)
        dev_cash = [p for u in developer if (p := _cash_ppm(u))]
        out["developer"] = {"count": len(developer), "median_ppm": _round(dev_ppm, -2),
                            "median_cash_ppm": _round(median(dev_cash), -2) if dev_cash else None}
        out["list_price_gap"] = round(median(ppm) / dev_ppm - 1, 4)
        if dev_cash and cash:
            # in today's money: both sides' instalments discounted the same way (methodology), so a developer's
            # ten-year plan and a resale balance compare on one basis
            out["resale_vs_new"] = round(median(cash) / median(dev_cash) - 1, 4)
    return out


def _compound_of_market(item: dict, names: dict[str, str]) -> str:
    """A market source's compound text («Zed East Compound - ORA») as one of the catalogue's compounds."""
    text = item.get("compound_name") or ""
    head = re.split(r"\s+(?:compound|كمبوند)\b|\s+-\s+", text, maxsplit=1, flags=re.I)[0]
    return names.get(fold(head), "") if head else ""


def build(resale: list[dict], market_items: list[dict], developer: list[dict], compounds: dict[str, dict],
          matched: dict[str, list[dict]], today: date) -> dict:
    """Every published segment, and the counts behind them."""
    names: dict[str, str] = {}
    for key, entry in compounds.items():
        for name in (entry["name"], entry.get("name_ar")):
            if name:
                names.setdefault(fold(name), key)
    pool = []
    outside_catalogue = {id(item) for item in market_items}
    developer = list(developer)
    for item in [*resale, *market_items]:
        if item.get("class") is None:
            continue
        info = classify(item)
        if info["market"] == "developer":
            developer.append(item)
            continue
        if id(item) in outside_catalogue and not item.get("compound_key"):
            item["compound_key"] = _compound_of_market(item, names)
        item["market"] = info
        pool.append(item)
    current, suspect = plausible(fresh(pool, today))
    kept, dropped = dedupe(current)
    developer = [u for u in fresh(developer, today) if u.get("class")]
    developer_by_district: dict[tuple, list[dict]] = defaultdict(list)
    for unit in developer:
        developer_by_district[(slug(unit["district"]), unit["class"])].append(unit)
    developer_by_compound: dict[tuple, list[dict]] = defaultdict(list)
    current_developer = {id(unit) for unit in developer}
    for key, units in matched.items():
        for unit in units:
            if unit.get("class") and id(unit) in current_developer:
                developer_by_compound[(key, unit["class"])].append(unit)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in kept:
        district, cls = slug(item["district"]), item["class"]
        compound = item.get("compound_key") or ""
        size, delivery = size_band(cls, item["area_m2"]), delivery_group(item)
        finish = item.get("finishing_class") or "unknown"
        groups[(district, "*", cls, "*", "*", "*")].append(item)
        if size:
            groups[(district, "*", cls, size, "*", "*")].append(item)
        if delivery:
            groups[(district, "*", cls, "*", delivery, "*")].append(item)
        if finish != "unknown":
            groups[(district, "*", cls, "*", "*", finish)].append(item)
        if compound:
            groups[(district, compound, cls, "*", "*", "*")].append(item)
            if size:
                groups[(district, compound, cls, size, "*", "*")].append(item)
            if finish != "unknown":
                groups[(district, compound, cls, "*", "*", finish)].append(item)
        else:
            groups[(district, "outside", cls, "*", "*", "*")].append(item)
    segments = []
    for (district, compound, cls, size, delivery, finish), items in groups.items():
        if not district:
            continue
        if compound in ("*", "outside"):
            dev = developer_by_district.get((district, cls), []) if compound == "*" else []
        else:
            dev = developer_by_compound.get((compound, cls), [])
        if size != "*":
            dev = [u for u in dev if size_band(cls, u["area_m2"]) == size]
        if finish != "*":
            dev = [u for u in dev if (u.get("finishing_class") or "unknown") == finish]
        figures = stats(items, dev)
        if figures is None:
            continue
        place = market.BY_KEY.get(district)
        entry = compounds.get(compound) if compound not in ("*", "outside") else None
        key_parts = (district, compound, cls, size, delivery) if finish == "*" else (district, compound, cls, size, delivery, finish)
        segments.append({
            "key": "/".join(key_parts),
            "district": district, "district_name": place.name if place else items[0]["district"],
            "district_name_ar": place.name_ar if place else None, "region": place.region if place else None,
            "compound": compound, "compound_name": entry["name"] if entry else None,
            "compound_name_ar": entry.get("name_ar") if entry else None,
            "class": cls, "size": size, "delivery": delivery, "finishing": finish, **figures,
        })
    segments.sort(key=lambda s: (s["district"], s["compound"] != "*", s["compound"], s["class"], s["size"], s["delivery"], s["finishing"]))
    levels = Counter(s["confidence"] for s in segments)
    multi = sum(1 for s in segments if not s["single_source"])
    return {
        "segments": segments, "period": {"start": (today - timedelta(days=WINDOW_DAYS)).isoformat(), "end": today.isoformat(),
                                         "days": WINDOW_DAYS},
        "counts": {"listings": len(current), "kept": len(kept), "duplicates": dropped, "suspect": suspect,
                   "developer_listings": len(developer), "segments": len(segments), "high": levels["high"],
                   "medium": levels["medium"], "indicative": levels["indicative"],
                   "multi_source_share": round(multi / len(segments), 4) if segments else None,
                   "sources": source_mix(kept)},
        "rules": {"min_multi": MIN_MULTI, "min_single": MIN_SINGLE, "high_min": HIGH_MIN,
                  "high_max_share": HIGH_MAX_SHARE, "window_days": WINDOW_DAYS, "duplicate_area": DUP_AREA,
                  "duplicate_price": DUP_PRICE, "duplicate_days": DUP_DAYS, "developer_min": DEVELOPER_MIN,
                  "size_bands": {k: list(v) for k, v in SIZE_BANDS.items()}, "method_version": METHOD_VERSION},
    }


def headline(segments: list[dict]) -> dict | None:
    """The figure a page leads with: apartments where there are enough of them, else the largest class."""
    if not segments:
        return None
    by_class = {s["class"]: s for s in segments}
    return by_class.get("apartment") or max(segments, key=lambda s: s["count"])


def month_label(month: str, lang: str = "en") -> str:
    year, number = month.split("-")
    return f"{(MONTHS_AR if lang == 'ar' else MONTHS_EN)[int(number) - 1]} {year}"


def index(guide: dict, today: date) -> dict:
    """The Qayem Index for the month of `today`: one dated figure set per district and compound."""
    month = today.strftime("%Y-%m")
    tops = [s for s in guide["segments"] if s["size"] == "*" and s["delivery"] == "*" and s.get("finishing", "*") == "*"]
    districts: dict[str, dict] = {}
    compounds: dict[str, dict] = {}
    for segment in tops:
        if segment["compound"] == "*":
            entry = districts.setdefault(segment["district"], {
                "key": segment["district"], "name": segment["district_name"], "name_ar": segment["district_name_ar"],
                "region": segment["region"], "classes": []})
            entry["classes"].append(_index_row(segment))
        elif segment["compound"] != "outside":
            entry = compounds.setdefault(segment["compound"], {
                "key": segment["compound"], "name": segment["compound_name"], "name_ar": segment["compound_name_ar"],
                "district": segment["district"], "district_name": segment["district_name"], "classes": []})
            entry["classes"].append(_index_row(segment))
    for entry in [*districts.values(), *compounds.values()]:
        entry["classes"].sort(key=lambda row: -row["count"])
        entry["count"] = sum(row["count"] for row in entry["classes"])
    return {
        "name": "Qayem Index", "name_ar": "مؤشر قيّم", "month": month, "label": month_label(month),
        "label_ar": month_label(month, "ar"), "period": guide["period"], "as_of": today.isoformat(),
        "provisional": True, "method_version": METHOD_VERSION, "counts": guide["counts"],
        "districts": sorted(districts.values(), key=lambda d: -d["count"]),
        "compounds": sorted(compounds.values(), key=lambda c: -c["count"]),
        "licence": "CC BY 4.0", "attribution": "Qayem Index (qayem.ai)",
    }


def _index_row(segment: dict) -> dict:
    keys = ("class", "count", "confidence", "single_source", "median_ppm", "p25_ppm", "p75_ppm", "median_cash_ppm",
            "median_price", "resale_vs_new", "list_price_gap")
    row = {key: segment[key] for key in keys}
    row["sources"] = [s["id"] for s in segment["sources"]]
    row["developer_ppm"] = segment["developer"]["median_ppm"] if segment["developer"] else None
    return row


def changes(current: dict, previous: dict | None) -> list[dict]:
    """District and compound figures that moved between two index editions (same class, enough data)."""
    if not previous:
        return []
    before = {(kind, entry["key"], row["class"]): row for kind in ("districts", "compounds")
              for entry in previous.get(kind, []) for row in entry["classes"]}
    moves = []
    for kind in ("districts", "compounds"):
        for entry in current.get(kind, []):
            for row in entry["classes"]:
                old = before.get((kind, entry["key"], row["class"]))
                if not old or not old.get("median_ppm") or not row.get("median_ppm"):
                    continue
                if row["confidence"] == "indicative" and old["confidence"] == "indicative":
                    continue
                change = row["median_ppm"] / old["median_ppm"] - 1
                moves.append({"kind": kind[:-1], "key": entry["key"], "name": entry["name"], "name_ar": entry.get("name_ar"),
                              "class": row["class"], "from": old["median_ppm"], "to": row["median_ppm"],
                              "change": round(change, 4), "count": row["count"], "previous_count": old["count"]})
    return sorted(moves, key=lambda m: -abs(m["change"]))


def csv_rows(edition: dict) -> list[list]:
    """The public monthly CSV (aggregates only, CC BY 4.0)."""
    header = ["month", "level", "key", "name", "name_ar", "district", "class", "listings", "confidence",
              "single_source", "median_price_per_m2_egp", "p25_price_per_m2_egp", "p75_price_per_m2_egp",
              "median_cash_today_per_m2_egp", "median_price_egp", "developer_price_per_m2_egp", "resale_vs_new",
              "sources"]
    rows = [header]
    for kind in ("districts", "compounds"):
        for entry in edition.get(kind, []):
            for row in entry["classes"]:
                rows.append([edition["month"], kind[:-1], entry["key"], entry["name"], entry.get("name_ar") or "",
                             entry.get("district", entry["key"]), row["class"], row["count"], row["confidence"],
                             int(row["single_source"]), row["median_ppm"], row["p25_ppm"], row["p75_ppm"],
                             row["median_cash_ppm"] or "", row["median_price"], row["developer_ppm"] or "",
                             "" if row["resale_vs_new"] is None else row["resale_vs_new"], " ".join(row["sources"])])
    return rows

"""Read-only, bounded projections for the public Qayem website.

The website deliberately does not import the ingestion engine. SQLite's read-only
URI and query_only flag enforce the boundary, including when a caller misconfigures
the database path. Raw source payloads and contact columns are never selected.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import unescape
import json
import math
from pathlib import Path
import re
import sqlite3
from statistics import median
from threading import Lock, Thread
import time
from typing import Any, Collection
from urllib.parse import urlsplit

from .valuation import (
    CLASSES, DISCOUNT_RATE, alias_key, canonical_district, delivery_bucket, developer_key, finishing_class, fold,
    majority, payment_terms, slug,
)

SOURCE_NAMES = {
    "nawy": "Nawy", "nawy_primary": "Nawy (developer launches)", "opensooq": "OpenSooq", "aqarmap": "Aqarmap",
    "semsar": "Semsar Masr", "gpm": "GPM", "coldwellbanker": "Coldwell Banker",
    "aqarexit": "AqarExit",
}
# Sources whose absent installment plan means a cash price (structured payment data; AqarExit
# publishes the balance owed, so none owed is a unit paid in full).
CASH_WHEN_NO_PLAN = {"nawy", "nawy_primary", "aqarexit"}
# Developers' current launch units: a benchmark for resale, never resale evidence.
PRIMARY_SOURCES = {"nawy_primary"}
# Sources that transfer a unit at the owner's original contract price, with no premium («بدون أوفر»):
# their price is what the seller paid the developer, in the year the contract was signed.
CONTRACT_PRICE_SOURCES = {"aqarexit"}
TYPE_ALIASES = {
    "apartments": "apartment", "villas": "villa", "chalets": "chalet",
    "retail": "shop", "medical": "clinic", "townhouses": "townhouse",
    "twinhouses": "twinhouse", "twin_house": "twinhouse", "town_house": "townhouse",
    "بنتهاوس": "penthouse", "administrative": "office",
}
MIN_PRICE, MAX_PRICE = 100_000, 200_000_000
MIN_AREA, MAX_AREA = 20, 5_000
HISTORY_READY_DAYS = 56
# Listings not re-observed this long before their source's latest observation are
# hidden: a sampled or budget-limited source must not keep sold units looking active.
UNCONFIRMED_AFTER_DAYS = 14
_EMPTY = {"", "none", "null", "unknown", "n/a", "na", "-", "not specified"}
_PHONE = re.compile(r"(?<!\d)(?:\+?20[\s().-]*)?0?1[0125](?:[\s().-]*\d){8}(?!\d)")
_TAGS = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FIELDS = (
    "id", "source", "url", "title", "property_type", "price", "currency",
    "area_m2", "bedrooms", "bathrooms", "city", "district", "compound",
    "developer", "finishing", "delivery_status", "delivery_date", "is_installment", "down_payment",
    "installment_months", "is_resale", "resale_evidence", "status", "purpose",
    "first_seen_at", "last_seen_at", "images",
)


class CatalogUnavailable(Exception):
    """A missing, unreadable, or incompatible source database."""


def clean_text(value: Any, limit: int = 400) -> str | None:
    if not isinstance(value, str):
        return None
    value = _CONTROL.sub("", _TAGS.sub(" ", unescape(value)))
    value = _PHONE.sub("[contact withheld]", value)
    value = " ".join(value.split()).strip()
    return value[:limit] if value.casefold() not in _EMPTY else None


def number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and minimum <= parsed <= maximum else None


def integer(value: Any, maximum: int) -> int | None:
    parsed = number(value, 0, maximum)
    return int(parsed) if parsed is not None and parsed.is_integer() else None


def boolean(value: Any) -> bool | None:
    return bool(value) if value in (0, 1) and value is not None else None


def photo_urls(value: Any, limit: int = 12) -> list[str]:
    """The listing's photos as the source published them: https links only, at most `limit`."""
    try:
        urls = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return []
    if not isinstance(urls, list):
        return []
    safe = [safe_url(url) for url in urls]
    return list(dict.fromkeys(url for url in safe if url and url.startswith("https://")))[:limit]


def safe_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        return None
    value = value.strip()
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def url_key(value: str | None) -> str | None:
    """Comparable form of a listing URL: host without www, path without trailing slash."""
    if not value:
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/')}".casefold() if host else None


def iso_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def decode_json(value: Any, expected: type) -> Any:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return expected()
    return decoded if isinstance(decoded, expected) else expected()


def contract_year(row: sqlite3.Row) -> int | None:
    value = row["contract_year"] if "contract_year" in row.keys() else None
    year = integer(str(value).strip()[:4], 2100) if value is not None and str(value).strip()[:4].isdigit() else None
    return year if year and year >= 2000 else None


def property_projection(row: sqlite3.Row) -> dict | None:
    """Return eligible sale inventory, with invalid optional fields omitted."""
    price = number(row["price"], MIN_PRICE, MAX_PRICE)
    area = number(row["area_m2"], MIN_AREA, MAX_AREA)
    kind = clean_text(row["property_type"])
    kind = TYPE_ALIASES.get(kind.casefold(), kind.casefold()) if kind else None
    district, compound = clean_text(row["district"]), clean_text(row["compound"])
    if (row["status"] != "active" or row["purpose"] != "sale"
            or (row["currency"] or "").upper() != "EGP"
            or price is None or area is None or not kind or not (district or compound)):
        return None
    down = number(row["down_payment"], 0, price)
    months = integer(row["installment_months"], 360) or None
    # False is the ingestion model's default, including sources that do not
    # publish payment terms. It must not be presented as evidence of cash terms.
    installments = True if boolean(row["is_installment"]) is True else None
    source = clean_text(row["source"], 32) or "unknown"
    delivery_date = row["delivery_date"] if isinstance(row["delivery_date"], str) else None
    return {
        "id": row["id"], "source": source, "source_name": SOURCE_NAMES.get(source, source.title()),
        "source_url": safe_url(row["url"]), "title": clean_text(row["title"], 300),
        "property_type": kind, "class": CLASSES.get(kind), "price": price, "area_m2": area,
        "price_per_m2": round(price / area), "bedrooms": integer(row["bedrooms"], 12),
        "bathrooms": integer(row["bathrooms"], 12),
        "district": canonical_district(district or compound), "compound_name": compound,
        "developer_name": clean_text(row["developer"]), "finishing": clean_text(row["finishing"]),
        "finishing_class": finishing_class(clean_text(row["finishing"])),
        "delivery_status": clean_text(row["delivery_status"]),
        "delivery_date": delivery_date[:10] if delivery_date and re.match(r"\d{4}-\d{2}-\d{2}", delivery_date) else None,
        "installments": installments, "down_payment": down, "installment_months": months,
        "payment": payment_terms(price, down, months, installments, source in CASH_WHEN_NO_PLAN),
        "is_resale": boolean(row["is_resale"]), "resale_evidence": clean_text(row["resale_evidence"]),
        "contract_year": contract_year(row) if source in CONTRACT_PRICE_SOURCES else None,
        "last_seen_at": iso_date(row["last_seen_at"]), "first_seen_at": iso_date(row["first_seen_at"]),
        "images": photo_urls(row["images"]),
    }


# Arabic spellings of large compounds, as they appear on AqarExit and classifieds.
COMPOUND_ALIASES = {slug(arabic): key for arabic, key in {
    "باديا": "badya", "سراي": "sarai", "بارك سنترال": "park-central", "سيليا": "celia", "مدينتي": "madinaty",
    "الرحاب": "el-rehab", "ميفيدا": "mivida", "تاج سيتي": "taj-city", "كايرو فستيفال سيتي": "cairo-festival-city",
    "فيليت": "villette", "زد ايست": "zed-east", "ايست تاون": "eastown", "هاسيندا باي": "hacienda-bay",
    "هاسيندا وايت": "hacienda-white", "ماراسي": "marassi", "مراسي": "marassi", "فوكا باي": "fouka-bay",
    "سولت": "salt", "جيفيرا": "jefaira", "بالم هيلز القاهرة الجديدة": "palm-hills-new-cairo",
    "البوسكو": "il-bosco-city", "البوسكو سيتي": "il-bosco-city", "البوسكو سيتى": "il-bosco-city",
    "هاب تاون": "haptown", "ذا كريست": "the-crest", "كريك تاون": "creektown", "بلوم فيلدز": "bloomfields",
    "سوديك ايست": "sodic-east", "جاردن ليكس": "garden-lakes",
}.items()}

_GENERIC = {"the", "el", "al", "la", "il", "new", "compound", "city", "residence", "residences", "park", "hills",
            "mountain", "view", "palm", "hyde", "project", "phase", "كمبوند", "مشروع"}


def match_compound(key: str, developers: Counter, anchors: set[str], anchor_developers: dict) -> str | None:
    """Established compound (≥5 listings) that `key` is a spelling variant of, within the same developer."""
    plain = re.sub(r"^(كمبوند|compound)-", "", key)
    if COMPOUND_ALIASES.get(plain) in anchors:
        return COMPOUND_ALIASES[plain]
    key = plain
    candidates = [a for a in anchors if not developers or set(developers) & set(anchor_developers[a])]
    flat = key.replace("-", "")
    for anchor in candidates:  # identical ignoring separators: "thebrooks" = "the-brooks"
        if anchor.replace("-", "") == flat:
            return anchor
    prefixed = sorted((a for a in candidates if key.startswith(f"{a}-") or a.startswith(f"{key}-")), key=len)
    if prefixed:
        return prefixed[-1] if key.startswith(f"{prefixed[-1]}-") else prefixed[0]
    if not developers:
        return None
    word = next((w for w in key.split("-") if w not in _GENERIC and len(w) >= 4), None)
    if word is None:
        return None
    same_word = [a for a in candidates if word in a.split("-")]
    return same_word[0] if len(same_word) == 1 else None


def confirmed(item: dict, source_latest: str | None) -> bool:
    if not item["last_seen_at"] or not source_latest:
        return True
    gap = datetime.fromisoformat(source_latest.replace("Z", "+00:00")) - datetime.fromisoformat(
        item["last_seen_at"].replace("Z", "+00:00"))
    return gap.days < UNCONFIRMED_AFTER_DAYS


@dataclass
class Snapshot:
    records: dict[int, dict]
    default: list[dict]
    today: date
    compounds: dict[str, dict]
    developers: dict[str, dict]
    districts: dict[str, dict]
    overview: dict
    catalog: dict
    urls: dict[str, int]
    launches: dict[str, list[dict]]  # the developer's current units per compound key
    peers: dict[tuple[str, str], list[dict]]  # resale units per (compound key, unit type)


def majority_or_none(counter: Counter | None) -> str | None:
    return counter.most_common(1)[0][0] if counter else None


def _median(values: list[float], digits: int = 0) -> float | None:
    return round(median(values), digits) if values else None


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def scope(items: list[dict]) -> dict:
    """Where the numbers come from — shown next to every statistic."""
    counts = Counter(item["source"] for item in items)
    total = sum(counts.values())
    return {"count": total, "sources": [
        {"id": source, "name": SOURCE_NAMES.get(source, source.title()), "count": count, "share": _share(count, total)}
        for source, count in counts.most_common()]}


# --- opportunity: two comparisons, no fair price -------------------------------
#
# Egypt publishes no resale transactions, and AqarExit's prices are the sellers' old contract
# prices, so Qayem does not estimate a "fair price". It compares each unit, in today's money,
# with what can actually be bought now: the developer's current price for a similar unit
# (launch_units) and the similar resale units listed in the same compound (peer_comparison).

PEER_MIN = 4  # other similar units needed before a unit is ranked against them
PEER_AREA_RATIO = 1.5
PEER_LIMIT = 60  # similar units listed on a unit page (the page shows the nearest six until asked)
# A level needs every available comparison to agree: strong means all at least 15% cheaper and
# one at least 25%; good means all at least 5% cheaper and one at least 10%.
STRONG_ALL, STRONG_ONE = -0.15, -0.25
GOOD_ALL, GOOD_ONE = -0.05, -0.10
PRICIER = 0.10
# Too far below everything to be real: most likely a listing error, not a deal.
CHECK_DEVELOPER, CHECK_PEERS = -0.70, -0.60
# A quarter or more below even the cheapest similar unit, on both bases: an outlier to verify first
# (a listing error, or an unusually early contract), not a verdict.
CHECK_BELOW_CHEAPEST = -0.25
LEVELS = ("strong", "good", "in_line", "mixed", "pricier", "check", "unrated")
LEVEL_ORDER = {level: index for index, level in enumerate(LEVELS)}


def peer_groups(records) -> dict[tuple[str, str], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        if record.get("compound_key") and record["payment"]["cash_equivalent"]:
            groups[(record["compound_key"], record["property_type"])].append(record)
    return groups


def similar_units(record: dict, groups: dict[tuple[str, str], list[dict]]) -> list[dict]:
    """Resale units in the same compound, of the same type, within 1.5× the size; the same finishing
    when there are enough of them. Nearest in size first."""
    pool = [p for p in groups.get((record.get("compound_key") or "", record["property_type"]), [])
            if p["id"] != record.get("id")
            and abs(math.log(p["area_m2"] / record["area_m2"])) <= math.log(PEER_AREA_RATIO)]
    same = [p for p in pool if p["finishing_class"] == record["finishing_class"] != "unknown"]
    if len(same) >= PEER_MIN:
        pool = same
    return sorted(pool, key=lambda p: (abs(math.log(p["area_m2"] / record["area_m2"])), p["id"]))


def peer_comparison(record: dict, pool: list[dict]) -> dict | None:
    """Where the unit's cash-today price per m² sits among similar units listed now."""
    cash = record["payment"]["cash_equivalent"]
    if not cash or len(pool) < PEER_MIN:
        return None
    own = cash / record["area_m2"]
    others = [p["payment"]["cash_equivalent"] / p["area_m2"] for p in pool]
    typical, typical_headline = median(others), median(p["price_per_m2"] for p in pool)
    cash_gap, headline_gap = own / typical - 1, record["price_per_m2"] / typical_headline - 1
    cheapest, cheapest_headline = min(others), min(p["price_per_m2"] for p in pool)
    return {"count": len(pool) + 1, "rank": 1 + sum(value < own for value in others),
            "cash_ppm": round(own), "median_cash_ppm": round(typical), "median_headline_ppm": round(typical_headline),
            # the less favourable of the two, as for the developer comparison
            "gap": round(max(cash_gap, headline_gap), 4), "cash_gap": round(cash_gap, 4),
            "headline_gap": round(headline_gap, 4),
            "min_cash_ppm": round(cheapest), "min_headline_ppm": round(cheapest_headline),
            "cheapest_gap": round(max(own / cheapest - 1, record["price_per_m2"] / cheapest_headline - 1), 4),
            "same_finishing": all(p["finishing_class"] == record["finishing_class"] for p in pool)}


def opportunity(record: dict) -> dict:
    """The unit's level from the comparisons that apply to it. Each comparison is made both on the
    listed price and in today's money: it counts as cheaper only if both are, and as pricier only if
    both are. The developer comparison counts only on like-for-like finishing: an unfinished unit is
    not a deal for being unfinished."""
    signals: dict[str, tuple[float, float]] = {}
    launch, peers = record.get("launch"), record.get("peers")
    if launch and launch["same_finishing"]:
        signals["developer"] = (launch["cash_gap"], launch["headline_gap"])
    if peers:
        signals["peers"] = (peers["cash_gap"], peers["headline_gap"])
    if not signals:
        return {"level": "unrated", "score": None, "signals": []}
    cheap = [max(pair) for pair in signals.values()]  # the less favourable basis
    dear = [min(pair) for pair in signals.values()]
    if (launch and "developer" in signals and launch["gap"] <= CHECK_DEVELOPER) or (
            peers and (peers["gap"] <= CHECK_PEERS or peers["cheapest_gap"] <= CHECK_BELOW_CHEAPEST)):
        level = "check"
    elif max(cheap) <= STRONG_ALL and min(cheap) <= STRONG_ONE:
        level = "strong"
    elif max(cheap) <= GOOD_ALL and min(cheap) <= GOOD_ONE:
        level = "good"
    elif min(cheap) <= GOOD_ONE and max(dear) >= PRICIER:
        level = "mixed"
    elif max(dear) >= PRICIER:
        level = "pricier"
    else:
        level = "in_line"
    return {"level": level, "score": round(sum(cheap) / len(cheap), 4), "signals": sorted(signals)}


def opportunity_key(record: dict) -> tuple:
    """Best first. Within a level, a unit checked against both the developer and similar units ranks
    ahead of one checked against only one of them: it has cleared more evidence, not less."""
    rated = record["opportunity"]
    return (LEVEL_ORDER[rated["level"]], -len(rated["signals"]), rated["score"] if rated["score"] is not None else 0,
            record["id"] or 0)


def unknowns(record: dict) -> list[str]:
    """What the comparison could not see for this unit."""
    missing = []
    if record["payment"]["terms"] == "unknown":
        missing.append("payment_terms")
    if record["payment"]["terms"] == "partial":
        missing.append("installment_term")
    if not record.get("compound_key"):
        missing.append("compound")
    if not record.get("developer_key"):
        missing.append("developer")
    if record["finishing_class"] == "unknown":
        missing.append("finishing")
    if record.get("delivery", {}).get("bucket") == "unknown":
        missing.append("delivery")
    # never published by any source today — always unknown
    return missing + ["floor_and_view", "legal_status", "transfer_fee", "maintenance_deposit"]


def public_unit(record: dict, full: bool = False) -> dict:
    keys = ("id", "source", "source_name", "source_url", "title", "property_type", "class", "price", "area_m2",
            "price_per_m2", "bedrooms", "district", "compound", "developer", "finishing_class", "delivery",
            "payment", "launch", "peers", "opportunity", "contract_year", "is_resale")
    extra = ("bathrooms", "finishing", "installments", "down_payment", "installment_months",
             "resale_evidence", "last_seen_at", "unknowns")
    unit = {key: record.get(key) for key in keys + (extra if full else ())}
    images = record.get("images") or []
    unit["photo"] = images[0] if images else None  # lists show the first photo; a unit page shows them all
    if full:
        unit["images"] = images
    return unit


class Catalog:
    """Share sanitized immutable-by-convention projections, never live sessions."""

    def __init__(self, path: str | Path, refresh_seconds: float = 300, sources: Collection[str] | None = None):
        self.path = Path(path).expanduser().resolve()
        # Only these sources are shown and fitted (None: every source); other rows are never read.
        self.sources = tuple(sorted(sources)) if sources is not None else None
        # A crawl commits every few seconds; the model is refitted at most this often.
        self.refresh_seconds = refresh_seconds
        self._lock = Lock()  # guards the fields below; never held while building
        self._build_lock = Lock()  # one build at a time
        self._fingerprint: tuple | None = None
        self._cached: Snapshot | None = None
        self._built_at = 0.0
        self._refreshing = False

    def _signature(self) -> tuple:
        try:
            if not self.path.is_file():
                raise OSError("Not a file")
            files = [self.path, Path(f"{self.path}-wal")]
            return tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in files)
        except OSError as exc:
            raise CatalogUnavailable("Qayem dataset is unavailable. Set QAYEM_DB to an existing Qayem database.") from exc

    def connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            return connection
        except sqlite3.Error as exc:
            raise CatalogUnavailable("Qayem dataset cannot be opened. Check the QAYEM_DB path and read permissions.") from exc

    def warm(self) -> None:
        """Build the first snapshot ahead of the first visitor; failures surface on real requests."""
        try:
            self.snapshot()
        except CatalogUnavailable:
            pass

    def snapshot(self) -> Snapshot:
        signature = self._signature()
        with self._lock:
            cached = self._cached
            if cached is not None and (
                    signature == self._fingerprint or time.monotonic() - self._built_at < self.refresh_seconds):
                return cached
            # A refit takes seconds on the full dataset: keep serving the last fit while it rebuilds.
            # refresh_seconds <= 0 means "always current" and rebuilds inline.
            if cached is not None and self.refresh_seconds > 0:
                if not self._refreshing:
                    self._refreshing = True
                    Thread(target=self._refresh, name="qayem-catalog-refresh", daemon=True).start()
                return cached
        return self._build()

    def _refresh(self) -> None:
        try:
            self._build()
        except CatalogUnavailable:
            with self._lock:
                self._built_at = time.monotonic()  # retry after the next refresh window, not on every request
        finally:
            with self._lock:
                self._refreshing = False

    def _build(self) -> Snapshot:
        with self._build_lock:
            signature = self._signature()
            with self._lock:
                if self._cached is not None and signature == self._fingerprint:
                    return self._cached  # a concurrent build already covers this state
            try:
                with closing(self.connect()) as connection:
                    present = {row[1] for row in connection.execute("PRAGMA table_info(properties)")}
                    columns = ", ".join(name if name in present else f"NULL AS {name}" for name in _FIELDS)
                    # one scalar from the payload, never the payload itself
                    columns += (", CASE WHEN json_valid(raw) THEN json_extract(raw, '$.contract_year') END AS contract_year"
                                if "raw" in present else ", NULL AS contract_year")
                    only = f" WHERE source IN ({', '.join('?' * len(self.sources))})" if self.sources is not None else ""
                    params = self.sources or ()
                    rows = connection.execute(f"SELECT {columns} FROM properties{only}", params).fetchall()
                    runs = connection.execute(
                        f"SELECT source, status, started_at, id FROM parse_runs{only} ORDER BY started_at, id", params
                    ).fetchall()
                    moves = connection.execute(
                        "SELECT property_id, changed_fields FROM property_versions "
                        "WHERE change_type IN ('updated', 'relisted') AND changed_fields LIKE '%delivery_date%'"
                    ).fetchall()
                    hidden = unreliable_price_ids(connection)
                    aliases = entity_aliases(connection)
                snapshot = build_snapshot(rows, runs, moves, hidden, aliases)
            except sqlite3.Error as exc:
                raise CatalogUnavailable("Qayem dataset is not ready. Point QAYEM_DB to a database containing the Qayem tables.") from exc
            with self._lock:
                self._cached, self._fingerprint, self._built_at = snapshot, signature, time.monotonic()
            return snapshot

    def description(self, property_id: int) -> str | None:
        try:
            with closing(self.connect()) as connection:
                row = connection.execute("SELECT description FROM properties WHERE id = ?", (property_id,)).fetchone()
        except sqlite3.Error as exc:
            raise CatalogUnavailable("Qayem listing details are temporarily unavailable. Please retry.") from exc
        return clean_text(row[0], 10_000) if row else None


def unreliable_price_ids(connection: sqlite3.Connection) -> set[int]:
    """Listings whose description shows the stored price is only the down payment."""
    present = {row[1] for row in connection.execute("PRAGMA table_info(property_enrichments)")}
    if "flags" not in present:
        return set()
    return {row[0] for row in connection.execute(
        "SELECT property_id FROM property_enrichments WHERE flags LIKE '%\"price_is_down_payment\"%'")}


def entity_aliases(connection: sqlite3.Connection) -> dict[str, dict]:
    """Canonical compound and developer per spelling pair (entities.py); only confident answers."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'entity_aliases'").fetchone():
        return {}
    rows = connection.execute(
        "SELECT key, kind, compound, compound_ar, developer, developer_ar, reference, confidence FROM entity_aliases "
        "WHERE status = 'done' AND confidence IN ('high', 'medium')").fetchall()
    return {row["key"]: dict(row) for row in rows}


def apply_aliases(records: list[dict], aliases: dict[str, dict]) -> dict[str, str]:
    """Replace free-text compound and developer spellings with their canonical names.

    Spellings of one compound share its Nawy reference, or else its canonical name and
    developer; each such compound gets one display name. Returns the Nawy reference key
    of each compound → the compound's key, which is how launch units find their compound.
    """
    names: dict[tuple, Counter] = defaultdict(Counter)
    for record in records:
        alias = aliases.get(alias_key(record["compound_name"], record["developer_name"]) or "")
        if alias is None:
            continue
        if alias["kind"] == "not_compound":
            if alias["confidence"] == "high":  # a district or a description, not a development
                record["compound_name"] = None
            continue
        if not alias["compound"]:
            continue
        developer = alias["developer"] or record["developer_name"]
        identity = (("reference", alias["reference"]) if alias["reference"]
                    else ("name", fold(alias["compound"]), developer_key(developer)))
        record["_identity"], record["developer_name"] = identity, developer
        record["developer_name_ar"] = alias["developer_ar"]
        record["compound_name_ar"] = alias["compound_ar"]
        names[identity][alias["compound"]] += 1
    display: dict[tuple, str] = {}
    taken: dict[str, tuple] = {}
    for identity, counter in sorted(names.items(), key=lambda pair: -sum(pair[1].values())):
        name = counter.most_common(1)[0][0]
        if taken.get(slug(name), identity) != identity:  # two compounds marketed under one name
            developer = next((r["developer_name"] for r in records if r.get("_identity") == identity), None)
            name = f"{name} ({developer})" if developer else f"{name} ({identity[-1]})"
        taken[slug(name)] = identity
        display[identity] = name
    for record in records:
        if identity := record.pop("_identity", None):
            record["compound_name"] = display[identity]
    return {slug(identity[1]): slug(name) for identity, name in display.items() if identity[0] == "reference"}


def build_snapshot(rows: list, runs: list, moves: list, hidden: set[int] = frozenset(),
                   aliases: dict[str, dict] | None = None) -> Snapshot:
    latest_by_source: dict[str, str] = {}
    for row in rows:
        if seen := iso_date(row["last_seen_at"]):
            latest_by_source[row["source"]] = max(seen, latest_by_source.get(row["source"], seen))
    projected = [item for row in rows if row["id"] not in hidden
                 and (item := property_projection(row)) is not None
                 and confirmed(item, latest_by_source.get(row["source"]))]
    launches = [item for item in projected if item["source"] in PRIMARY_SOURCES]
    records = {item["id"]: item for item in projected if item["source"] not in PRIMARY_SOURCES}
    dates = [d for row in rows if (d := iso_date(row["last_seen_at"]))]
    firsts = [d for row in rows if (d := iso_date(row["first_seen_at"]))]
    last_updated = max(dates) if dates else None
    today = date.fromisoformat(last_updated[:10]) if last_updated else date.today()

    # --- entity resolution: one compound → one district and developer ------
    references = apply_aliases(list(records.values()), aliases or {})
    compound_names: dict[str, Counter] = defaultdict(Counter)
    arabic_names: dict[str, Counter] = defaultdict(Counter)
    compound_districts: dict[str, Counter] = defaultdict(Counter)
    compound_developers: dict[str, Counter] = defaultdict(Counter)
    developer_names: dict[str, Counter] = defaultdict(Counter)
    for record in records.values():
        compound = slug(record["compound_name"])
        developer = developer_key(record["developer_name"])
        if developer:
            developer_names[developer][record["developer_name"]] += 1
        if compound:
            compound_names[compound][record["compound_name"]] += 1
            compound_districts[compound][record["district"]] += 1
            if developer:
                compound_developers[compound][developer] += 1
    # The same compound is spelled differently across sources ("Palm Hills New Cairo Phase 5A",
    # "thebrooks", "Aliva city"). A variant joins an established compound of the same developer.
    anchors = {key for key, names in compound_names.items() if sum(names.values()) >= 5}
    alias = {key: target for key in compound_names if key not in anchors
             and (target := match_compound(key, compound_developers[key], anchors, compound_developers))}
    for key, target in alias.items():
        compound_districts[target].update(compound_districts[key])
        compound_developers[target].update(compound_developers[key])
    for record in records.values():
        compound = alias.get(slug(record["compound_name"]), slug(record["compound_name"]))
        record["compound_key"] = compound
        record["developer_key"] = developer_key(record["developer_name"]) or (
            compound_developers[compound].most_common(1)[0][0] if compound and compound_developers[compound] else "")
        if compound:
            record["district"] = compound_districts[compound].most_common(1)[0][0]
        if compound and record.get("compound_name_ar"):
            arabic_names[compound][record["compound_name_ar"]] += 1
        if record["developer_key"] and record.get("developer_name_ar"):
            arabic_names[f"developer:{record['developer_key']}"][record["developer_name_ar"]] += 1
    for record in records.values():
        compound, developer = record["compound_key"], record["developer_key"]
        record["compound"] = ({"key": compound, "name": compound_names[compound].most_common(1)[0][0],
                               "name_ar": majority_or_none(arabic_names.get(compound))} if compound else None)
        record["developer"] = ({"key": developer, "name": developer_names[developer].most_common(1)[0][0],
                                "name_ar": majority_or_none(arabic_names.get(f"developer:{developer}"))}
                               if developer else None)
        bucket, years = delivery_bucket(record["delivery_date"], record["delivery_status"], today)
        record["delivery"] = {"bucket": bucket, "date": record["delivery_date"], "years": years}
        record["unknowns"] = unknowns(record)

    # --- the two comparisons ----------------------------------------------------
    default = [record for record in records.values() if record["is_resale"] is True]
    index = {r["compound_key"]: {"key": r["compound_key"], "developer": r["developer"]}
             for r in default if r["compound_key"]}
    matched, unmatched = match_launches(launches, index, references, aliases)
    launch_units(records.values(), matched, today)
    groups = peer_groups(default)
    for record in records.values():
        record["peers"] = peer_comparison(record, similar_units(record, groups))
        record["opportunity"] = opportunity(record)
    default.sort(key=opportunity_key)

    compounds = build_compounds(default, matched)
    developers = build_developers(default, compounds, matched, moves)
    districts = build_districts(default, compounds, matched)

    run_status = {run["source"]: run["status"] or "unknown" for run in runs}
    source_counts = Counter(row["source"] for row in rows)
    source_resale = Counter(record["source"] for record in default)
    source_rated = Counter(record["source"] for record in default if record["opportunity"]["level"] != "unrated")
    source_dates: dict[str, str] = {}
    for row in rows:
        if seen := iso_date(row["last_seen_at"]):
            source_dates[row["source"]] = max(seen, source_dates.get(row["source"], seen))
    sources = [{"id": source, "name": SOURCE_NAMES.get(source, source.title()), "count": count,
                "resale_count": source_resale[source], "rated_count": source_rated[source],
                "last_seen_at": source_dates.get(source), "status": run_status.get(source, "unknown")}
               for source, count in source_counts.most_common() if source not in PRIMARY_SOURCES]
    # developers' current prices: read only to compare resale against, never listed
    benchmarks = [{"id": source, "name": SOURCE_NAMES.get(source, source.title()), "count": count,
                   "last_seen_at": source_dates.get(source), "status": run_status.get(source, "unknown")}
                  for source, count in source_counts.most_common() if source in PRIMARY_SOURCES]
    first_observed = min(firsts) if firsts else None
    # calendar days with observations, inclusive: one day of crawling is day 1
    window = ((datetime.fromisoformat(last_updated[:10]) - datetime.fromisoformat(first_observed[:10])).days + 1
              if last_updated and first_observed else 0)
    terms = Counter(record["payment"]["terms"] for record in default)
    plan_discounts = [record["payment"]["discount"] for record in default if record["payment"]["terms"] == "plan"]
    levels = Counter(record["opportunity"]["level"] for record in default)
    compared = [r for r in default if r["launch"] and r["launch"]["same_finishing"]]
    since = [r["launch"]["since_contract"]["annual"] for r in default
             if r["launch"] and r["launch"]["since_contract"] and r["launch"]["since_contract"]["annual"] is not None]
    overview = {
        "total_records": sum(1 for row in rows if row["source"] not in PRIMARY_SOURCES),
        "total_eligible": len(records), "total_resale": len(default),
        "rated_count": len(default) - levels["unrated"], "opportunities": dict(levels),
        # headline counts: established entities only, not one-off spellings
        "compound_count": sum(1 for c in compounds.values() if c["units"] >= 5),
        "developer_count": sum(1 for d in developers.values() if d["units"] >= 5),
        "district_count": sum(1 for d in districts.values() if d["units"] >= 5),
        "last_updated": last_updated, "first_observed": first_observed, "observation_days": window,
        "history_ready": window >= HISTORY_READY_DAYS, "sources": sources, "benchmarks": benchmarks,
        "scope": scope(default), "payment_terms": dict(terms), "plan_median_discount": _median(plan_discounts, 4),
        "discount_rate": DISCOUNT_RATE,
        "launch": {"units": len(launches), "matched": sum(len(units) for units in matched.values()),
                   "unmatched": unmatched, "compounds": len(matched), "compared": len(compared),
                   "median_gap": _median([r["launch"]["gap"] for r in compared], 4)},
        "peers": {"ranked": sum(1 for r in default if r["peers"]), "min_similar": PEER_MIN},
        "since_contract": {"units": len(since), "median_annual": _median(since, 4)},
        "thresholds": {"strong_all": STRONG_ALL, "strong_one": STRONG_ONE, "good_all": GOOD_ALL,
                       "good_one": GOOD_ONE, "pricier": PRICIER, "check_developer": CHECK_DEVELOPER,
                       "check_peers": CHECK_PEERS, "check_cheapest": CHECK_BELOW_CHEAPEST},
        # which developers' resale units sit furthest below their own prices today
        "developer_gaps": sorted(
            ({"key": d["key"], "name": d["name"], "name_ar": d["name_ar"], "gap": d["launch"]["median_gap"],
              "units": d["launch"]["compared"]}
             for d in developers.values() if d["launch"] and d["launch"]["compared"] >= 20),
            key=lambda d: d["gap"]),
    }
    catalog = {
        "districts": [{"key": d["key"], "name": d["name"], "units": d["units"]} for d in districts.values()],
        "compounds": [{"key": c["key"], "name": c["name"], "name_ar": c["name_ar"], "district": c["district"],
                       "developer": c["developer"]["name"] if c["developer"] else None,
                       "developer_ar": c["developer"]["name_ar"] if c["developer"] else None, "units": c["units"]}
                      for c in compounds.values()],
        "developers": [{"key": d["key"], "name": d["name"], "name_ar": d["name_ar"], "units": d["units"]}
                       for d in developers.values()],
        "property_types": [{"value": kind, "class": cls, "count": count} for (kind, cls), count in Counter(
            (r["property_type"], r["class"]) for r in default).most_common()],
    }
    urls = Counter(key for r in records.values() if (key := url_key(r["source_url"])))
    unique_urls = {key: r["id"] for r in records.values()
                   if (key := url_key(r["source_url"])) and urls[key] == 1}
    return Snapshot(records=records, default=default, today=today, compounds=compounds,
                    developers=developers, districts=districts, overview=overview, catalog=catalog,
                    urls=unique_urls, launches=dict(matched), peers=groups)


def _cash_ppm(record: dict) -> float | None:
    cash = record["payment"]["cash_equivalent"]
    return cash / record["area_m2"] if cash else None


def price_classes(items: list[dict], units: list[dict]) -> list[dict]:
    """Observed prices per property class: the resale units' contract and cash-today prices per m²,
    the developer's current prices for the same class, and the resale units' gap to them."""
    out = []
    for cls in ("apartment", "chalet", "house"):
        group = [r for r in items if r["class"] == cls]
        if not group:
            continue
        developer = [u for u in units if u["class"] == cls]
        compared = [r for r in group if r["launch"] and r["launch"]["same_finishing"]]
        years = [r["contract_year"] for r in group if r.get("contract_year")]
        out.append({
            "class": cls, "units": len(group),
            "median_asking_ppm": _median([r["price_per_m2"] for r in group], -2),
            "median_cash_ppm": _median([p for r in group if (p := _cash_ppm(r))], -2),
            "developer_ppm": _median([u["price_per_m2"] for u in developer], -2),
            "developer_cash_ppm": _median([p for u in developer if (p := _cash_ppm(u))], -2),
            "median_gap": _median([r["launch"]["gap"] for r in compared], 4), "compared": len(compared),
            "median_contract_year": round(median(years)) if years else None,
        })
    return out


def developer_prices(units: list[dict], resale: list[dict]) -> dict | None:
    """The developer's current units (in a compound, or across a developer) against its resale units."""
    if not units:
        return None
    compared = [r for r in resale if r["launch"] and r["launch"]["same_finishing"]]
    since = [r["launch"]["since_contract"]["annual"] for r in resale if r["launch"] and r["launch"]["since_contract"]
             and r["launch"]["since_contract"]["annual"] is not None]
    return {
        "units": len(units), "median_headline_ppm": _median([u["price_per_m2"] for u in units], -2),
        "median_cash_ppm": _median([p for u in units if (p := _cash_ppm(u))], -2),
        "median_plan_years": _median([u["payment"]["years"] for u in units if u["payment"]["years"] is not None], 1),
        "median_down_share": _median([1 - (u["payment"]["remaining_share"] or 0) for u in units], 4),
        "latest_delivery_year": max((int(u["delivery_date"][:4]) for u in units if u["delivery_date"]), default=None),
        "phases": sorted({u["compound_name"] for u in units if u["compound_name"]})[:6],
        "compared": len(compared), "median_gap": _median([r["launch"]["gap"] for r in compared], 4),
        "median_since_contract": _median(since, 4),
    }


def _profile(items: list[dict]) -> dict:
    """Delivery and payment structure of a set of listings, and how many are opportunities."""
    dated = [r["delivery"]["years"] for r in items if r["delivery"]["years"] is not None]
    known = [r for r in items if r["delivery"]["bucket"] != "unknown"]
    plans = [r for r in items if r["payment"]["terms"] == "plan"]
    finishing = Counter(r["finishing_class"] for r in items)
    return {
        "ready_share": _share(sum(r["delivery"]["bucket"] == "ready" for r in known), len(known)),
        "delivery_known": len(known),
        "median_years_to_delivery": _median([y for y in dated if y > 0], 1),
        "latest_delivery_year": max((int(r["delivery"]["date"][:4]) for r in items if r["delivery"]["date"]), default=None),
        "plan_share": _share(len(plans), sum(r["payment"]["terms"] in ("plan", "cash") for r in items)),
        "median_remaining_share": _median([r["payment"]["remaining_share"] for r in plans], 4),
        "median_plan_years": _median([r["payment"]["years"] for r in plans], 1),
        "median_plan_discount": _median([r["payment"]["discount"] for r in plans], 4),
        "finishing": {level: count for level, count in finishing.most_common()},
        "opportunities": dict(Counter(r["opportunity"]["level"] for r in items)),
    }


def _good(profile: dict) -> int:
    return sum(profile["opportunities"].get(level, 0) for level in ("strong", "good"))


def match_launches(launches: list[dict], compounds: dict[str, dict], references: dict[str, str] | None = None,
                   aliases: dict[str, dict] | None = None) -> tuple[dict[str, list[dict]], int]:
    """Developer launch units per resale compound, and how many could not be placed.

    A launch unit joins a compound through the Nawy name the compound's spellings resolve to
    (entities.py), by name, through the compound its own sub-project name resolves to
    ("Sealine - Seashore" → Seashore), or as a new phase of it ("SODIC East — New Phase" →
    "SODIC East"). The last two need the developer to agree.
    """
    known = {key: key for key in compounds}
    known.update({ref: key for ref, key in (references or {}).items() if key in compounds})
    by_prefix = sorted(known, key=len, reverse=True)
    matched: dict[str, list[dict]] = defaultdict(list)
    unmatched = 0

    def same_developer(key: str, developer: str) -> bool:
        return bool(compounds[key]["developer"]) and compounds[key]["developer"]["key"] == developer

    for record in launches:
        if not record["payment"]["cash_equivalent"]:
            continue
        key, developer = slug(record["compound_name"]), developer_key(record["developer_name"])
        alias = (aliases or {}).get(alias_key(record["compound_name"], record["developer_name"]) or "")
        parent = slug(alias["compound"]) if alias and alias["kind"] == "compound" and alias["compound"] else ""
        if parent not in compounds or not same_developer(parent, developer):
            parent = ""
        target = compounds.get(known.get(key, "")) or compounds.get(parent) or next(
            (compounds[known[k]] for k in by_prefix if key.startswith(f"{k}-") and same_developer(known[k], developer)),
            None)
        if target is None:
            unmatched += 1
        else:
            matched[target["key"]].append(record)
    return matched, unmatched


LAUNCH_NEIGHBOURS = 5
LAUNCH_MIN_UNITS = 2  # one launch unit is an anecdote, not the developer's price
LAUNCH_AREA_RATIO = 1.5  # a launch unit is similar when neither size is more than 1.5× the other


def launch_units(records, matched: dict[str, list[dict]], today: date) -> None:
    """The developer's current price for a unit like each resale unit, where the developer is selling.

    Similar means the same compound and unit type, within 1.5× the size; the nearest five by size
    are used, and at least two are needed. The type must match exactly: Nawy's cabins and lofts
    share the chalet and apartment classes but are priced per m² like different products. Units
    with the same finishing are preferred when there are two; the finishing compared is reported. Both sides are compared in today's money (cash-equivalent), so a launch
    price on a ten-year plan and a resale balance are on one basis. The launch units' delivery
    is reported alongside: a resale unit usually delivers sooner.
    """
    for record in records:
        record["launch"] = None
        units = matched.get(record.get("compound_key") or "")
        cash = record["payment"]["cash_equivalent"]
        if not units or not cash:
            continue
        similar = [u for u in units if u["property_type"] == record["property_type"]
                   and abs(math.log(u["area_m2"] / record["area_m2"])) <= math.log(LAUNCH_AREA_RATIO)]
        if len(similar) < LAUNCH_MIN_UNITS:
            continue
        same_finishing = [u for u in similar if u["finishing_class"] == record["finishing_class"] != "unknown"]
        if len(same_finishing) >= LAUNCH_MIN_UNITS:
            similar = same_finishing
        similar.sort(key=lambda u: (abs(math.log(u["area_m2"] / record["area_m2"])), u["id"]))
        nearest = similar[:LAUNCH_NEIGHBOURS]
        cash_ppm = median(u["payment"]["cash_equivalent"] / u["area_m2"] for u in nearest)
        headline_ppm = median(u["price_per_m2"] for u in nearest)
        developer_cash = cash_ppm * record["area_m2"]
        years = [u["payment"]["years"] for u in nearest if u["payment"]["years"] is not None]
        deliveries = [int(u["delivery_date"][:4]) for u in nearest if u["delivery_date"]]
        cash_gap, headline_gap = cash / developer_cash - 1, record["price_per_m2"] / headline_ppm - 1
        record["launch"] = {
            # the less favourable of the two: cheaper only if cheaper both as listed and in today's money,
            # so neither a long remaining plan nor the discount rate can make a deal on its own
            "gap": round(max(cash_gap, headline_gap), 4), "cash_gap": round(cash_gap, 4),
            "headline_gap": round(headline_gap, 4), "units": len(nearest),
            "developer_cash": round(developer_cash, -3), "developer_price": round(headline_ppm * record["area_m2"], -3),
            "cash_ppm": round(cash_ppm), "headline_ppm": round(headline_ppm),
            "down_share": _median([1 - (u["payment"]["remaining_share"] or 0) for u in nearest], 4),
            "plan_years": _median(years, 1), "delivery_year": round(median(deliveries)) if deliveries else None,
            "area_range": [min(u["area_m2"] for u in nearest), max(u["area_m2"] for u in nearest)],
            "types": sorted({u["property_type"] for u in nearest}),
            "finishing": majority(u["finishing_class"] for u in nearest),
            "same_finishing": all(u["finishing_class"] == record["finishing_class"] for u in nearest),
            "since_contract": since_contract(record, headline_ppm, today),
        }


def since_contract(record: dict, developer_ppm: float, today: date) -> dict | None:
    """How the developer's list price per m² moved since the seller signed: both are headline prices
    (the seller's is his contract price, the developer's is today's for a similar unit)."""
    year = record.get("contract_year")
    if not year or year > today.year:
        return None
    change = developer_ppm / record["price_per_m2"] - 1
    years = (today - date(year, 7, 1)).days / 365.25  # the contract month is not published: mid-year
    annual = (1 + change) ** (1 / years) - 1 if years >= 1 and change > -1 else None
    return {"year": year, "contract_ppm": record["price_per_m2"], "change": round(change, 4),
            "annual": round(annual, 4) if annual is not None else None}


def build_compounds(default: list[dict], matched: dict[str, list[dict]]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in default:
        if record["compound_key"]:
            groups[record["compound_key"]].append(record)
    compounds = {}
    for key, items in groups.items():
        first = items[0]
        profile = _profile(items)
        compounds[key] = {
            "key": key, "name": first["compound"]["name"], "name_ar": first["compound"]["name_ar"],
            "district": first["district"], "district_key": slug(first["district"]), "developer": first["developer"],
            "units": len(items), "classes": price_classes(items, matched.get(key, [])),
            "area_range": [min(r["area_m2"] for r in items), max(r["area_m2"] for r in items)],
            "types": dict(Counter(r["property_type"] for r in items).most_common()),
            "scope": scope(items), **profile, "good_count": _good(profile),
            "launch": developer_prices(matched.get(key, []), items),
        }
    return dict(sorted(compounds.items(), key=lambda pair: (-pair[1]["units"], pair[0])))


def build_developers(default: list[dict], compounds: dict[str, dict], matched: dict[str, list[dict]],
                     moves: list) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in default:
        if record["developer_key"]:
            groups[record["developer_key"]].append(record)
    moved: dict[int, int] = {}
    for row in moves:
        change = decode_json(row["changed_fields"], dict).get("delivery_date")
        if isinstance(change, dict) and isinstance(change.get("old"), str) and isinstance(change.get("new"), str):
            moved[row["property_id"]] = (change["new"] > change["old"]) - (change["new"] < change["old"])
    developers = {}
    for key, items in groups.items():
        own = [c for c in compounds.values() if c["developer"] and c["developer"]["key"] == key]
        tracked = [moved[r["id"]] for r in items if r["id"] in moved]
        profile = _profile(items)
        developers[key] = {
            "key": key, "name": items[0]["developer"]["name"], "name_ar": items[0]["developer"]["name_ar"],
            "units": len(items),
            "compounds": [{"key": c["key"], "name": c["name"], "name_ar": c["name_ar"], "district": c["district"],
                           "units": c["units"], "good_count": c["good_count"],
                           "median_gap": c["launch"]["median_gap"] if c["launch"] else None} for c in own],
            "districts": [{"name": name, "units": count}
                          for name, count in Counter(r["district"] for r in items).most_common()],
            "delivery_changes": {"tracked_units": sum(1 for r in items if r["delivery"]["date"]),
                                 "postponed": tracked.count(1), "brought_forward": tracked.count(-1)},
            "scope": scope(items), **profile, "good_count": _good(profile),
            "launch": developer_prices([u for c in own for u in matched.get(c["key"], [])], items),
        }
    return dict(sorted(developers.items(), key=lambda pair: (-pair[1]["units"], pair[0])))


def build_districts(default: list[dict], compounds: dict[str, dict], matched: dict[str, list[dict]]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in default:
        groups[slug(record["district"])].append(record)
    districts = {}
    for key, items in groups.items():
        name = majority(r["district"] for r in items)
        inside = [c["key"] for c in compounds.values() if c["district_key"] == key]
        districts[key] = {
            "key": key, "name": name, "units": len(items),
            "classes": price_classes(items, [u for c in inside for u in matched.get(c, [])]),
            "compound_count": len(inside), "scope": scope(items), **_profile(items),
        }
    return dict(sorted(districts.items(), key=lambda pair: (-pair[1]["units"], pair[0])))


def comparables(snapshot: Snapshot, record: dict) -> list[dict]:
    """The similar resale units the unit is ranked against, nearest in size first; otherwise the
    nearest units of its class in the same compound."""
    pool = similar_units(record, snapshot.peers)
    if not pool and record.get("compound_key"):
        pool = sorted((r for r in snapshot.default if r["compound_key"] == record["compound_key"]
                       and r["class"] == record["class"] and r["id"] != record.get("id") and _cash_ppm(r)),
                      key=lambda r: (abs(math.log(r["area_m2"] / record["area_m2"])), r["id"]))
    return [{**public_unit(r), "cash_ppm": round(_cash_ppm(r))} for r in pool[:PEER_LIMIT]]


def detail(snapshot: Snapshot, record: dict, description: str | None) -> dict:
    return {"unit": {**public_unit(record, full=True), "description": description},
            "comparables": comparables(snapshot, record)}


def evaluate(snapshot: Snapshot, *, property_type: str, area: float, price: float, compound: str,
             down_payment: float | None = None, installment_years: float | None = None, delivery: str = "",
             finishing: str = "") -> dict:
    """Compare a unit the user describes with the developer's price today and the similar units listed now."""
    kind = TYPE_ALIASES.get(property_type.strip().casefold(), property_type.strip().casefold())
    wanted = compound.strip().casefold()
    entry = snapshot.compounds.get(slug(compound)) or next(
        (c for c in snapshot.compounds.values() if wanted in (c["name"].casefold(), (c["name_ar"] or "").casefold())), None)
    months = round(installment_years * 12) if installment_years else None
    plan = down_payment is not None and months
    payment = payment_terms(price, down_payment if plan else None, months if plan else None,
                            True if plan else None, cash_when_not_installment=True)
    inputs = {"property_type": kind, "class": CLASSES.get(kind), "area_m2": area, "price": price,
              "price_per_m2": round(price / area), "finishing_class": finishing_class(finishing),
              "compound": {"key": entry["key"], "name": entry["name"], "name_ar": entry["name_ar"]} if entry else None,
              "developer": entry["developer"] if entry else None, "district": entry["district"] if entry else None}
    if entry is None:
        return {"status": "compound_not_found", "inputs": inputs, "payment": payment, "launch": None, "peers": None,
                "opportunity": {"level": "unrated", "score": None, "signals": []}, "comparables": [], "unknowns": []}
    delivery_date = f"{delivery}-01"[:10] if re.fullmatch(r"\d{4}(-\d{2})?", delivery or "") else None
    if delivery_date and len(delivery) == 4:
        delivery_date = f"{delivery}-06-30"
    record = {
        "id": None, "class": inputs["class"], "property_type": kind, "district": entry["district"],
        "compound_key": entry["key"], "developer_key": entry["developer"]["key"] if entry["developer"] else "",
        "area_m2": area, "price": price, "price_per_m2": inputs["price_per_m2"],
        "finishing_class": inputs["finishing_class"], "delivery_date": delivery_date,
        "delivery_status": "ready" if delivery.casefold() == "ready" else None, "payment": payment,
        "contract_year": None,
    }
    bucket, years = delivery_bucket(delivery_date, record["delivery_status"], snapshot.today)
    record["delivery"] = inputs["delivery"] = {"bucket": bucket, "date": delivery_date, "years": years}
    launch_units([record], snapshot.launches, snapshot.today)
    record["peers"] = peer_comparison(record, similar_units(record, snapshot.peers))
    record["opportunity"] = opportunity(record)
    return {"status": "compared", "inputs": inputs, "payment": payment, "launch": record["launch"],
            "peers": record["peers"], "opportunity": record["opportunity"],
            "comparables": comparables(snapshot, record),
            "unknowns": [u for u in unknowns(record) if u not in ("payment_terms", "installment_term")]}

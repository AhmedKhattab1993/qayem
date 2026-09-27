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
from threading import RLock
import time
from typing import Any
from urllib.parse import urlsplit

from .valuation import (
    CLASSES, DISCOUNT_RATE, OUTLIER_LOG, REFERENCE_TYPE, Model, Unit, canonical_district,
    delivery_bucket, developer_key, finishing_class, fit, majority, payment_terms, plan_bucket, slug,
    summarize_effects,
)

SOURCE_NAMES = {
    "nawy": "Nawy", "nawy_primary": "Nawy (developer launches)", "opensooq": "OpenSooq", "aqarmap": "Aqarmap",
    "semsar": "Semsar Masr", "gpm": "GPM", "coldwellbanker": "Coldwell Banker",
    "aqarexit": "AqarExit",
}
# Sources whose absent installment plan means a cash price (structured payment data).
CASH_WHEN_NO_PLAN = {"nawy", "nawy_primary"}
# Developers' current launch units: a benchmark for resale, never resale evidence.
PRIMARY_SOURCES = {"nawy_primary"}
TYPE_ALIASES = {
    "apartments": "apartment", "villas": "villa", "chalets": "chalet",
    "retail": "shop", "medical": "clinic", "townhouses": "townhouse",
    "twinhouses": "twinhouse", "twin_house": "twinhouse", "town_house": "townhouse",
    "بنتهاوس": "penthouse",
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
    "first_seen_at", "last_seen_at",
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
        "last_seen_at": iso_date(row["last_seen_at"]), "first_seen_at": iso_date(row["first_seen_at"]),
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
    model: Model
    today: date
    compounds: dict[str, dict]
    developers: dict[str, dict]
    districts: dict[str, dict]
    overview: dict
    catalog: dict
    urls: dict[str, int]


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


def unit_for(record: dict, today: date) -> Unit | None:
    if not record["class"] or not record["district"]:
        return None
    bucket, _ = delivery_bucket(record["delivery_date"], record["delivery_status"], today)
    cash = record["payment"]["cash_equivalent"]
    return Unit(id=record["id"], cls=record["class"], type=record["property_type"], district=record["district"],
                developer=record["developer_key"], compound=record["compound_key"],
                finishing=record["finishing_class"], delivery=bucket, log_area=math.log(record["area_m2"]),
                y=math.log(cash / record["area_m2"]) if cash else None, plan=plan_bucket(record["payment"]),
                in_compound=record.get("in_compound"))


def valuation(model: Model, unit: Unit | None, payment: dict, price: float, area: float,
              in_training: bool) -> dict:
    """Fair value for one unit and where its price sits. Listings in the training set are
    valued leave-one-out, so a listing never vouches for its own price."""
    if unit is None:
        return {"status": "not_modelled", "reason": "Qayem values apartments, chalets and houses only."}
    prediction = model.predict(unit, exclude=in_training)
    if prediction is None:
        return {"status": "insufficient", "reason": "Too few comparable listings in this district and class."}
    fair, low, high = (prediction[k] * area for k in ("fair_ppm", "low_ppm", "high_ppm"))
    result = {
        "status": "valued", "grade": prediction["grade"], "fair_value": round(fair, -3),
        "fair_low": round(low, -3), "fair_high": round(high, -3), "fair_ppm": round(prediction["fair_ppm"]),
        "basis": None, "compared_price": None, "deviation": None, "verdict": None, "fair_headline": None,
    }
    if payment["terms"] in ("cash", "plan"):
        result["basis"] = "cash_equivalent"
        result["compared_price"] = payment["cash_equivalent"]
        if payment["terms"] == "plan" and payment["cash_equivalent"]:
            result["fair_headline"] = round(fair * price / payment["cash_equivalent"], -3)
    # Unknown terms are not positioned: classifieds often post only what is due now
    # (down payment plus overpayment), leaving remaining installments out of the price.
    if result["compared_price"]:
        compared = result["compared_price"]
        result["deviation"] = round(compared / fair - 1, 4)
        if abs(math.log(compared / fair)) > OUTLIER_LOG:
            result["verdict"] = "suspect"  # too far from any comparable: likely a listing error
        else:
            result["verdict"] = "below" if compared < low else "above" if compared > high else "within"
    return result


def breakdown(model: Model, unit: Unit, labels: dict[str, str]) -> dict:
    """How the fair price per m² was built, in percentage steps."""
    steps = model.path(unit, exclude=unit.id in model.contributions)
    levels = []
    for step in steps:
        levels.append({"level": step["level"], "label": labels.get(step["level"]), "listings": step["n"],
                       "change": round(math.exp(step["delta"]) - 1, 4), "ppm": round(math.exp(step["estimate"]))})
    area_effect = model.area_slope.get(unit.cls, 0.0) * (unit.log_area - model.area_center.get(unit.cls, unit.log_area))
    adjustments = [
        {"factor": "type", "value": unit.type, "change": round(math.exp(model.effects["type"].get(unit.type, 0.0)) - 1, 4)},
        {"factor": "finishing", "value": unit.finishing,
         "change": round(math.exp(model.effects["finishing"].get(unit.finishing, 0.0)) - 1, 4)},
        {"factor": "delivery", "value": unit.delivery,
         "change": round(math.exp(model.effects["delivery"].get(unit.delivery, 0.0)) - 1, 4)},
        {"factor": "plan", "value": unit.plan,
         "change": round(math.exp(model.effects["plan"].get(unit.plan, 0.0)) - 1, 4)},
        {"factor": "size", "value": round(math.exp(unit.log_area)),
         "typical": round(math.exp(model.area_center.get(unit.cls, unit.log_area))),
         "change": round(math.exp(area_effect) - 1, 4)},
    ]
    return {"levels": levels, "adjustments": adjustments}


def unknowns(record: dict) -> list[str]:
    """What the valuation could not see for this unit."""
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
            "payment", "valuation", "is_resale")
    extra = ("bathrooms", "finishing", "installments", "down_payment", "installment_months",
             "resale_evidence", "last_seen_at", "unknowns")
    return {key: record.get(key) for key in keys + (extra if full else ())}


class Catalog:
    """Share sanitized immutable-by-convention projections, never live sessions."""

    def __init__(self, path: str | Path, refresh_seconds: float = 300):
        self.path = Path(path).expanduser().resolve()
        # A crawl commits every few seconds; the model is refitted at most this often.
        self.refresh_seconds = refresh_seconds
        self._lock = RLock()
        self._fingerprint: tuple | None = None
        self._cached: Snapshot | None = None
        self._built_at = 0.0

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

    def snapshot(self) -> Snapshot:
        with self._lock:
            signature = self._signature()
            if self._cached is not None and (
                    signature == self._fingerprint or time.monotonic() - self._built_at < self.refresh_seconds):
                return self._cached
            try:
                with closing(self.connect()) as connection:
                    present = {row[1] for row in connection.execute("PRAGMA table_info(properties)")}
                    columns = ", ".join(name if name in present else f"NULL AS {name}" for name in _FIELDS)
                    rows = connection.execute(f"SELECT {columns} FROM properties").fetchall()
                    runs = connection.execute(
                        "SELECT source, status, started_at, id FROM parse_runs ORDER BY started_at, id"
                    ).fetchall()
                    moves = connection.execute(
                        "SELECT property_id, changed_fields FROM property_versions "
                        "WHERE change_type IN ('updated', 'relisted') AND changed_fields LIKE '%delivery_date%'"
                    ).fetchall()
                    hidden = unreliable_price_ids(connection)
                snapshot = build_snapshot(rows, runs, moves, hidden)
            except sqlite3.Error as exc:
                raise CatalogUnavailable("Qayem dataset is not ready. Point QAYEM_DB to a database containing the Qayem tables.") from exc
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


def build_snapshot(rows: list, runs: list, moves: list, hidden: set[int] = frozenset()) -> Snapshot:
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
    compound_names: dict[str, Counter] = defaultdict(Counter)
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
        record["compound"] = ({"key": compound, "name": compound_names[compound].most_common(1)[0][0]}
                              if compound else None)
        record["developer"] = ({"key": record["developer_key"],
                                "name": developer_names[record["developer_key"]].most_common(1)[0][0]}
                               if record["developer_key"] else None)
        bucket, years = delivery_bucket(record["delivery_date"], record["delivery_status"], today)
        record["delivery"] = {"bucket": bucket, "date": record["delivery_date"], "years": years}
        record["unknowns"] = unknowns(record)

    # --- fit on identified resale with known payment terms --------------------
    default = [record for record in records.values() if record["is_resale"] is True]
    units = {record["id"]: unit_for(record, today) for record in default}
    model = fit([unit for unit in units.values() if unit is not None], today)
    for record in records.values():
        unit = units.get(record["id"]) or unit_for(record, today)
        record["valuation"] = valuation(model, unit, record["payment"], record["price"], record["area_m2"],
                                        in_training=record["id"] in model.contributions)
    default.sort(key=lambda r: ({"A": 0, "B": 1, "C": 2}.get(r["valuation"].get("grade"), 3), r["id"]))

    compounds = build_compounds(default, model, today)
    developers = build_developers(default, model, compounds, moves)
    districts = build_districts(default, model, compounds)
    launch = launch_benchmarks(launches, compounds, developers, model, today)
    launch["support"] = launch_support(default)

    run_status = {run["source"]: run["status"] or "unknown" for run in runs}
    source_counts = Counter(row["source"] for row in rows)
    source_resale = Counter(record["source"] for record in default)
    source_valued = Counter(record["source"] for record in default if record["valuation"].get("verdict"))
    source_dates: dict[str, str] = {}
    for row in rows:
        if seen := iso_date(row["last_seen_at"]):
            source_dates[row["source"]] = max(seen, source_dates.get(row["source"], seen))
    sources = [{"id": source, "name": SOURCE_NAMES.get(source, source.title()), "count": count,
                "resale_count": source_resale[source], "valued_count": source_valued[source],
                "last_seen_at": source_dates.get(source), "status": run_status.get(source, "unknown")}
               for source, count in source_counts.most_common()]
    first_observed = min(firsts) if firsts else None
    # calendar days with observations, inclusive: one day of crawling is day 1
    window = ((datetime.fromisoformat(last_updated[:10]) - datetime.fromisoformat(first_observed[:10])).days + 1
              if last_updated and first_observed else 0)
    valued = [record for record in default if record["valuation"]["status"] == "valued"]
    terms = Counter(record["payment"]["terms"] for record in default)
    plan_discounts = [record["payment"]["discount"] for record in default if record["payment"]["terms"] == "plan"]
    overview = {
        "total_records": len(rows), "total_eligible": len(records), "total_resale": len(default),
        "valued_count": len(valued), "positioned_count": sum(1 for r in valued if r["valuation"]["verdict"]),
        # headline counts: established entities only, not one-off spellings from classifieds
        "compound_count": sum(1 for c in compounds.values() if c["units"] >= 5),
        "developer_count": sum(1 for d in developers.values() if d["units"] >= 5),
        "district_count": sum(1 for d in districts.values() if d["units"] >= 5),
        "last_updated": last_updated, "first_observed": first_observed, "observation_days": window,
        "history_ready": window >= HISTORY_READY_DAYS, "sources": sources, "scope": scope(default),
        "backtest": model.backtest, "effects": summarize_effects(model),
        "payment_terms": dict(terms), "plan_median_discount": _median(plan_discounts, 4), "launch": launch,
        "discount_rate": DISCOUNT_RATE,
        "verdicts": dict(Counter(r["valuation"]["verdict"] for r in valued if r["valuation"]["verdict"])),
        "developer_premiums": sorted(
            ({"key": d["key"], "name": d["name"], "premium": d["premium_vs_district"], "units": d["units"]}
             for d in developers.values() if d["premium_vs_district"] is not None and d["units"] >= 40),
            key=lambda d: -d["premium"]),
    }
    catalog = {
        "districts": [{"key": d["key"], "name": d["name"], "units": d["units"]} for d in districts.values()],
        "compounds": [{"key": c["key"], "name": c["name"], "district": c["district"],
                       "developer": c["developer"]["name"] if c["developer"] else None, "units": c["units"]}
                      for c in compounds.values()],
        "developers": [{"key": d["key"], "name": d["name"], "units": d["units"]} for d in developers.values()],
        "property_types": [{"value": kind, "class": cls, "count": count} for (kind, cls), count in Counter(
            (r["property_type"], r["class"]) for r in default if r["class"]).most_common()],
    }
    urls = Counter(key for r in records.values() if (key := url_key(r["source_url"])))
    unique_urls = {key: r["id"] for r in records.values()
                   if (key := url_key(r["source_url"])) and urls[key] == 1}
    return Snapshot(records=records, default=default, model=model, today=today, compounds=compounds,
                    developers=developers, districts=districts, overview=overview, catalog=catalog,
                    urls=unique_urls)


def _reference_unit(cls: str, district: str, developer: str, compound: str, model: Model) -> Unit:
    return Unit(id=None, cls=cls, type=REFERENCE_TYPE[cls], district=district, developer=developer,
                compound=compound, finishing="finished", delivery="ready",
                log_area=model.area_center.get(cls, math.log(120)))


def _classes(items: list[dict], model: Model, district: str, developer: str, compound: str) -> list[dict]:
    """Reference fair price per m² and observed prices, per property class."""
    out = []
    for cls in ("apartment", "chalet", "house"):
        group = [r for r in items if r["class"] == cls]
        if not group or cls not in model.base:
            continue
        reference = _reference_unit(cls, district, developer, compound, model)
        steps = model.path(reference)
        grade = model.grade(steps)
        district_step = next((s for s in steps if s["level"] == "district"), None)
        premium = (math.exp(steps[-1]["estimate"] - district_step["estimate"]) - 1
                   if district_step and grade and len(steps) > 2 else None)
        cash = [r["payment"]["cash_equivalent"] / r["area_m2"] for r in group if r["payment"]["cash_equivalent"]]
        out.append({
            "class": cls, "units": len(group), "grade": grade,
            "reference_ppm": round(math.exp(steps[-1]["estimate"]), -2) if grade else None,
            "premium_vs_district": round(premium, 4) if premium is not None else None,
            "median_asking_ppm": _median([r["price_per_m2"] for r in group], -2),
            "median_cash_ppm": _median(cash, -2),
            "median_area": _median([r["area_m2"] for r in group]),
        })
    return out


def _profile(items: list[dict]) -> dict:
    """Delivery and payment structure of a set of listings."""
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
        "verdicts": dict(Counter(r["valuation"]["verdict"] for r in items if r["valuation"].get("verdict"))),
    }


def launch_benchmarks(launches: list[dict], compounds: dict[str, dict], developers: dict[str, dict],
                      model: Model, today: date) -> dict:
    """Compare each developer launch unit with what the resale market pays for the same unit.

    A launch unit is matched to its resale compound by name, or as a new phase of it
    ("SODIC East — New Phase" → "SODIC East") when the developer agrees. The resale value
    is the model's fair cash-equivalent for the same compound, type, finishing, delivery,
    plan length and size; only compound- or developer-level valuations (grades A/B) count.
    """
    by_prefix = sorted(compounds, key=len, reverse=True)
    per_compound: dict[str, list[dict]] = defaultdict(list)
    per_developer: dict[str, list[dict]] = defaultdict(list)
    unmatched = 0
    for record in launches:
        cash = record["payment"]["cash_equivalent"]
        if not record["class"] or not cash:
            continue
        key, developer = slug(record["compound_name"]), developer_key(record["developer_name"])
        target = compounds.get(key) or next(
            (compounds[k] for k in by_prefix if key.startswith(f"{k}-") and compounds[k]["developer"]
             and compounds[k]["developer"]["key"] == developer), None)
        if target is None:
            unmatched += 1
            continue
        matched = {**record, "compound_key": target["key"], "in_compound": True, "district": target["district"],
                   "developer_key": target["developer"]["key"] if target["developer"] else developer}
        bucket, years = delivery_bucket(matched["delivery_date"], matched["delivery_status"], today)
        matched["delivery"] = {"bucket": bucket, "date": matched["delivery_date"], "years": years}
        unit = unit_for(matched, today)
        prediction = model.predict(unit) if unit else None
        if not prediction or prediction["grade"] not in ("A", "B"):
            continue
        item = {"spread": cash / (prediction["fair_ppm"] * record["area_m2"]) - 1,
                "headline_ppm": record["price_per_m2"], "cash_ppm": cash / record["area_m2"],
                "years": record["payment"]["years"], "down": 1 - (record["payment"]["remaining_share"] or 0),
                "phase": record["compound_name"], "delivery_year": int(record["delivery_date"][:4]) if record["delivery_date"] else None}
        per_compound[target["key"]].append(item)
        per_developer[matched["developer_key"]].append(item)

    def summary(items: list[dict]) -> dict:
        return {"units": len(items), "median_spread": _median([i["spread"] for i in items], 4),
                "median_headline_ppm": _median([i["headline_ppm"] for i in items], -2),
                "median_cash_ppm": _median([i["cash_ppm"] for i in items], -2),
                "median_plan_years": _median([i["years"] for i in items if i["years"] is not None], 1),
                "median_down_share": _median([i["down"] for i in items], 4),
                "latest_delivery_year": max((i["delivery_year"] for i in items if i["delivery_year"]), default=None),
                "phases": sorted({i["phase"] for i in items})[:6]}

    for compound in compounds.values():
        compound["launch"] = summary(per_compound[compound["key"]]) if per_compound.get(compound["key"]) else None
    for key, developer in developers.items():
        developer["launch"] = summary(per_developer[key]) if per_developer.get(key) else None
    everything = [item for items in per_compound.values() for item in items]
    return {"units": len(launches), "compared": len(everything), "unmatched": unmatched,
            "compounds": len(per_compound), "median_spread": _median([i["spread"] for i in everything], 4)}


def launch_support(default: list[dict]) -> dict:
    """How well the model prices resale units whose plans look like launch plans
    (most of the price still owed over many years): the evidence behind the spread."""
    similar = [r for r in default if r["payment"]["terms"] == "plan" and r["payment"]["remaining_share"] >= 0.85
               and r["payment"]["years"] >= 7 and r["valuation"].get("deviation") is not None]
    return {"units": len(similar), "median_residual": _median([r["valuation"]["deviation"] for r in similar], 4)}


def build_compounds(default: list[dict], model: Model, today: date) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in default:
        if record["compound_key"]:
            groups[record["compound_key"]].append(record)
    compounds = {}
    for key, items in groups.items():
        first = items[0]
        classes = _classes(items, model, first["district"], first["developer_key"], key)
        graded = [c for c in classes if c["grade"]]
        compounds[key] = {
            "key": key, "name": first["compound"]["name"], "district": first["district"],
            "district_key": slug(first["district"]), "developer": first["developer"],
            "units": len(items), "classes": classes,
            "premium_vs_district": max(graded, key=lambda c: c["units"])["premium_vs_district"] if graded else None,
            "grade": min((c["grade"] for c in graded), default=None),
            "area_range": [min(r["area_m2"] for r in items), max(r["area_m2"] for r in items)],
            "types": dict(Counter(r["property_type"] for r in items).most_common()),
            "scope": scope(items), **_profile(items),
        }
    return dict(sorted(compounds.items(), key=lambda pair: (-pair[1]["units"], pair[0])))


def build_developers(default: list[dict], model: Model, compounds: dict[str, dict], moves: list) -> dict[str, dict]:
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
        premiums = []
        for record in items:
            unit = unit_for(record, model.reference_date)
            steps = model.path(unit) if unit else []
            district_step = next((s for s in steps if s["level"] == "district"), None)
            if district_step and len(steps) > 2 and model.grade(steps):
                premiums.append(steps[-1]["estimate"] - district_step["estimate"])
        own = [c for c in compounds.values() if c["developer"] and c["developer"]["key"] == key]
        tracked = [moved[r["id"]] for r in items if r["id"] in moved]
        developers[key] = {
            "key": key, "name": items[0]["developer"]["name"], "units": len(items),
            "premium_vs_district": round(math.exp(sum(premiums) / len(premiums)) - 1, 4) if len(premiums) >= 5 else None,
            "premium_basis": len(premiums),
            "compounds": [{"key": c["key"], "name": c["name"], "district": c["district"], "units": c["units"],
                           "premium_vs_district": c["premium_vs_district"], "grade": c["grade"]} for c in own],
            "districts": [{"name": name, "units": count}
                          for name, count in Counter(r["district"] for r in items).most_common()],
            "delivery_changes": {"tracked_units": sum(1 for r in items if r["delivery"]["date"]),
                                 "postponed": tracked.count(1), "brought_forward": tracked.count(-1)},
            "scope": scope(items), **_profile(items),
        }
    return dict(sorted(developers.items(), key=lambda pair: (-pair[1]["units"], pair[0])))


def build_districts(default: list[dict], model: Model, compounds: dict[str, dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in default:
        groups[slug(record["district"])].append(record)
    districts = {}
    for key, items in groups.items():
        name = majority(r["district"] for r in items)
        districts[key] = {
            "key": key, "name": name, "units": len(items),
            "classes": _classes(items, model, name, "", ""),
            "compound_count": sum(1 for c in compounds.values() if c["district_key"] == key),
            "scope": scope(items), **_profile(items),
        }
    return dict(sorted(districts.items(), key=lambda pair: (-pair[1]["units"], pair[0])))


def comparables(snapshot: Snapshot, record: dict, limit: int = 6) -> list[dict]:
    """Nearest listings by size from the same compound, else developer and district, else district."""
    pool = [r for r in snapshot.default if r["id"] != record.get("id") and r["class"] == record["class"]
            and r["payment"]["cash_equivalent"]]
    for match in (lambda r: record.get("compound_key") and r["compound_key"] == record["compound_key"],
                  lambda r: record.get("developer_key") and r["developer_key"] == record["developer_key"]
                  and r["district"] == record["district"],
                  lambda r: r["district"] == record["district"]):
        chosen = [r for r in pool if match(r)]
        if len(chosen) >= 3:
            break
    chosen.sort(key=lambda r: (abs(math.log(r["area_m2"] / record["area_m2"])), r["id"]))
    return [{**public_unit(r), "cash_ppm": round(r["payment"]["cash_equivalent"] / r["area_m2"])}
            for r in chosen[:limit]]


def detail(snapshot: Snapshot, record: dict, description: str | None) -> dict:
    unit = unit_for(record, snapshot.today)
    labels = {"class": record["class"], "district": record["district"],
              "developer": record["developer"]["name"] if record["developer"] else None,
              "compound": record["compound"]["name"] if record["compound"] else None}
    return {"unit": {**public_unit(record, full=True), "description": description},
            "breakdown": breakdown(snapshot.model, unit, labels) if unit and record["valuation"]["status"] == "valued" else None,
            "comparables": comparables(snapshot, record) if record["class"] else []}


def evaluate(snapshot: Snapshot, *, property_type: str, area: float, price: float, compound: str = "",
             developer: str = "", district: str = "", down_payment: float | None = None,
             installment_years: float | None = None, delivery: str = "", finishing: str = "") -> dict:
    """Value a unit the user describes. Unknown names fall back to the next level up."""
    kind = TYPE_ALIASES.get(property_type.strip().casefold(), property_type.strip().casefold())
    notes = []
    compound_key = slug(compound)
    entry = snapshot.compounds.get(compound_key)
    if compound_key and not entry:
        matches = [c for c in snapshot.compounds.values() if c["name"].casefold() == compound.strip().casefold()]
        entry = matches[0] if matches else None
        if not entry:
            notes.append("compound_not_found")
            compound_key = ""
    if entry:
        compound_key = entry["key"]
    developer_id = developer_key(developer)
    if developer_id and developer_id not in snapshot.developers:
        notes.append("developer_not_found")
        developer_id = ""
    if entry and entry["developer"]:
        developer_id = entry["developer"]["key"]
    district_name = entry["district"] if entry else None
    if not district_name and district:
        found = snapshot.districts.get(slug(canonical_district(district)))
        district_name = found["name"] if found else None
        if not found:
            notes.append("district_not_found")
    months = round(installment_years * 12) if installment_years else None
    plan = down_payment is not None and months
    payment = payment_terms(price, down_payment if plan else None, months if plan else None,
                            True if plan else None, cash_when_not_installment=True)
    delivery_date = f"{delivery}-01"[:10] if re.fullmatch(r"\d{4}(-\d{2})?", delivery or "") else None
    if delivery_date and len(delivery) == 4:
        delivery_date = f"{delivery}-06-30"
    ready = delivery.casefold() == "ready"
    record = {
        "id": None, "class": CLASSES.get(kind), "property_type": kind, "district": district_name,
        "compound_key": compound_key, "developer_key": developer_id, "area_m2": area, "price": price,
        "finishing_class": finishing_class(finishing), "delivery_date": delivery_date,
        "in_compound": bool(compound.strip()),
        "delivery_status": "ready" if ready else None, "payment": payment,
    }
    bucket, years = delivery_bucket(delivery_date, record["delivery_status"], snapshot.today)
    record["delivery"] = {"bucket": bucket, "date": delivery_date, "years": years}
    unit = unit_for(record, snapshot.today) if district_name else None
    result = valuation(snapshot.model, unit, payment, price, area, in_training=False)
    if not district_name:
        result = {"status": "insufficient", "reason": "Choose a known compound or district."}
    elif result["status"] == "insufficient" and not compound.strip():
        result["reason"] = "Too few comparable listings outside compounds in this district."
    developer_entry = snapshot.developers.get(developer_id)
    labels = {"class": record["class"], "district": district_name,
              "developer": developer_entry["name"] if developer_entry else None,
              "compound": entry["name"] if entry else None}
    return {
        "inputs": {"property_type": kind, "class": record["class"], "area_m2": area, "price": price,
                   "compound": {"key": entry["key"], "name": entry["name"]} if entry else None,
                   "developer": {"key": developer_id, "name": developer_entry["name"]} if developer_entry else None,
                   "district": district_name, "finishing_class": record["finishing_class"],
                   "delivery": record["delivery"], "price_per_m2": round(price / area)},
        "payment": payment, "valuation": result, "notes": notes,
        "breakdown": breakdown(snapshot.model, unit, labels) if unit and result["status"] == "valued" else None,
        "comparables": comparables(snapshot, record) if record["class"] and district_name else [],
        "unknowns": [u for u in unknowns(record) if u not in ("payment_terms", "installment_term")],
    }

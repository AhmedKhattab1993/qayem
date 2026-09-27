"""Batched Codex extraction of missing listing facts from title and description.

The model, effort, prompt, output format and batch size are the configuration
chosen by the benchmark in bench/enrichment/RESULTS.md (held-out precision
99% on the core fields): gpt-6-sol at low effort, the enrichment_spec.md
instructions, sparse JSON output and 40 listings per headless call. Every
proposed value is then checked against the listing's own text before it may
fill a column that the source left empty.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import cache
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path

from sqlalchemy import and_, delete, func, insert, inspect, or_, select, update
from sqlalchemy.engine import Engine

from .db import session_scope
from .models import Property, PropertyEnrichment, utcnow
from .normalization import to_western_digits
from .valuation import CLASSES
from .website_data import MAX_PRICE, MIN_PRICE


MODEL = "gpt-6-sol"
REASONING_EFFORT = "low"
PROMPT_VERSION = "v2"
SPEC_PATH = Path(__file__).with_name("enrichment_spec.md")
BATCH_SIZE = 40
TIMEOUT_SECONDS = 600
TIMEOUT_ATTEMPTS = 2
MAX_ATTEMPTS = 3  # a failed listing is retried on later runs, at most this many runs in total
STALE_CLAIM = timedelta(hours=6)  # a claim this old was left by a crashed run
CIRCUIT_BREAKER = 2  # consecutive fully failed batches that stop a run (outage, auth, quota)

# Columns a description can fill. is_multi_unit has no column: a multi-unit
# ad (a project or several units) describes no single unit, so nothing from
# it is applied.
INFERABLE_FIELDS = (
    "property_type", "is_resale", "price", "down_payment", "installment_months",
    "area_m2", "bedrooms", "bathrooms", "finishing", "delivery_status",
    "compound", "developer",
)
EXTRACTED_FIELDS = (*INFERABLE_FIELDS, "is_multi_unit")
# Fields the website gate or the valuation uses. A listing is only worth a
# call when one of these is missing; bedrooms, bathrooms and developer are
# then filled along the way.
VALUATION_FIELDS = (
    "property_type", "area_m2", "is_resale", "finishing", "delivery_status",
    "compound", "down_payment", "installment_months",
)
# Nawy generates both title and description from its structured payload, so
# the text holds nothing the parser has not already read. (Semsar's
# description is a template read by its parser, but its titles are free text.)
TEMPLATED_SOURCES = {"nawy", "nawy_primary"}
# Structured findings about a listing, stored on its enrichment record. The
# website hides listings flagged price_is_down_payment: their shown price is
# only the down payment.
FLAG_NOTES = {
    "multi_unit": "Multi-unit ad: nothing applied",
    "price_is_down_payment": "Listing price equals the stated down payment",
}
TEXT_FIELDS = {"property_type", "finishing", "delivery_status", "compound", "developer"}
PROPERTY_TYPES = {
    "apartment", "villa", "townhouse", "twinhouse", "penthouse",
    "duplex", "studio", "chalet", "roof", "land", "building",
    "office", "shop", "clinic", "warehouse", "farm", "factory",
    "house", "cabin", "loft", "pharmacy",
}
FINISHING = {
    "finished", "semi_finished", "core_shell", "lux", "super_lux",
    "extra_super_lux", "flexi_finished",
}
DELIVERY = {"ready_to_move", "under_construction"}
TEXT_LIMITS = {"compound": 191, "developer": 191}
PROPERTY_TYPE_EVIDENCE = {
    "apartment": r"apartment|\bflat\b|شقة|شقه|شقق|شقت",
    "villa": r"villa|فيلا|فيلات|فلل|ڤيلا",
    "townhouse": r"town\s*house|تاون\s*هاوس",
    "twinhouse": r"twin\s*house|توين\s*هاوس",
    "penthouse": r"pent\s*house|بنت\s*هاوس|بينت\s*هاوس|بنتهاوس|بنتاهاوس",
    "duplex": r"duplex|دوبل[يِ]?كس|دوبلكس",
    "studio": r"studio|ستوديو|استديو|استوديو",
    "chalet": r"chalet|شاليه|شالية|شاليهات",
    "roof": r"\broof\b|روف|رووف",
    "land": r"\bland\b|\bplot\b|أرض|ارض",
    "building": r"\bbuilding\b|عمارة|عماره|مبنى|بناية",
    "office": r"\boffice\b|مكتب|إداري|اداري",
    "shop": r"\bshop\b|\bretail\b|محل|متجر|تجاري",
    "clinic": r"\bclinic\b|عيادة|عياده",
    "warehouse": r"\bwarehouse\b|مخزن|مستودع",
    "farm": r"\bfarm\b|مزرعة|مزرعه",
    "factory": r"\bfactory\b|مصنع",
    "house": r"\bhouse\b|منزل|بيت",
    "cabin": r"\bcabin\b|كابينة|كابينه",
    "loft": r"\bloft\b|لوفت",
    "pharmacy": r"\bpharmacy\b|صيدلية|صيدليه",
}
FINISHING_EVIDENCE = {
    "finished": r"fully\s*finished|finished|متشطب|مشطب|تشطيب\s*كامل|كامل[ةه]?\s*التشطيب",
    "semi_finished": r"semi[\s-]*finished|نصف\s*تشطيب|نص\s*تشطيب",
    "core_shell": r"core\s*(?:and|&)\s*shell|unfinished|بدون\s*تشطيب|على\s*الطوب|علي\s*الطوب",
    "lux": r"\blux\b|لوكس",
    "super_lux": r"super\s*lux|سوبر\s*لوكس",
    "extra_super_lux": r"(?:extra|ultra)\s*super\s*lux|(?:اكسترا|إكسترا|الترا|ألترا|التر)\s*سوبر\s*لوكس",
    "flexi_finished": r"flexi[\s-]*finished",
}
DELIVERY_EVIDENCE = {
    "ready_to_move": r"ready\s*to\s*(?:move|occupy)|immediate\s*delivery|استلام\s*فور|تسليم\s*فور"
                     r"|جاهز[ةه]?\s*(?:لل|ع)|#استلام_فور|للسكن\s*الفور|سكن\s*فور",
    "under_construction": r"under\s*construction|delivery\s*(?:in\s*)?20\d\d|قيد\s*ال[اإ]نشاء|تحت\s*ال[اإ]نشاء"
                          r"|(?:استلام|تسليم|الاستلام|التسليم)\s*(?:بعد|خلال|في|علي|على|سن|20\d\d|\d)",
}
RESALE_EVIDENCE = (
    r"\bresale\b|ريسيل|إعادة\s*بيع|اعادة\s*بيع|تنازل|متنازل|أقل\s*من\s*سعر\s*(?:الشرك|المطور)"
    r"|اقل\s*من\s*سعر\s*(?:الشرك|المطور)|مدفوع|المتبقي|المتبقى|تكمل[ةه]\s*ال[أا]قساط"
    r"|خالص[ةه]\s*ال[أا]قساط|willing\s*to\s*lose|what\s*(?:was\s*)?paid"
)
PRIMARY_EVIDENCE = (
    r"من\s*المطور\s*مباشر|من\s*الشرك[ةه]\s*(?:المالك[ةه]\s*|المطور[ةه]\s*)?مباشر"
    r"|طرح\s*جديد|سعر\s*(?:ال)?طرح|[اأ]ول\s*طرح|\blaunch\b"
)

# Cheap pre-filter: the text must mention at least one missing valuation
# field before a listing is sent. On the benchmark it kept 261 of 266 gold
# facts; the misses were compound names written without "compound".
FIELD_SIGNALS = {
    "property_type": "|".join(PROPERTY_TYPE_EVIDENCE.values()),
    "area_m2": r"\d\s*(?:م\b|م2|م²|متر|m2|m²|sqm|meter)",
    "is_resale": RESALE_EVIDENCE + "|" + PRIMARY_EVIDENCE,
    "finishing": "|".join(FINISHING_EVIDENCE.values()) + r"|تشطيب",
    "delivery_status": "|".join(DELIVERY_EVIDENCE.values()) + r"|استلام|تسليم",
    "compound": r"كمبوند|كومباوند|كمباوند|كومبوند|compound|مشروع|project|residence|\bpark\b|hills"
                r"|city\b|سيتي|هايتس|heights",
    "down_payment": r"مقدم|دفع[ةه]|down\s*payment|deposit|كاش|مطلوب",
    "installment_months": r"قسط|تقسيط|اقساط|أقساط|سنوات|سنين|installment|years",
}


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string", "enum": list(EXTRACTED_FIELDS)},
                                "value": {"type": "string"},
                            },
                            "required": ["field", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "facts"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["listings"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Task:
    property_id: int
    title: str
    description: str
    missing: tuple[str, ...]
    price: float | None = None  # the listing's current price, for consistency checks

    @property
    def text(self) -> str:
        return listing_text(self.title, self.description)


@dataclass(frozen=True)
class Result:
    property_id: int
    status: str
    applied: int
    error: str | None = None


def listing_text(title: str | None, description: str | None) -> str:
    return f"{title or ''}\n{description or ''}".strip()


def description_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_missing(field: str, value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip().casefold()
        return not stripped or stripped in {"-", "unknown", "n/a", "null"}
    return False


def missing_fields(prop) -> tuple[str, ...]:
    return tuple(name for name in INFERABLE_FIELDS if is_missing(name, getattr(prop, name)))


def worth_enriching(title: str | None, description: str | None, missing: Collection[str]) -> bool:
    """Does the text mention at least one missing field the website or valuation uses?"""
    text = listing_text(title, description)
    haystack = f"{to_western_digits(_normalized_text(text))}\n{to_western_digits(_folded(text))}"
    return any(
        re.search(FIELD_SIGNALS[field], haystack, re.IGNORECASE)
        for field in VALUATION_FIELDS if field in missing
    )


def _candidates(engine: Engine, source: str | None, retry_failed: bool, dry_run: bool,
                since: datetime | None, exclude_ids: Collection[int]):
    """Listings the website could show once enriched, newest first."""
    missing_conditions = [getattr(Property, name).is_(None) for name in VALUATION_FIELDS]
    missing_conditions.extend(
        func.lower(func.trim(getattr(Property, name))).in_(("", "-", "unknown", "n/a", "null"))
        for name in TEXT_FIELDS if name in VALUATION_FIELDS
    )
    columns = {"id", "title", "description", "price", *INFERABLE_FIELDS}
    query = select(*(getattr(Property, name) for name in sorted(columns))).where(
        Property.status == "active",
        Property.description.is_not(None),
        func.trim(Property.description) != "",
        Property.source.not_in(TEMPLATED_SOURCES),
        Property.purpose == "sale",
        func.upper(Property.currency) == "EGP",
        Property.price.between(MIN_PRICE, MAX_PRICE),
        or_(Property.property_type.is_(None), func.trim(Property.property_type) == "",
            func.lower(Property.property_type).in_(list(CLASSES))),
        or_(*missing_conditions),
    )
    if retry_failed:
        if not inspect(engine).has_table(PropertyEnrichment.__tablename__):
            return None
        query = query.join(
            PropertyEnrichment, PropertyEnrichment.property_id == Property.id
        ).where(PropertyEnrichment.status == "failed")
    elif not dry_run or inspect(engine).has_table(PropertyEnrichment.__tablename__):
        query = query.outerjoin(
            PropertyEnrichment, PropertyEnrichment.property_id == Property.id
        ).where(or_(PropertyEnrichment.property_id.is_(None), _retriable()))
    if exclude_ids:
        query = query.where(Property.id.not_in(exclude_ids))
    if source:
        query = query.where(Property.source == source)
    if since:
        query = query.where(Property.first_seen_at >= since)
    return query.order_by(Property.first_seen_at.desc(), Property.id.desc())


def _retriable():
    """Records a normal run may take again: failed with attempts left, or abandoned claims."""
    stale_before = utcnow() - STALE_CLAIM
    return or_(
        and_(PropertyEnrichment.status == "failed",
             func.coalesce(PropertyEnrichment.attempts, 1) < MAX_ATTEMPTS),
        and_(PropertyEnrichment.status == "claimed", PropertyEnrichment.claimed_at < stale_before),
    )


def count_eligible(engine: Engine, source: str | None = None, since: datetime | None = None) -> int:
    """How many listings a full run would send to the model."""
    with session_scope(engine) as session:
        query = _candidates(engine, source, False, True, since, ())
        return sum(
            1 for row in session.execute(query).all()
            if worth_enriching(row.title, row.description, missing_fields(row))
        )


def claim_batch(
    engine: Engine, source: str | None = None, *, dry_run: bool = False,
    retry_failed: bool = False, exclude_ids: Collection[int] = (),
    since: datetime | None = None,
) -> list[Task]:
    """Reserve up to BATCH_SIZE worthwhile listings, or explicitly retry failed ones."""
    with session_scope(engine) as session:
        query = _candidates(engine, source, retry_failed, dry_run, since, exclude_ids)
        if query is None:
            return []
        # Read every candidate before the first claim is written: a write while a
        # read cursor is still open cannot wait for the lock in WAL mode and
        # fails at once with "database is locked" when another batch has committed.
        rows = session.execute(query).all()
        tasks: list[Task] = []
        for prop in rows:
            missing = missing_fields(prop)
            if not worth_enriching(prop.title, prop.description, missing):
                continue
            task = Task(prop.id, prop.title or "", prop.description, missing, prop.price)
            if not dry_run:
                claim_values = dict(
                    status="claimed", done=False, claimed_at=utcnow(),
                    description_hash=description_hash(task.text),
                    model=MODEL, reasoning_effort=REASONING_EFFORT,
                    prompt_version=PROMPT_VERSION,
                )
                claimed = None
                if not retry_failed:
                    claimed = session.execute(
                        insert(PropertyEnrichment).values(
                            property_id=prop.id, attempts=1, **claim_values
                        ).prefix_with("OR IGNORE")
                    )
                if claimed is None or claimed.rowcount != 1:
                    # An existing record: take it back only if it is (still) retriable.
                    condition = (PropertyEnrichment.status == "failed") if retry_failed else _retriable()
                    claimed = session.execute(
                        update(PropertyEnrichment)
                        .where(PropertyEnrichment.property_id == prop.id, condition)
                        .values(**claim_values, finished_at=None, error=None, flags=None,
                                proposed=None, applied=None,
                                attempts=func.coalesce(PropertyEnrichment.attempts, 1) + 1)
                    )
                if claimed.rowcount != 1:
                    continue
            tasks.append(task)
            if len(tasks) == BATCH_SIZE:
                break
        return tasks


def revoke_outdated(engine: Engine, *, dry_run: bool = False) -> list[dict]:
    """Undo fills made by an earlier prompt version and forget those records.

    A filled column is reset only while it still holds the value the old
    enrichment wrote; the record is deleted so the listing becomes eligible
    for the current configuration. Returns what was (or would be) reverted.
    """
    reverted: list[dict] = []
    with session_scope(engine) as session:
        records = session.execute(
            select(PropertyEnrichment).where(
                or_(PropertyEnrichment.prompt_version.is_(None),
                    PropertyEnrichment.prompt_version != PROMPT_VERSION))
        ).scalars().all()
        for record in records:
            prop = session.get(Property, record.property_id)
            for field, value in (record.applied or {}).items():
                if prop is None or not hasattr(prop, field) or getattr(prop, field) != value:
                    continue
                reverted.append({"property_id": prop.id, "field": field, "value": value,
                                 "model": record.model})
                if not dry_run:
                    setattr(prop, field, None)
        if not dry_run and records:
            session.execute(delete(PropertyEnrichment).where(
                PropertyEnrichment.property_id.in_([r.property_id for r in records])))
    return reverted


def _prompt(tasks: list[Task]) -> str:
    payload = [{"id": t.property_id, "title": t.title, "description": t.description} for t in tasks]
    return (
        "Extract the fields for each of these listings. Return exactly one entry per id "
        "and only the fields that are stated (omit null fields).\n"
        + json.dumps(payload, ensure_ascii=False)
    )


@cache
def _lean_flags() -> tuple[str, ...]:
    """Disable every optional Codex feature: the call then carries ~2.5k tokens of overhead, not ~12k."""
    try:
        listing = subprocess.run(
            ["codex", "features", "list"], capture_output=True, text=True, timeout=30, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ()
    flags: list[str] = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == "true" and "removed" not in parts:
            flags += ["--disable", parts[0]]
    return tuple(flags)


def invoke_codex(tasks: list[Task]) -> dict[int, list[dict]]:
    """Run one fresh, isolated headless Codex session for a batch of listings.

    Returns the facts proposed per listing id. Listings the answer omits are
    simply absent; the caller decides whether to ask again.
    """
    with tempfile.TemporaryDirectory(prefix="qayem-enrich-") as tmp:
        root = Path(tmp)
        schema_path = root / "output-schema.json"
        output_path = root / "answer.json"
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA), encoding="utf-8")
        command = [
            "codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--sandbox", "read-only",
            "--model", MODEL, "-c", f'model_reasoning_effort="{REASONING_EFFORT}"',
            "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
            "-c", f'model_instructions_file="{SPEC_PATH}"', *_lean_flags(),
            "--cd", str(root), "--output-schema", str(schema_path),
            "--output-last-message", str(output_path), "-",
        ]
        for attempt in range(TIMEOUT_ATTEMPTS):
            output_path.unlink(missing_ok=True)
            try:
                completed = subprocess.run(
                    command, input=_prompt(tasks), text=True, encoding="utf-8",
                    capture_output=True, timeout=TIMEOUT_SECONDS, check=False,
                )
                break
            except subprocess.TimeoutExpired as exc:
                if attempt + 1 == TIMEOUT_ATTEMPTS:
                    raise RuntimeError(
                        f"Codex timed out after {TIMEOUT_SECONDS}s "
                        f"on {TIMEOUT_ATTEMPTS} attempts"
                    ) from exc
                time.sleep(5)
            except OSError as exc:
                raise RuntimeError(f"Codex could not start: {exc.strerror or type(exc).__name__}") from exc
        if completed.returncode != 0:
            raise RuntimeError(f"Codex exited with status {completed.returncode}")
        if not output_path.is_file():
            raise RuntimeError("Codex did not write its final response")
        try:
            answer = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex response was not valid JSON") from exc
        if not isinstance(answer, dict) or not isinstance(answer.get("listings"), list):
            raise RuntimeError("Codex response did not match the expected schema")
        wanted = {task.property_id for task in tasks}
        facts: dict[int, list[dict]] = {}
        for item in answer["listings"]:
            if (isinstance(item, dict) and item.get("id") in wanted
                    and isinstance(item.get("facts"), list) and item["id"] not in facts):
                facts[item["id"]] = [fact for fact in item["facts"] if isinstance(fact, dict)]
        return facts


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": None})


def _folded(value: str) -> str:
    """Spelling-insensitive form for matching names: hamza, taa marbuta, punctuation."""
    value = _normalized_text(value).translate(_ARABIC_FOLD)
    value = re.sub(r"[#_()\[\]\"'«»,،.…\-–—|/*:!؟?]+", " ", value)
    return " ".join(value.split())


_GENERIC_COMPOUND_WORDS = {
    "ساكن", "عايش", "بالفعل", "سكني", "متكامل", "كامل", "الخدمات", "خدمات",
    "سياحي", "راقي", "ارقي", "اميز", "مميز", "كمبوند", "الكمبوند", "كومباوند",
    "الكومباوند", "compound", "the", "مجمع", "المجمع", "في", "من", "داخل",
}


def _is_generic_compound(name: str) -> bool:
    return all(word.lstrip("و") in _GENERIC_COMPOUND_WORDS for word in _folded(name).split())


def _money_amounts(text: str) -> set[float]:
    """Explicit amounts in the text, excluding percentages; scales thousand/million words."""
    quoted = to_western_digits(_normalized_text(text))
    amounts: set[float] = set()
    pattern = r"(?<![\d.,])(\d[\d,.]*)(?:\s*)(مليون|millions?|ألف|الف|thousands?)?"
    for match in re.finditer(pattern, quoted, re.IGNORECASE):
        token, unit = match.group(1).rstrip(".,"), (match.group(2) or "").casefold()
        if re.match(r"\s*[%٪]", quoted[match.end():]):
            continue
        try:
            if unit and token.count(".") == 1 and token.count(",") == 0:
                number = float(token)
            elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
                number = float(token.replace(",", "").replace(".", ""))
            else:
                number = float(token.replace(",", ""))
        except ValueError:
            continue
        # Ads sometimes write "850,000 ألف" with a redundant "thousand" word.
        redundant_thousand = (
            unit.startswith(("ألف", "الف", "thousand"))
            and number >= 1_000 and ("," in token or "." in token)
        )
        scale = (1_000_000 if unit.startswith(("مليون", "million")) else
                 1_000 if unit.startswith(("ألف", "الف", "thousand"))
                 and not redundant_thousand else 1)
        amount = number * scale
        if scale == 1_000_000:
            # "2 مليون ونص", "مليون و400 ألف": the model is asked to add these parts.
            rest = quoted[match.end():match.end() + 20]
            if re.match(r"\s*و\s*(?:نص|نصف)", rest):
                amounts.add(amount + 500_000)
            elif extra := re.match(r"\s*و\s*(\d{2,3})\s*(?:ألف|الف)", rest):
                amounts.add(amount + int(extra.group(1)) * 1_000)
        amounts.add(amount)
    # A bare "مليون" means one million: "مليون و400 ألف", "ب مليون".
    bare = r"(?:^|[^\d\s.,])\s*مليون(?:\s*و\s*(?:(نص|نصف)|(\d{2,3})\s*(?:ألف|الف)))?"
    for match in re.finditer(bare, quoted):
        extra = 500_000 if match.group(1) else int(match.group(2)) * 1_000 if match.group(2) else 0
        amounts.add(1_000_000 + extra)
    return amounts


def _installment_terms(text: str) -> set[int]:
    quoted = to_western_digits(_normalized_text(text))
    terms: set[int] = set()
    for match in re.finditer(
        r"(?<!\d)(\d+)\s*(سنوات|سنة|سنه|سنين|شهور|شهر|شهرا|years?|months?)\b(\s*و\s*نص)?",
        quoted, re.IGNORECASE,
    ):
        count = int(match.group(1))
        unit = match.group(2).casefold()
        months = count * 12 if unit.startswith(("سن", "year")) else count
        terms.add(months)
        if match.group(3) and unit.startswith(("سن", "year")):
            terms.add(months + 6)
    return terms


_COUNT_WORDS = {
    "واحد": 1, "واحده": 1, "اثنين": 2, "اتنين": 2, "ثلاث": 3, "ثلاثه": 3, "تلات": 3, "تلاته": 3,
    "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6,
}


def _counts(text: str, label: str) -> set[int]:
    """Room/bath counts written next to their label: '3 غرف', 'ثلاثة حمام', 'غرف: 3'."""
    quoted = to_western_digits(_normalized_text(text))
    counts = {int(m.group(1)) for m in re.finditer(rf"(\d+)\s*(?:{label})", quoted, re.IGNORECASE)}
    counts |= {int(m.group(1)) for m in re.finditer(rf"(?:{label})\s*[:：=]\s*(\d+)", quoted, re.IGNORECASE)}
    folded = to_western_digits(_folded(text))
    words = "|".join(_COUNT_WORDS)
    counts |= {_COUNT_WORDS[m.group(1)] for m in re.finditer(rf"(?<!\S)و?({words})\s+(?:{label})", folded)}
    return counts


def _supported(field: str, value: object, text: str) -> bool:
    """Is the proposed value grounded in the listing's own title and description?"""
    folded = _folded(text)
    digits = to_western_digits(_normalized_text(text))
    # Patterns are matched against the text as written and in a hamza-folded,
    # punctuation-free form ("إستلام", "#استلام_فوري" -> "استلام فوري").
    haystack = f"{digits}\n{to_western_digits(folded)}"

    def has(pattern: str) -> bool:
        return bool(re.search(pattern, haystack, re.IGNORECASE))

    if field == "property_type":
        if value == "house" and has(r"town\s*house|twin\s*house|تاون\s*هاوس|توين\s*هاوس"):
            return False
        return has(PROPERTY_TYPE_EVIDENCE[value])
    if field == "finishing":
        if value == "finished" and has(r"semi[\s-]*finished|unfinished|نصف\s*تشطيب|نص\s*تشطيب|بدون\s*تشطيب"):
            return False
        if value == "lux" and has(r"super\s*lux|سوبر\s*لوكس"):
            return False
        if value == "super_lux" and has(FINISHING_EVIDENCE["extra_super_lux"]):
            return False
        return has(FINISHING_EVIDENCE[value])
    if field == "delivery_status":
        return has(DELIVERY_EVIDENCE[value])
    if field in {"compound", "developer"}:
        name = _folded(str(value))
        # The name must appear as whole words; Arabic proclitics may be attached ("بهايد بارك").
        if len(name) < 2 or not re.search(rf"(?:^|\s)[وبلفك]?{re.escape(name)}(?:\s|$)", folded):
            return False
        return field != "compound" or not _is_generic_compound(name)
    if field == "is_resale":
        return has(RESALE_EVIDENCE) if value is True else has(PRIMARY_EVIDENCE)
    if field == "price":
        return float(value) in _money_amounts(text)
    if field == "down_payment":
        return (float(value) >= 1_000 and float(value) in _money_amounts(text)
                and has(r"down\s*payment|deposit|مقدم|دفع[ةه]|كاش|المطلوب|مطلوب"))
    if field == "installment_months":
        return (int(value) in _installment_terms(text)
                and has(r"installment|payment\s*plan|قسط|اقساط|أقساط|تقسيط|سداد|الباقي|المتبقي"))
    if field == "area_m2":
        plain = re.sub(r"(?<=\d)[,٬](?=\d{3})", "", digits)
        number = f"{float(value):g}"
        return bool(re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", plain))
    if field == "bedrooms":
        if value == 2 and has(r"غرفتين|غرفتي\b|حجرتين|two\s*bed"):
            return True
        return value in _counts(text, r"غرف|غرفة|غرفه|حجر|bed\s*rooms?|bedrooms?|beds?|\bbr\b|نوم")
    if field == "bathrooms":
        if value == 2 and has(r"حمامين|two\s*bath"):
            return True
        label = r"حمام|حمامات|تويلت|bath\s*rooms?|bathrooms?|baths?"
        counts = _counts(text, label)
        if value == 1 and not counts and has(r"حمام|\bbath"):
            return True  # "غرفتين وصالة وحمام": one bathroom named without a number
        return value in counts
    return False


def _validated_value(field: str, raw: str) -> object | None:
    value = raw.strip()
    if not value:
        return None
    if field in {"is_resale", "is_multi_unit"}:
        return {"true": True, "false": False}.get(value.casefold())
    if field in {"bedrooms", "bathrooms", "installment_months"}:
        if not re.fullmatch(r"\d+", value):
            return None
        number = int(value)
        maximum = 360 if field == "installment_months" else 20
        return number if (1 if field != "bedrooms" else 0) <= number <= maximum else None
    if field in {"price", "down_payment", "area_m2"}:
        value = value.replace(",", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", value):
            return None
        number = float(value)
        maximum = 1_000_000_000 if field != "area_m2" else 20_000
        return number if 0 < number <= maximum else None
    if field == "property_type":
        canonical = value.casefold().replace(" ", "").replace("-", "")
        return canonical if canonical in PROPERTY_TYPES else None
    if field == "finishing":
        canonical = value.casefold().replace(" ", "_").replace("-", "_")
        return canonical if canonical in FINISHING else None
    if field == "delivery_status":
        canonical = value.casefold().replace(" ", "_").replace("-", "_")
        return canonical if canonical in DELIVERY else None
    if field in TEXT_LIMITS:
        value = value.strip(" #_\"'«»()")
        if len(value) > TEXT_LIMITS[field] or value.casefold() in {"unknown", "n/a", "-", ""}:
            return None
        return value
    return None


def validated_facts(facts: list[dict], task: Task) -> tuple[dict[str, object], list[str]]:
    """Keep proposals that parse, are grounded in the text and fill a missing column.

    Returns the values to apply and flags about the listing (FLAG_NOTES): a
    multi-unit ad gets nothing applied, and a stated down payment equal to the
    listing's price means that price is probably the down payment.
    """
    proposed: dict[str, object] = {}
    duplicates: set[str] = set()
    for fact in facts:
        field, raw = fact.get("field"), fact.get("value")
        if field not in EXTRACTED_FIELDS or not isinstance(raw, str):
            continue
        value = _validated_value(field, raw)
        if value is None:
            continue
        if field in proposed and proposed[field] != value:
            duplicates.add(field)
        proposed[field] = value
    for field in duplicates:
        proposed.pop(field)
    if proposed.get("is_multi_unit") is True:
        return {}, ["multi_unit"]
    flags = []

    values = {
        field: value for field, value in proposed.items()
        if field in task.missing and _supported(field, value, task.text)
    }
    price = task.price if task.price is not None else values.get("price")
    down = values.get("down_payment")
    if down is not None and price is not None and down >= price:
        values.pop("down_payment")
        if task.price is not None and down == task.price:
            flags.append("price_is_down_payment")
    if values.get("price") is not None and task.price is None:
        extracted_down = proposed.get("down_payment")
        if extracted_down is not None and extracted_down >= values["price"]:
            values.pop("price")
    return values, flags


def _record_results(engine: Engine, tasks: list[Task], answers: dict[int, list[dict]],
                    error: str | None) -> list[Result]:
    results = []
    with session_scope(engine) as session:
        for task in tasks:
            record = session.get(PropertyEnrichment, task.property_id)
            prop = session.get(Property, task.property_id)
            if record is None or prop is None:
                results.append(Result(task.property_id, "failed", 0, "listing or claim disappeared"))
                continue
            record.finished_at = utcnow()
            record.done = True
            if task.property_id not in answers:
                record.status = "failed"
                record.error = error or "Codex returned no answer for this listing"
                results.append(Result(task.property_id, "failed", 0, record.error))
                continue
            facts = answers[task.property_id]
            record.proposed = facts
            record.applied = {}
            record.status = "done"
            if description_hash(listing_text(prop.title, prop.description)) != record.description_hash:
                record.error = "Listing text changed during invocation"
                results.append(Result(task.property_id, "done", 0, record.error))
                continue
            values, flags = validated_facts(facts, task)
            record.flags = flags or None
            record.error = "; ".join(FLAG_NOTES[flag] for flag in flags) or None
            applied = {}
            for field, value in values.items():
                if not is_missing(field, getattr(prop, field)):
                    continue
                setattr(prop, field, value)
                applied[field] = value
                if field == "is_resale":
                    prop.resale_evidence = "description"
                    applied["resale_evidence"] = "description"
            record.applied = applied
            results.append(Result(
                task.property_id, "done", len(applied) - int("resale_evidence" in applied),
            ))
    return results


def process_batch(engine: Engine, tasks: list[Task]) -> list[Result]:
    """One Codex call for the batch; listings missing from the answer are asked once more."""
    answers: dict[int, list[dict]] = {}
    error = None
    try:
        answers = invoke_codex(tasks)
        unanswered = [task for task in tasks if task.property_id not in answers]
        if unanswered:
            answers.update(invoke_codex(unanswered))
    except RuntimeError as exc:
        error = str(exc)
    return _record_results(engine, tasks, answers, error)


def run_batches(
    engine: Engine, batches: int, source: str | None = None,
    on_batch: Callable[[int, list[Result]], None] | None = None,
    *, retry_failed: bool = False, workers: int = 4, since: datetime | None = None,
    deadline: float | None = None, on_stop: Callable[[str], None] | None = None,
) -> list[Result]:
    """Claim batches of BATCH_SIZE and keep at most ``workers`` Codex calls running.

    No new batch starts after ``deadline`` (a time.monotonic() value) or after
    CIRCUIT_BREAKER consecutive batches failed entirely; running ones finish.
    A listing is attempted at most once per run.
    """
    if shutil.which("codex") is None:
        raise RuntimeError("Codex CLI is not installed or not on PATH")
    results: list[Result] = []
    claimed_batches = 0
    reported = 0
    exhausted = False
    failed_in_a_row = 0
    attempted_ids: set[int] = set()

    def stop(reason: str) -> None:
        nonlocal exhausted
        if not exhausted and on_stop:
            on_stop(reason)
        exhausted = True
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def submit() -> None:
            nonlocal claimed_batches, exhausted
            if exhausted or (batches != 0 and claimed_batches >= batches):
                return
            if deadline is not None and time.monotonic() >= deadline:
                stop("time budget reached")
                return
            tasks = claim_batch(
                engine, source, retry_failed=retry_failed, exclude_ids=attempted_ids, since=since,
            )
            if not tasks:
                exhausted = True
                return
            claimed_batches += 1
            attempted_ids.update(task.property_id for task in tasks)
            pending[pool.submit(process_batch, engine, tasks)] = tasks

        for _ in range(workers):
            submit()
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                tasks = pending.pop(future)
                try:
                    batch_results = future.result()
                except Exception as exc:
                    batch_results = [
                        Result(task.property_id, "failed", 0, f"worker failed: {type(exc).__name__}")
                        for task in tasks
                    ]
                results.extend(batch_results)
                reported += 1
                if on_batch:
                    on_batch(reported, batch_results)
                failed_in_a_row = failed_in_a_row + 1 if all(
                    r.status == "failed" for r in batch_results) else 0
                if failed_in_a_row >= CIRCUIT_BREAKER:
                    stop(f"{failed_in_a_row} batches in a row failed: {batch_results[0].error}")
                submit()
    return results


def enrichment_health(engine: Engine, now: datetime | None = None) -> dict:
    """Backlog, recent failures and abandoned claims, judged like a source's health."""
    now = now or utcnow()
    day_ago = now - timedelta(hours=24)
    backlog = count_eligible(engine)
    with session_scope(engine) as session:
        finished = session.execute(
            select(PropertyEnrichment.status, func.count())
            .where(PropertyEnrichment.finished_at >= day_ago)
            .group_by(PropertyEnrichment.status)).all()
        last = session.scalar(select(func.max(PropertyEnrichment.finished_at)))
        stale = session.scalar(select(func.count()).select_from(PropertyEnrichment).where(
            PropertyEnrichment.status == "claimed", PropertyEnrichment.claimed_at < now - STALE_CLAIM))
    counts = dict(finished)
    done, failed = counts.get("done", 0), counts.get("failed", 0)
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if failed >= 10 and failed > 0.2 * (done + failed):
        state, detail = "failing", f"{failed} of {done + failed} listings failed in 24 h"
    elif backlog and (last is None or now - last > timedelta(hours=36)):
        state, detail = "stale", f"{backlog} listings waiting; last enrichment " + (
            f"{int((now - last).total_seconds() // 3600)} h ago" if last else "never")
    else:
        state, detail = "ok", f"{done} done, {failed} failed in 24 h; {backlog} waiting"
    if stale:
        detail += f"; {stale} abandoned claims"
    return {"state": state, "detail": detail, "backlog": backlog, "done_24h": done,
            "failed_24h": failed, "abandoned_claims": stale,
            "last_finished": last.isoformat() if last else None}

"""Canonical compound and developer names for free-text source spellings.

AqarExit publishes the compound and developer as the seller typed them: Badya appears as
«باديا», «بادية», «Badya» and «باديه», under «بالم هيلز», «Palm hills» or the chairman's
name. One Pi pass maps each distinct (compound, developer) spelling pair to a canonical
English name, the Arabic name, and — when the compound is listed on Nawy — Nawy's exact
compound name, which is how the developers' current prices are matched to resale units.

Answers are validated before they are stored: a reference must be a real Nawy compound of
the same developer. Only new spelling pairs are sent on later runs, so the nightly cost
is a handful of names. The website reads the table; it never calls the model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import time

from sqlalchemy import select
from sqlalchemy.engine import Engine

from .config import active_sources, benchmark_sources
from .db import session_scope
from .ai import MODEL, REASONING_EFFORT, run_pi
from .models import EntityAlias, Property, utcnow
from .valuation import alias_key, developer_key

PROMPT_VERSION = "v2"  # v2: Nawy's launch sub-project names resolve to their compound
SPEC_PATH = Path(__file__).with_name("entity_spec.md")
BATCH_SIZE = 120
TIMEOUT_SECONDS = 900
MAX_ATTEMPTS = 3  # a pair the model failed on is retried on later runs, at most this often
CIRCUIT_BREAKER = 2
# Sources whose names are the reference: Nawy names each compound once, in English, with its developer.
REFERENCE_SOURCES = ("nawy", "nawy_primary")
CONFIDENCE = ("high", "medium", "low")
MAX_NAME = 200

_NULLABLE = {"type": ["string", "null"]}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["compound", "not_compound"]},
                    "compound": _NULLABLE, "compound_ar": _NULLABLE,
                    "developer": _NULLABLE, "developer_ar": _NULLABLE,
                    "reference": _NULLABLE,
                    "confidence": {"type": "string", "enum": list(CONFIDENCE)},
                },
                "required": ["id", "kind", "compound", "compound_ar", "developer", "developer_ar",
                             "reference", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _clean(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:MAX_NAME] if value else None


@dataclass
class Pair:
    """One spelling pair as published, with how many listings use it."""
    key: str
    compound: str
    developer: str | None
    district: str | None
    listings: int


@dataclass
class Reference:
    compounds: dict[str, dict] = field(default_factory=dict)  # exact name → {developer, area, units}
    developers: list[str] = field(default_factory=list)


def reference(engine: Engine) -> Reference:
    """Nawy's compounds (name, developer, area) and developers."""
    names: dict[str, Counter] = defaultdict(Counter)
    areas: dict[str, Counter] = defaultdict(Counter)
    units: Counter = Counter()
    developers: Counter = Counter()
    with session_scope(engine) as session:
        rows = session.execute(select(Property.compound, Property.developer, Property.district)
                               .where(Property.source.in_(REFERENCE_SOURCES))).all()
    for compound, developer, district in rows:
        name = _clean(compound)
        if not name:
            continue
        units[name] += 1
        if developer := _clean(developer):
            names[name][developer] += 1
            developers[developer] += 1
        if district := _clean(district):
            areas[name][district] += 1
    compounds = {name: {"developer": names[name].most_common(1)[0][0] if names[name] else None,
                        "area": areas[name].most_common(1)[0][0] if areas[name] else None, "units": count}
                 for name, count in sorted(units.items())}
    return Reference(compounds, [name for name, _ in developers.most_common()])


def spelling_pairs(engine: Engine) -> list[Pair]:
    """Every compound/developer spelling pair among active listings of the sources in use and the
    benchmarks: Nawy names launches by sub-project («Sealine - Seashore»), which resolve to their compound."""
    sources = active_sources()
    query = select(Property.compound, Property.developer, Property.district).where(
        Property.status == "active", Property.compound.is_not(None))
    if sources is not None:
        query = query.where(Property.source.in_(sources | benchmark_sources()))
    grouped: dict[str, list] = defaultdict(list)
    with session_scope(engine) as session:
        for compound, developer, district in session.execute(query):
            if key := alias_key(compound, developer):
                grouped[key].append((_clean(compound), _clean(developer), _clean(district)))
    pairs = []
    for key, rows in grouped.items():
        compound, developer = Counter((c, d) for c, d, _ in rows).most_common(1)[0][0]
        districts = Counter(d for _, _, d in rows if d)
        pairs.append(Pair(key, compound, developer, districts.most_common(1)[0][0] if districts else None, len(rows)))
    pairs.sort(key=lambda p: (-p.listings, p.key))
    return pairs


def pending(engine: Engine, retry_failed: bool = True) -> list[Pair]:
    """Pairs never resolved, or failed fewer than MAX_ATTEMPTS times; most-listed first."""
    with session_scope(engine) as session:
        stored = {row.key: (row.status, row.attempts or 1)
                  for row in session.execute(select(EntityAlias.key, EntityAlias.status, EntityAlias.attempts))}
    return [pair for pair in spelling_pairs(engine) if pair.key not in stored or (
        retry_failed and stored[pair.key][0] == "failed" and stored[pair.key][1] < MAX_ATTEMPTS)]


def known_names(engine: Engine, limit: int = 1500) -> list[str]:
    """Canonical names already given to compounds that are not on Nawy, for consistency across batches."""
    with session_scope(engine) as session:
        rows = session.execute(select(EntityAlias.compound, EntityAlias.developer, EntityAlias.listings).where(
            EntityAlias.status == "done", EntityAlias.kind == "compound", EntityAlias.reference.is_(None),
            EntityAlias.compound.is_not(None), EntityAlias.confidence != "low")).all()
    weight: Counter = Counter()
    for compound, developer, listings in rows:
        weight[f"{compound} | {developer or ''}".strip(" |")] += listings or 1
    return [name for name, _ in weight.most_common(limit)]


def prompt(pairs: list[Pair], ref: Reference, known: list[str]) -> str:
    lines = [f"{name} | {info['developer'] or ''} | {info['area'] or ''}" for name, info in ref.compounds.items()]
    items = [{"id": index, "compound": pair.compound, "developer": pair.developer, "area": pair.district,
              "listings": pair.listings} for index, pair in enumerate(pairs)]
    return (
        "Resolve every item. Return exactly one entry per id.\n\n"
        "reference:\n" + "\n".join(lines) + "\n\n"
        "developers:\n" + "\n".join(ref.developers) + "\n\n"
        "known:\n" + "\n".join(known) + "\n\n"
        "items:\n" + json.dumps(items, ensure_ascii=False)
    )


def validated(answer: dict, pair: Pair, ref: Reference) -> dict:
    """Stored columns for one model answer. A reference must exist on Nawy and share the developer."""
    notes = []
    kind = answer.get("kind") if answer.get("kind") in ("compound", "not_compound") else None
    confidence = answer.get("confidence") if answer.get("confidence") in CONFIDENCE else "low"
    compound = _clean(answer.get("compound")) if kind == "compound" else None
    developer = _clean(answer.get("developer"))
    target = _clean(answer.get("reference")) if kind == "compound" else None
    if target and target not in ref.compounds:
        notes.append("reference_not_listed")
        target = None
    if target and confidence != "high":
        notes.append("reference_not_certain")
        target = None
    if target:
        listed = ref.compounds[target]["developer"]
        if listed and developer_key(listed) != developer_key(developer):
            notes.append("reference_developer_differs")
            target = None
        elif listed:
            developer = listed  # Nawy's spelling, so the developer joins its launch units
    if kind == "compound" and not compound:
        notes.append("compound_missing")
        confidence = "low"
    if compound and parent_area_differs(pair, compound, ref):
        notes.append("parent_area_differs")  # «IVY» (New Sphinx) is not a phase of SODIC East (New Heliopolis)
        compound = pair.compound
    return {"status": "done", "kind": kind, "compound": compound, "compound_ar": _clean(answer.get("compound_ar")),
            "developer": developer, "developer_ar": _clean(answer.get("developer_ar")), "reference": target,
            "confidence": confidence, "notes": notes or None, "error": None}


def parent_area_differs(pair: Pair, parent: str, ref: Reference) -> bool:
    """A Nawy launch placed inside another Nawy compound must be in the same area. Only Nawy's own
    names are checked (their area is Nawy's): a seller's «Greens» in New Cairo is rightly
    Greens Residence New Cairo even though Nawy also lists a «Greens» elsewhere."""
    own, other = ref.compounds.get(pair.compound), ref.compounds.get(parent)
    return bool(pair.compound != parent and own and other and own["area"] and pair.district == own["area"]
                and other["area"] and own["area"] != other["area"])


@dataclass
class BatchResult:
    done: int
    failed: int
    error: str | None = None


def resolve_batch(engine: Engine, pairs: list[Pair], ref: Reference, known: list[str],
                  invoke: Callable[[str], dict] | None = None) -> BatchResult:
    """One Pi call for the batch; answers are validated and stored, missing ids stored as failed."""
    invoke = invoke or (lambda text: run_pi(text, OUTPUT_SCHEMA, SPEC_PATH, model=MODEL,
                                               effort=REASONING_EFFORT, timeout=TIMEOUT_SECONDS))
    answers: dict[int, dict] = {}
    error = None
    try:
        answer = invoke(prompt(pairs, ref, known))
        for item in answer.get("items") or []:
            if isinstance(item, dict) and isinstance(item.get("id"), int) and 0 <= item["id"] < len(pairs):
                answers.setdefault(item["id"], item)
    except RuntimeError as exc:
        error = str(exc)
    now = utcnow()
    done = 0
    with session_scope(engine) as session:
        for index, pair in enumerate(pairs):
            row = session.get(EntityAlias, pair.key)
            if row is None:
                row = EntityAlias(key=pair.key, attempts=0)
                session.add(row)
            row.compound_text, row.developer_text, row.district_text = pair.compound, pair.developer, pair.district
            row.listings = pair.listings
            row.attempts = (row.attempts or 0) + 1
            row.model, row.prompt_version, row.resolved_at = MODEL, PROMPT_VERSION, now
            if index in answers:
                for column, value in validated(answers[index], pair, ref).items():
                    setattr(row, column, value)
                done += 1
            else:
                row.status, row.error = "failed", error or "missing from the answer"
    return BatchResult(done, len(pairs) - done, error)


def run(engine: Engine, *, limit: int | None = None, workers: int = 4, max_minutes: float | None = None,
        retry_failed: bool = True, on_batch: Callable[[int, BatchResult], None] | None = None,
        invoke: Callable[[str], dict] | None = None) -> list[BatchResult]:
    """Resolve pending spelling pairs in batches, at most `workers` Pi calls at a time."""
    if invoke is None and shutil.which("pi") is None:
        raise RuntimeError("Pi CLI is not installed or not on PATH")
    todo = pending(engine, retry_failed)[:limit]
    if not todo:
        return []
    ref = reference(engine)
    known = known_names(engine)
    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    deadline = time.monotonic() + max_minutes * 60 if max_minutes else None
    results: list[BatchResult] = []
    failed_in_a_row = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        running = {}

        def submit() -> None:
            if batches and failed_in_a_row < CIRCUIT_BREAKER and (deadline is None or time.monotonic() < deadline):
                running[pool.submit(resolve_batch, engine, batches.pop(0), ref, known, invoke)] = True

        for _ in range(workers):
            submit()
        while running:
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                running.pop(future)
                result = future.result()
                results.append(result)
                failed_in_a_row = failed_in_a_row + 1 if result.done == 0 else 0
                if on_batch:
                    on_batch(len(results), result)
                submit()
    return results

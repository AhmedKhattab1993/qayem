"""Sync engine: upsert parsed listings into `properties`, record version
history with field-level diffs, and mark removals — but only after a run
that is known to be complete (no errors, pagination not truncated)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .enrichment import description_hash, is_missing, listing_text
from .models import Property, PropertyEnrichment, PropertyVersion, utcnow
from .sources.base import NormalizedListing

# Fields that participate in change detection. Anything here changing marks
# the listing 'updated'; metadata columns (first_seen_at etc.) never do.
CONTENT_FIELDS = [
    "url",
    "title",
    "description",
    "purpose",
    "property_type",
    "is_resale",
    "resale_evidence",
    "price",
    "currency",
    "price_negotiable",
    "is_installment",
    "down_payment",
    "installment_months",
    "area_m2",
    "bedrooms",
    "bathrooms",
    "finishing",
    "delivery_status",
    "delivery_date",
    "compound",
    "developer",
    "governorate",
    "city",
    "district",
    "lat",
    "lng",
    "seller_type",
    "phone",
    "posted_at",
    "images",
]

# Fields added after listings were first hashed. While empty they stay out of
# the hash, so a new column never makes every stored listing look changed.
LATE_FIELDS = {"delivery_date"}


@dataclass
class SyncStats:
    seen: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    relisted: int = 0
    marked_removed: int = 0
    errors: list[str] = field(default_factory=list)


def _json_safe(value):
    """JSON columns can't hold datetimes — convert them to ISO strings."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _payload(listing: NormalizedListing) -> dict:
    return {name: value for name in CONTENT_FIELDS
            if (value := getattr(listing, name)) is not None or name not in LATE_FIELDS}


def content_hash(listing: NormalizedListing) -> str:
    blob = json.dumps(_payload(listing), sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _snapshot(prop: Property) -> dict:
    """Current DB row as a JSON-safe plain dict (for version payloads)."""
    return _json_safe({name: getattr(prop, name) for name in CONTENT_FIELDS})


def _diff(old: dict, new: dict) -> dict:
    return {
        key: {"old": old.get(key), "new": new.get(key)}
        for key in new
        if old.get(key) != new.get(key)
    }


def _apply(
    listing: NormalizedListing, prop: Property, now: datetime,
    enriched: dict | None = None,
) -> None:
    _assign(listing, prop, enriched)
    prop.last_seen_at = now
    prop.updated_at = now


def _assign(listing: NormalizedListing, prop: Property, enriched: dict | None = None) -> None:
    """Write a parsed listing's content onto its row, keeping enrichment fills."""
    enriched = enriched or {}
    use_resale_evidence = (
        "is_resale" in enriched and listing.is_resale is None
        and "resale_evidence" in enriched
    )
    for name in CONTENT_FIELDS:
        source_value = getattr(listing, name)
        if name == "resale_evidence" and use_resale_evidence:
            value = enriched[name]
        elif name in enriched and is_missing(name, source_value):
            value = enriched[name]
        else:
            value = source_value
        setattr(prop, name, value)
    prop.raw = _json_safe(listing.raw)
    if listing.scope_key is not None:
        prop.scope_key = listing.scope_key
    prop.content_hash = content_hash(listing)


def upsert_listing(
    session: Session, source: str, listing: NormalizedListing, run_id: int | None = None
) -> str:
    """Insert or update one listing. Returns the action taken:
    'created' | 'updated' | 'unchanged' | 'relisted'."""
    now = utcnow()
    prop = session.execute(
        select(Property).where(
            Property.source == source, Property.source_listing_id == listing.source_listing_id
        )
    ).scalar_one_or_none()

    new_hash = content_hash(listing)

    if prop is None:
        prop = Property(
            source=source,
            source_listing_id=listing.source_listing_id,
            status="active",
            first_seen_at=now,
        )
        _apply(listing, prop, now)
        session.add(prop)
        session.flush()  # assign prop.id for the version row
        session.add(
            PropertyVersion(property_id=prop.id, captured_at=now, change_type="created",
                            payload=_snapshot(prop))
        )
        return "created"

    was_removed = prop.status == "removed"
    old_payload = _snapshot(prop)

    if prop.content_hash == new_hash and not was_removed:
        prop.last_seen_at = now
        if prop.scope_key is None and listing.scope_key is not None:
            prop.scope_key = listing.scope_key
        return "unchanged"

    _apply(listing, prop, now, _enriched(session, prop, listing))
    diff = _diff(old_payload, _snapshot(prop))
    if not diff and not was_removed:
        return "unchanged"  # e.g. a parser change already backfilled onto this row
    if was_removed:
        prop.status = "active"
        prop.removed_at = None
        change_type = "relisted"
    else:
        change_type = "updated"
    session.add(
        PropertyVersion(property_id=prop.id, captured_at=now, change_type=change_type,
                        payload=_snapshot(prop), changed_fields=diff)
    )
    return "relisted" if was_removed else "updated"


def _enriched(session: Session, prop: Property, listing: NormalizedListing) -> dict:
    enrichment = session.get(PropertyEnrichment, prop.id)
    return (
        enrichment.applied or {}
        if enrichment is not None
        and enrichment.status == "done"
        and enrichment.description_hash in {
            description_hash(listing_text(listing.title, listing.description)),
            description_hash(listing.description or ""),  # records made before titles were sent
        }
        else {}
    )


def renormalize(session: Session, source: str, parse) -> tuple[int, int]:
    """Re-run a source's parser over stored `raw` payloads. → (rows, changed).

    A parser improvement is not a market event: rows are rewritten in place
    without version rows, and lifecycle timestamps are left untouched.
    """
    rows = changed = 0
    for prop in session.execute(select(Property).where(Property.source == source)).scalars():
        listing = parse(prop.raw) if prop.raw else None
        if listing is None or listing.source_listing_id != prop.source_listing_id:
            continue
        rows += 1
        before = _snapshot(prop)
        _assign(listing, prop, _enriched(session, prop, listing))
        changed += before != _snapshot(prop)
    return rows, changed


def known_versions(session: Session, source: str) -> dict[str, str | None]:
    """Active listings of a source → the `lastmod` stored in their raw payload."""
    rows = session.execute(
        select(Property.source_listing_id, Property.raw).where(
            Property.source == source, Property.status == "active")
    ).all()
    return {sid: (raw or {}).get("lastmod") for sid, raw in rows}


def touch_present(session: Session, source: str, ids: set[str], now: datetime) -> int:
    """Refresh last_seen_at for active listings confirmed present without a fetch."""
    touched = 0
    ordered = sorted(ids)
    for start in range(0, len(ordered), 500):
        chunk = ordered[start:start + 500]
        touched += session.query(Property).filter(
            Property.source == source, Property.status == "active", Property.source_listing_id.in_(chunk),
            Property.last_seen_at < now,
        ).update({Property.last_seen_at: now}, synchronize_session=False)
    return touched


def mark_removals(session: Session, source: str, scope_key: str, cutoff: datetime) -> int:
    """Listings of `source` within `scope_key` still 'active' but not seen
    since `cutoff` are marked removed. Call ONLY for scopes whose crawl
    completed naturally in this run (no errors, no truncation) — a scope the
    run didn't cover (other city/category) is never touched."""
    now = utcnow()
    stale = session.execute(
        select(Property).where(
            Property.source == source,
            Property.scope_key == scope_key,
            Property.status == "active",
            Property.last_seen_at < cutoff,
        )
    ).scalars().all()
    for prop in stale:
        prop.status = "removed"
        prop.removed_at = now
        prop.updated_at = now
        session.add(
            PropertyVersion(property_id=prop.id, captured_at=now, change_type="removed",
                            payload=_snapshot(prop))
        )
    return len(stale)


def backfill_from_description(session: Session, source: str, extract, column: str = "description") -> tuple[int, int]:
    """Fill empty columns from facts a source's generated description states. → (rows, changed).

    For sources whose stored payload cannot be re-parsed but whose description
    is a fixed template (Semsar). Like renormalize, this is a parser fix, not
    a market event: no version rows. Known values are never overwritten; a
    False installment/negotiable flag (the parser default) may become True.
    """
    rows = changed = 0
    for prop in session.execute(select(Property).where(Property.source == source)).scalars():
        rows += 1
        touched = False
        for name, value in extract(getattr(prop, column)).items():
            current = getattr(prop, name)
            if not (is_missing(name, current) or (value is True and current is False)):
                continue
            if name == "down_payment" and prop.price is not None and value >= prop.price:
                continue
            setattr(prop, name, value)
            touched = True
        changed += touched
    return rows, changed

"""SQLAlchemy models: unified properties, version history, parse-run log."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Property(Base):
    """Current state of one listing from one source. Rows are never deleted:
    listings that disappear get status='removed' and keep their history."""

    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("source", "source_listing_id", name="uq_source_listing"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_listing_id: Mapped[str] = mapped_column(String(191))
    scope_key: Mapped[str | None] = mapped_column(String(191), index=True)

    # content
    url: Mapped[str | None] = mapped_column(String(768))
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(String(8))  # sale | rent
    property_type: Mapped[str | None] = mapped_column(String(32))
    is_resale: Mapped[bool | None] = mapped_column(Boolean)  # tri-state: unknown = NULL
    resale_evidence: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    price_negotiable: Mapped[bool | None] = mapped_column(Boolean)
    is_installment: Mapped[bool | None] = mapped_column(Boolean)
    down_payment: Mapped[float | None] = mapped_column(Float)
    installment_months: Mapped[int | None] = mapped_column(Integer)
    area_m2: Mapped[float | None] = mapped_column(Float)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    finishing: Mapped[str | None] = mapped_column(String(32))
    delivery_status: Mapped[str | None] = mapped_column(String(32))
    delivery_date: Mapped[str | None] = mapped_column(String(10))  # ISO YYYY-MM-DD, as published
    compound: Mapped[str | None] = mapped_column(String(191))
    developer: Mapped[str | None] = mapped_column(String(191))
    governorate: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(64))
    district: Mapped[str | None] = mapped_column(String(191))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    seller_type: Mapped[str | None] = mapped_column(String(16))  # owner|broker|developer|unknown
    phone: Mapped[str | None] = mapped_column(String(32))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    images: Mapped[list | None] = mapped_column(JSON)
    raw: Mapped[dict | None] = mapped_column(JSON)

    # state
    content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PropertyVersion(Base):
    """Point-in-time snapshot of a property; `changed_fields` carries the
    field-level diff for 'updated'/'relisted' rows."""

    __tablename__ = "property_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    change_type: Mapped[str] = mapped_column(String(16))  # created|updated|removed|relisted
    payload: Mapped[dict | None] = mapped_column(JSON)
    changed_fields: Mapped[dict | None] = mapped_column(JSON)


class PropertyEnrichment(Base):
    """One durable description-enrichment record per property.

    The primary key is the durable claim. Interrupted or failed invocations
    are skipped unless the operator explicitly requests a failed-row retry.
    """

    __tablename__ = "property_enrichments"

    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16))  # claimed | done | failed
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    reasoning_effort: Mapped[str] = mapped_column(String(16))
    prompt_version: Mapped[str | None] = mapped_column(String(16))  # None: before the v2 prompt
    attempts: Mapped[int | None] = mapped_column(Integer)  # runs that claimed this listing (None: one)
    proposed: Mapped[list | None] = mapped_column(JSON)
    applied: Mapped[dict | None] = mapped_column(JSON)
    flags: Mapped[list | None] = mapped_column(JSON)  # e.g. ["price_is_down_payment"]; see enrichment.FLAG_NOTES
    error: Mapped[str | None] = mapped_column(Text)


class ParseRun(Base):
    """Log of one parse invocation for one source."""

    __tablename__ = "parse_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(16))  # running|completed|partial|failed
    params: Mapped[dict | None] = mapped_column(JSON)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    seen: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    marked_removed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(JSON)

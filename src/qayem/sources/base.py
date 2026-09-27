"""Source contract and the normalized listing model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import field
from datetime import datetime

from pydantic import BaseModel

from ..http_client import Fetcher


class NormalizedListing(BaseModel):
    """One listing in the unified schema. `raw` keeps the source payload so
    we can re-normalize later without re-fetching. `scope_key` tags which
    crawl scope produced the listing (e.g. 'cat:765', 'city:cairo', 'all') —
    removal marking is scoped to it."""

    source_listing_id: str
    scope_key: str | None = None
    url: str | None = None
    title: str | None = None
    description: str | None = None
    purpose: str | None = "sale"  # sale | rent
    property_type: str | None = None
    is_resale: bool | None = None
    resale_evidence: str | None = None
    price: float | None = None
    currency: str | None = "EGP"
    price_negotiable: bool = False
    is_installment: bool = False
    down_payment: float | None = None
    installment_months: int | None = None
    area_m2: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    finishing: str | None = None
    delivery_status: str | None = None
    delivery_date: str | None = None  # ISO YYYY-MM-DD promised handover
    compound: str | None = None
    developer: str | None = None
    governorate: str | None = None
    city: str | None = None
    district: str | None = None
    lat: float | None = None
    lng: float | None = None
    seller_type: str | None = None
    phone: str | None = None
    posted_at: datetime | None = None
    images: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class BaseSource(ABC):
    """One portal. A source's `fetch()` yields NormalizedListings; after the
    generator is exhausted, the engine inspects `complete` and `errors`:
    removals are only marked when complete=True and errors==[]."""

    name: str = "base"
    # Sources that fetch incrementally ask the engine for {listing id: stored raw["lastmod"]}.
    wants_known: bool = False

    def __init__(self, fetcher: Fetcher, **params):
        self.fetcher = fetcher
        self.params = params
        self.complete = False
        self.errors: list[str] = []
        self.pages_fetched = 0
        # Scope keys whose crawl reached a natural end — only these may have
        # their unseen listings marked removed.
        self.scopes_completed: set[str] = set()
        # Listings confirmed still listed without a fetch (e.g. present in a complete
        # sitemap); the engine refreshes their last_seen_at before marking removals.
        self.present_ids: set[str] = set()

    @abstractmethod
    def fetch(self) -> Iterator[NormalizedListing]:
        """Yield listings. Set self.complete=True when pagination ended
        naturally; record failures in self.errors instead of raising."""

    def param(self, key: str, default=None):
        return self.params.get(key, default)

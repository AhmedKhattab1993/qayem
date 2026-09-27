"""OpenSooq Egypt — property classifieds.

Endpoint: /en/{city}/{category-path}?page=N  (e.g.
/en/cairo/property/apartments-for-sale?page=2)
Data: `__NEXT_DATA__` → pageProps.serpApiResponse.listings.items (30/page)
with meta {count, per_page, pages}. The SERP caps pagination at 50 pages:
when meta.pages > 50 the crawl is truncated and must not trigger removals.
No resale filter exists — classification is keyword-based.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from ..http_client import FetchError
from ..normalization import (
    classify_resale,
    parse_highlights,
    parse_number,
    to_western_digits,
)
from .base import BaseSource, NormalizedListing
from .nawy import extract_next_data

BASE = "https://eg.opensooq.com"
# url_en paths from the live taxonomy (verified 2026-09-21).
CATEGORIES = {
    "apartments": "property/apartments-for-sale",
    "villas": "property/villas-palaces-for-sale",
    "buildings": "property/whole-buildings-for-sale",
    "townhouses": "property/townhouses-for-sale",
    "farms-chalets": "property/farms-chalets-for-sale",
}
DEFAULT_CATEGORIES = ["apartments"]
PAGE_CAP = 50

_CPS_BEDS = re.compile(r"(\d+)\s*Bedrooms?", re.I)
_CPS_BATHS = re.compile(r"(\d+)\s*Bathrooms?", re.I)
_CPS_AREA = re.compile(r"Area:\s*([\d,]+)\s*m2", re.I)
_FURNISHED_RE = re.compile(r"unfurnished|semi furnished|furnished", re.I)
_POSTED_AGO = re.compile(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", re.I)


def parse_posted_at(text: str | None, now: datetime) -> datetime | None:
    """OpenSooq gives relative times ('54 minutes ago'). Best-effort."""
    if not text:
        return None
    m = _POSTED_AGO.search(to_western_digits(text))
    if not m:
        return None
    value, unit = int(m.group(1)), m.group(2).lower()
    delta = {
        "minute": timedelta(minutes=value),
        "hour": timedelta(hours=value),
        "day": timedelta(days=value),
        "week": timedelta(weeks=value),
        "month": timedelta(days=30 * value),
        "year": timedelta(days=365 * value),
    }[unit]
    return now - delta


def parse_item(item: dict, now: datetime) -> NormalizedListing | None:
    item_id = item.get("id")
    if item_id is None:
        return None
    price = parse_number(item.get("price_amount"))
    cps = " | ".join(item.get("cps") or [])
    highlights = parse_highlights(item.get("highlights"))
    if not highlights.get("bedrooms") and (m := _CPS_BEDS.search(cps)):
        highlights["bedrooms"] = int(m.group(1))
    if not highlights.get("bathrooms") and (m := _CPS_BATHS.search(cps)):
        highlights["bathrooms"] = int(m.group(1))
    if not highlights.get("area_m2") and (m := _CPS_AREA.search(cps)):
        highlights["area_m2"] = float(m.group(1).replace(",", ""))

    furnishing = None
    if (m := _FURNISHED_RE.search(cps)):
        furnishing = m.group().lower().replace(" ", "_")

    title = item.get("title")
    resale, evidence = classify_resale(" ".join(x for x in (title, cps) if x))
    image_uri = item.get("image_uri")
    post_url = item.get("post_url")

    return NormalizedListing(
        source_listing_id=str(item_id),
        url=f"{BASE}/en/{post_url}" if post_url else None,
        title=title,
        description=item.get("masked_description"),
        purpose="sale",
        is_resale=resale,
        resale_evidence=evidence or "no resale signals in title/attributes",
        price=price,
        currency=item.get("price_currency_iso") or "EGP",
        area_m2=highlights.get("area_m2"),
        bedrooms=highlights.get("bedrooms"),
        bathrooms=highlights.get("bathrooms"),
        finishing=furnishing,
        city=(item.get("city_label") or "").lower() or None,
        district=item.get("nhood_label"),
        seller_type="unknown",
        phone=item.get("phone_number"),  # masked by OpenSooq in SERP data
        posted_at=parse_posted_at(item.get("posted_at"), now),
        images=[f"https://opensooq-imagesv2.os-cdn.com/previews/640x480/{image_uri}.webp"]
        if image_uri
        else [],
        raw=item,
    )


class OpenSooqSource(BaseSource):
    name = "opensooq"

    def fetch(self) -> Iterator[NormalizedListing]:
        now = datetime.now(timezone.utc)
        city = self.param("city", "cairo")
        categories = [self.param("category")] if self.param("category") else DEFAULT_CATEGORIES
        max_pages = self.param("max_pages")
        any_truncated = False

        for category in categories:
            cat_path = CATEGORIES.get(category, category)
            natural = yield from self._fetch_category(city, cat_path, max_pages, now)
            any_truncated |= not natural

        self.complete = not self.errors and not any_truncated

    def _fetch_category(
        self, city: str, cat_path: str, max_pages: int | None, now: datetime
    ) -> Iterator[NormalizedListing]:
        """Yield listings; `return` value = True when pagination ended naturally."""
        scope = f"{city}:{cat_path}"
        page = 1
        while True:
            url = f"{BASE}/en/{city}/{cat_path}"
            if page > 1:
                url += f"?{urlencode({'page': page})}"
            try:
                html = self.fetcher.get_text(url)
            except FetchError as exc:
                self.errors.append(f"{city}/{cat_path} page {page}: {exc}")
                return False
            self.pages_fetched += 1
            try:
                props = extract_next_data(html)["props"]["pageProps"]
                listings = props["serpApiResponse"]["listings"]
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"{city}/{cat_path} page {page}: parse failed: {exc}")
                return False

            items = listings.get("items") or []
            for item in items:
                parsed = parse_item(item, now)
                if parsed is not None:
                    parsed.scope_key = scope
                    yield parsed

            meta = listings.get("meta") or {}
            current, pages = meta.get("current_page", page), meta.get("pages", page)
            if not items or current >= pages:
                self.scopes_completed.add(scope)  # natural end of this category
                return True
            if (max_pages and page >= max_pages) or current >= PAGE_CAP:
                return False  # truncated by caller cap or SERP hard cap
            page += 1

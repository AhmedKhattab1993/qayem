"""OpenSooq Egypt — property classifieds.

Since November 2026 the SERP is server-rendered without `__NEXT_DATA__`: each listing is a card
`<a data-id1=… data-city=… data-nhood=…>` with its price, title, area, rooms and furnishing as text
(`parse_cards`). The older `__NEXT_DATA__` shape below is still read when present. The card's masked
phone number is never read.

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
    detect_property_type,
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


_CARD = re.compile(r'<a\s[^>]*data-id1="(\d+)"[^>]*>', re.S)
_ATTR = re.compile(r'data-(city|nhood|user-target-type|cat2-code)="([^"]*)"')
_HREF = re.compile(r'href="(/[^"]+)"')
_PRICE = re.compile(r"([\d,]+)\s*EGP")
_PAGE_LINK = re.compile(r"[?&]page=(\d+)")


def _card_text(fragment: str) -> list[str]:
    fragment = re.sub(r"<(svg|script|style|button)\b.*?</\1>", " ", fragment, flags=re.S)
    return [" ".join(part.split()) for part in re.split(r"<[^>]+>", fragment) if part.strip()]


def parse_cards(html: str) -> tuple[list[dict], int]:
    """Listings as item dicts in the shape `parse_item` reads, and the last page number linked."""
    items = []
    starts = list(_CARD.finditer(html))
    for index, match in enumerate(starts):
        end = html.find("</a>", match.end())
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(html)
        fragment = html[match.end(): end if 0 < end < stop else stop]
        attrs = dict(_ATTR.findall(match.group(0)))
        texts = _card_text(fragment)
        price = next((m.group(1) for t in texts if (m := _PRICE.fullmatch(t.strip()))), None)
        cps = [t for t in texts if re.search(r"Area:|Bedroom|Bathroom|furnished|Floor", t, re.I)]
        title = next((t for t in texts if len(t) > 15 and not _PRICE.search(t) and t not in cps
                      and not re.search(r"\bago\b|^Compare$|^Chat$|XX$", t)), None)
        href = _HREF.search(match.group(0))
        items.append({
            "id": int(match.group(1)), "price_amount": price.replace(",", "") if price else None,
            "price_currency_iso": "EGP", "title": title, "cps": cps,
            "city_label": attrs.get("city"), "nhood_label": attrs.get("nhood"),
            "user_target_type": attrs.get("user-target-type"), "cat2_code": attrs.get("cat2-code"),
            "post_url": href.group(1).lstrip("/").removeprefix("en/") if href else None,
            "posted_at": next((t for t in texts if re.search(r"\bago\b", t)), None),
        })
    pages = max((int(n) for n in _PAGE_LINK.findall(html)), default=1)
    return items, pages


CAT2_TYPES = {"ApartmentsForSale": "apartment", "VillasPalacesForSale": "villa", "TownhousesForSale": "townhouse",
              "FarmsChaletsForSale": "chalet", "WholeBuildingsForSale": "building"}


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
        property_type=detect_property_type(title) if item.get("cat2_code") == "FarmsChaletsForSale" and detect_property_type(title)
        else CAT2_TYPES.get(item.get("cat2_code") or "") or detect_property_type(title),
        price=price,
        currency=item.get("price_currency_iso") or "EGP",
        area_m2=highlights.get("area_m2"),
        bedrooms=highlights.get("bedrooms"),
        bathrooms=highlights.get("bathrooms"),
        finishing=furnishing,
        city=(item.get("city_label") or "").lower() or None,
        district=item.get("nhood_label"),
        seller_type="unknown",
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
                if "__NEXT_DATA__" in html:
                    props = extract_next_data(html)["props"]["pageProps"]
                    listings = props["serpApiResponse"]["listings"]
                else:
                    cards, last = parse_cards(html)
                    if not cards and page == 1:
                        raise ValueError("no listing cards on the first page")
                    listings = {"items": cards, "meta": {"current_page": page, "pages": max(last, page)}}
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

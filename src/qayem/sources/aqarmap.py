"""Aqarmap — for-sale listings across cities.

Endpoint: /en/for-sale/property-type/{city}/?page=N  (exact path shape —
the CloudFront WAF 403s unknown paths, so never improvise URL variants)
Data: SSR `.listing-card` articles (`<data value>` price, icon-classified
spec li items, district/compound links) + RSC-flight flags
(`isResaleInstallment`) associated per listing by proximity in the payload.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http_client import FetchError
from ..normalization import classify_resale, detect_finishing, detect_property_type, parse_number
from .base import BaseSource, NormalizedListing

BASE = "https://aqarmap.com.eg"
_FLAG_RE = re.compile(r'\\"isResaleInstallment\\":(true|false)')


def _spec_value(card, icon_class: str) -> float | None:
    li = card.find("i", class_=re.compile(icon_class))
    if li is None:
        return None
    span = li.find_parent("li")
    if span is None:
        return None
    return parse_number(span.get_text(" ", strip=True))


def parse_card(card, flags_by_listing: dict[str, bool]) -> NormalizedListing | None:
    label = card.get("aria-labelledby") or ""
    m = re.search(r"listing-(\d+)-title", label)
    if not m:
        return None
    listing_id = m.group(1)

    link = card.select_one('a[href*="/en/listing/"]')
    url = urljoin(BASE, link["href"]) if link and link.has_attr("href") else None

    price = None
    data_el = card.find("data", attrs={"value": True})
    if data_el is not None:
        price = parse_number(data_el["value"])

    h2 = card.find("h2", id=re.compile(rf"^listing-{listing_id}-title$"))
    title = h2.get_text(" ", strip=True) if h2 else None
    if h2 and h2.get("title"):
        title = h2["title"]

    district = compound = None
    city = None
    for a in card.select('a[href*="/for-sale/property-type/"]'):
        href = a.get("href", "")
        if "/compounds/" in href:
            compound = a.get_text(" ", strip=True) or None
        else:
            district = a.get_text(" ", strip=True) or None
            cm = re.search(r"/for-sale/property-type/([^/]+)/", href)
            if cm:
                city = cm.group(1)

    area_m2 = _spec_value(card, r"size-icon")
    bedrooms = _spec_value(card, r"bedroom-icon")
    bathrooms = _spec_value(card, r"bathroom-icon")

    seller = None
    seller_a = card.find("a", attrs={"aria-label": re.compile(r"View listing by ")})
    if seller_a is not None:
        seller = seller_a["aria-label"].replace("View listing by ", "").strip() or None

    flag = flags_by_listing.get(listing_id)
    if flag is True:
        is_resale, evidence = True, "aqarmap isResaleInstallment=true"
    else:
        is_resale, evidence = classify_resale(title)
        if is_resale is None and flag is False:
            evidence = "isResaleInstallment=false; no resale signals in title"

    images = [img["src"] for img in card.select("img[src]") if img["src"].startswith("http")]

    return NormalizedListing(
        source_listing_id=listing_id,
        url=url,
        title=title,
        purpose="sale",
        property_type=detect_property_type(title),
        is_resale=is_resale,
        resale_evidence=evidence,
        price=price,
        currency="EGP",
        area_m2=area_m2,
        bedrooms=int(bedrooms) if bedrooms else None,
        bathrooms=int(bathrooms) if bathrooms else None,
        finishing=detect_finishing(title),
        city=city,
        district=district,
        compound=compound,
        seller_type="broker" if seller else None,
        images=images,
        raw={"seller": seller, "isResaleInstallment": flag},
    )


def build_flag_map(html: str) -> dict[str, bool]:
    """Associate each isResaleInstallment flag in the RSC-flight payload with
    the next `listing-{id}-title` marker that follows it (that is how the
    chunks are laid out: installment plan object, then the listing h2)."""
    events = []
    for m in _FLAG_RE.finditer(html):
        events.append((m.start(), "flag", m.group(1) == "true"))
    for m in re.finditer(r"listing-(\d+)-title", html):
        events.append((m.start(), "id", m.group(1)))
    events.sort()
    flags: dict[str, bool] = {}
    pending: bool | None = None
    for _, kind, value in events:
        if kind == "flag":
            pending = value
        elif pending is not None:
            flags.setdefault(value, pending)
            pending = None
    return flags


class AqarmapSource(BaseSource):
    name = "aqarmap"

    def fetch(self) -> Iterator[NormalizedListing]:
        city = self.param("city", "cairo")
        scope = f"city:{city}"
        max_pages = self.param("max_pages")
        page = 1
        while True:
            url = f"{BASE}/en/for-sale/property-type/{city}/"
            if page > 1:
                url += f"?page={page}"
            try:
                html = self.fetcher.get_text(url)
            except FetchError as exc:
                self.errors.append(f"page {page}: {exc}")
                return
            self.pages_fetched += 1
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select("article.listing-card")
            if not cards:
                self.complete = True  # past the last page
                self.scopes_completed.add(scope)
                return
            flags = build_flag_map(html)
            for card in cards:
                parsed = parse_card(card, flags)
                if parsed is not None:
                    parsed.scope_key = scope
                    yield parsed
            if max_pages and page >= max_pages:
                return  # truncated
            page += 1

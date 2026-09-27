"""GPM Egypt — dedicated resale catalogue.

List: /en/resale?page=N   (div.property-grid-1 cards, 12/page)
Details: /en/resale-real-estate/{slug}  (label/value blocks: Total Price,
Method Payment, Down Payment, Area, Bedrooms, Bathrooms, Finishing,
Delivery Date + description). Whole catalogue is resale by construction.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http_client import FetchError
from ..normalization import parse_number
from .base import BaseSource, NormalizedListing

BASE = "https://gpmegypt.com"

_ID_FROM_SLUG = re.compile(r"-([A-Za-z0-9]{4,10})$")
_FINISH_MAP = {
    "fully finished": "finished",
    "semi finished": "semi_finished",
    "unfinshed": "core_shell",  # site's own typo for unfinished
    "unfinished": "core_shell",
    "core and shell": "core_shell",
}


def _id_from_url(url: str) -> str | None:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    m = _ID_FROM_SLUG.search(slug)
    return m.group(1) if m else slug


def parse_list_card(card) -> NormalizedListing | None:
    link = card.select_one('a[href*="/en/resale-real-estate/"]')
    if link is None:
        return None
    url = urljoin(BASE, link["href"])

    title = None
    h6a = card.select_one("div.property_text h6 a")
    if h6a is not None:
        title = h6a.get_text(" ", strip=True)
    if not title:
        img = card.find("img", alt=True)
        title = img["alt"] if img else None

    price = None
    price_el = card.select_one("span.price-on")
    if price_el is not None:
        price = parse_number(price_el.get_text(" ", strip=True))

    ptype = None
    type_a = card.select_one("div.property_text .post-meta a span")
    if type_a is not None:
        ptype = type_a.get_text(" ", strip=True).lower() or None

    district = None
    for span in card.find_all("span"):
        if span.find("i", class_="fa-map-marker-alt"):
            district = span.get_text(" ", strip=True)
            break

    compound = None
    agent_a = card.select_one("div.agent a span")
    if agent_a is not None:
        compound = agent_a.get_text(" ", strip=True)

    phone = None
    tel = card.select_one('a[href^="tel:"]')
    if tel is not None:
        phone = tel["href"].replace("tel:", "").strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone

    images = []
    img = card.find("img", src=True)
    if img is not None:
        images.append(img["src"])

    return NormalizedListing(
        source_listing_id=_id_from_url(url),
        scope_key="all",
        url=url,
        title=title,
        purpose="sale",
        property_type=ptype,
        is_resale=True,
        resale_evidence="dedicated /en/resale catalogue",
        price=price,
        currency="EGP",
        district=district or None,
        compound=compound,
        seller_type="broker",
        phone=phone,
        images=images,
        raw={},
    )


def parse_detail(listing: NormalizedListing, html: str) -> None:
    """Enrich a listing in place from its detail page."""
    soup = BeautifulSoup(html, "lxml")
    offers = {}
    for li in soup.select(".product-offer-item"):
        strong = li.find("strong")
        small = li.find("small")
        if strong is None or small is None:
            continue
        offers[strong.get_text(" ", strip=True).strip().lower()] = small.get_text(" ", strip=True)

    if "area" in offers:
        listing.area_m2 = parse_number(offers["area"]) or listing.area_m2
    if "bedrooms" in offers:
        listing.bedrooms = int(parse_number(offers["bedrooms"]) or 0) or None
    if "bathrooms" in offers:
        listing.bathrooms = int(parse_number(offers["bathrooms"]) or 0) or None
    if "down payment" in offers:
        listing.down_payment = parse_number(offers["down payment"])
        listing.is_installment = True
    if "method payment" in offers:
        listing.is_installment = "installment" in offers["method payment"].lower()
    if "finishing" in offers:
        listing.finishing = _FINISH_MAP.get(
            offers["finishing"].lower(), offers["finishing"].lower().replace(" ", "_")
        )
    if "delivery date" in offers:
        listing.delivery_status = offers["delivery date"]

    # description: everything after the "Unit Details" heading
    label = soup.find(string=re.compile(r"^\s*Unit Details\s*$"))
    if label is not None:
        container = label.find_parent(["div", "section", "h2", "h3", "h4"])
        if container is not None:
            texts = []
            for sib in container.find_next_siblings():
                texts.append(sib.get_text(" ", strip=True))
            listing.description = " ".join(t for t in texts if t)[:4000] or None


class GpmSource(BaseSource):
    name = "gpm"

    def fetch(self) -> Iterator[NormalizedListing]:
        max_pages = self.param("max_pages")
        want_details = self.param("details", True)
        max_details = self.param("max_details", 100)
        details_done = 0

        page = 1
        while True:
            url = f"{BASE}/en/resale" + (f"?page={page}" if page > 1 else "")
            try:
                html = self.fetcher.get_text(url)
            except FetchError as exc:
                self.errors.append(f"page {page}: {exc}")
                return
            self.pages_fetched += 1
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select("div.property-grid-1")
            if not cards:
                self.complete = True
                self.scopes_completed.add("all")
                return
            for card in cards:
                parsed = parse_list_card(card)
                if parsed is None:
                    continue
                if want_details and (max_details is None or details_done < max_details):
                    try:
                        detail_html = self.fetcher.get_text(parsed.url)
                        self.pages_fetched += 1
                        parse_detail(parsed, detail_html)
                    except FetchError as exc:
                        self.errors.append(f"detail {parsed.source_listing_id}: {exc}")
                    details_done += 1
                yield parsed
            if max_pages and page >= max_pages:
                return  # truncated by caller
            page += 1

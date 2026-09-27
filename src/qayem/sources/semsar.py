"""Semsar Masr — classic Egyptian property classifieds.

Endpoint: /3akarat?r=70&g=0&a=0&cid={category}&p={N}  (r=70 g=0: all Egypt). The legacy
/3akarat.asp?cid=&p= form stopped paginating in 2026-09 (every page returned page 1),
so a page identical to the previous one is treated as broken paging, not more inventory.
Pages are windows-1256 encoded; every listing card carries full schema.org
microdata (Offer price/currency, businessFunction #Sell/#LeaseOut, rooms,
floorSize, PostalAddress). Detail pages add JSON-LD with agent phone.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup

from ..http_client import FetchError
from ..normalization import (
    classify_resale,
    detect_finishing,
    detect_property_type,
    detect_seller_type,
    normalize_governorate,
    parse_number,
    to_western_digits,
)
from .base import BaseSource, NormalizedListing

BASE = "https://www.semsarmasr.com"
ENCODING = "windows-1256"
CATEGORIES = {
    "apartments": 765,
    "land": 766,
    "villas": 767,
    "buildings": 769,
    "chalets": 770,
    "commercial": 771,
}
DEFAULT_CATEGORIES = ["apartments", "villas", "chalets"]


_ROOMS = re.compile(r"مصر،\s*(\d+)\s*غرف")
_DOWN_PAYMENT = re.compile(r"مقدم\s*دفعة\s*أولى\s*([\d,]+)\s*جنيه")
_PLAN_MONTHS = re.compile(r"قساط\s*على\s*(\d+)\s*شهر")


def parse_description(text: str | None) -> dict:
    """Facts from the card description, which Semsar generates from a fixed template:

    «شقة للبيع (تمليك) في <مكان> مصر، 3 غرف، 245 م² ،جديدة أول ساكن، بالتقسيط
    بواسطة سمسار متشطب سوبر لوكس . مقدم دفعة أولى 600,000 جنيه. والباقي أٌقساط
    على 36 شهر» — rooms, finishing, down payment, plan length and negotiability.
    """
    if not text:
        return {}
    text = to_western_digits(text)
    facts: dict = {}
    if (rooms := _ROOMS.search(text)) and int(rooms.group(1)) <= 20:
        facts["bedrooms"] = int(rooms.group(1))
    if finishing := detect_finishing(text):
        facts["finishing"] = finishing
    if down := _DOWN_PAYMENT.search(text):
        facts["down_payment"] = parse_number(down.group(1))
        facts["is_installment"] = True
    if months := _PLAN_MONTHS.search(text):
        facts["installment_months"] = int(months.group(1))
        facts["is_installment"] = True
    if "بالتقسيط" in text:
        facts["is_installment"] = True
    if "قابل للتفاوض" in text:
        facts["price_negotiable"] = True
    return facts


def _micro(soup_or_tag, prop: str):
    """Find the element carrying itemprop=prop."""
    return soup_or_tag.find(attrs={"itemprop": prop})


def parse_card(card) -> NormalizedListing | None:
    link = card.select_one("a.card-link[href]")
    if link is None:
        return None
    url = link["href"]
    id_m = re.search(r"/3akarat/(\d+)", url)
    if not id_m:
        return None

    title_el = _micro(card, "name")
    title = title_el.get_text(" ", strip=True) if title_el else None
    desc_el = _micro(card, "description")
    description = desc_el.get("content") if desc_el is not None else None

    region_el = _micro(card, "addressRegion")
    locality_el = _micro(card, "addressLocality")

    purpose = "sale"
    price = down_payment = None
    is_installment = False
    offers = _micro(card, "offers")
    if offers is not None:
        price_el = offers.find(attrs={"itemprop": "price"})
        if price_el is not None and price_el.get("content"):
            price = parse_number(price_el["content"])
        bf = offers.find("link", attrs={"itemprop": "businessFunction"})
        if bf is not None and bf.get("href", "").endswith("#LeaseOut"):
            purpose = "rent"
        price_text = offers.find("span", class_="price")
        if price_text is not None:
            text = price_text.get_text(" ", strip=True)
            if "مقدم" in text:  # displayed number is the down payment
                down_payment = parse_number(text)
                is_installment = True

    rooms_el = _micro(card, "numberOfRooms")
    area = None
    size_el = _micro(card, "floorSize")
    if size_el is not None:
        value_el = _micro(size_el, "value")
        if value_el is not None:
            area = parse_number(value_el.get_text(" ", strip=True))

    img = card.find("img", attrs={"itemprop": "image"})
    image_url = img.get("src") if img is not None else None

    stated = parse_description(description)
    down_payment = down_payment or stated.get("down_payment")
    if down_payment is not None and price is not None and down_payment >= price:
        down_payment = None  # the displayed number was the whole price
    bedrooms = int(rooms_el.get_text(strip=True)) if rooms_el is not None else stated.get("bedrooms")

    text_for_heuristics = " ".join(x for x in (title, description) if x)
    itemtype = card.get("itemtype", "")
    schema_type = itemtype.rsplit("/", 1)[-1] if itemtype else None

    # resale is a sale-side concept; «من المالك» in a rent ad doesn't apply
    if purpose == "sale":
        resale, evidence = classify_resale(text_for_heuristics)
        if resale is None:
            evidence = "no resale signals in title/description"
    else:
        resale, evidence = None, "rent listing"

    return NormalizedListing(
        source_listing_id=id_m.group(1),
        url=url,
        title=title,
        description=description,
        purpose=purpose,
        property_type=detect_property_type(title) or (schema_type.lower() if schema_type else None),
        is_resale=resale,
        resale_evidence=evidence or "no resale signals in title/description",
        price=price,
        currency="EGP",
        price_negotiable=stated.get("price_negotiable", False),
        is_installment=is_installment or stated.get("is_installment", False),
        down_payment=down_payment,
        installment_months=stated.get("installment_months"),
        finishing=stated.get("finishing"),
        area_m2=area,
        bedrooms=bedrooms,
        district=region_el.get_text(" ", strip=True) or None if region_el is not None else None,
        governorate=normalize_governorate(
            locality_el.get_text(" ", strip=True) if locality_el is not None else None
        ),
        seller_type=detect_seller_type(description or ""),
        images=[image_url] if image_url else [],
        raw={"schema_type": schema_type},
    )


def parse_detail_jsonld(html: str) -> dict | None:
    """Detail pages embed one schema.org JSON-LD block with the agent phone."""
    m = re.search(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


class SemsarSource(BaseSource):
    name = "semsar"

    def fetch(self) -> Iterator[NormalizedListing]:
        categories = [self.param("category")] if self.param("category") else DEFAULT_CATEGORIES
        max_pages = self.param("max_pages")
        want_details = self.param("details", False)
        max_details = self.param("max_details")
        details_done = 0

        for category in categories:
            cid = CATEGORIES.get(category)
            if cid is None:
                self.errors.append(f"unknown category {category}")
                continue
            page = 1
            previous: list[str] = []
            scope = f"cat:{cid}"
            while True:
                url = f"{BASE}/3akarat?r=70&g=0&a=0&cid={cid}&p={page}"
                try:
                    html = self.fetcher.get_text(url, encoding=ENCODING)
                except FetchError as exc:
                    self.errors.append(f"{category} page {page}: {exc}")
                    break
                self.pages_fetched += 1
                soup = BeautifulSoup(html, "lxml")
                cards = soup.select("article.property-card")
                if not cards:
                    self.complete = True  # past the last page of this category
                    self.scopes_completed.add(scope)
                    break
                signature = [card.get("id") or str(card)[:400] for card in cards]
                if signature == previous:
                    self.errors.append(f"{category} page {page} repeats page {page - 1}: site paging changed")
                    break
                previous = signature
                for card in cards:
                    parsed = parse_card(card)
                    if parsed is None:
                        continue
                    parsed.scope_key = scope
                    if want_details and (max_details is None or details_done < max_details):
                        self._enrich_from_detail(parsed)
                        details_done += 1
                    yield parsed
                if max_pages and page >= max_pages:
                    return  # truncated by caller
                page += 1

    def _enrich_from_detail(self, listing: NormalizedListing) -> None:
        """Fetch the detail page for the agent phone (only data the list card
        lacks). Failures are recorded but don't fail the listing."""
        try:
            html = self.fetcher.get_text(f"{BASE}/3akarat/{listing.source_listing_id}/x",
                                         encoding=ENCODING)
        except FetchError as exc:
            self.errors.append(f"detail {listing.source_listing_id}: {exc}")
            return
        self.pages_fetched += 1
        data = parse_detail_jsonld(html)
        if not data:
            return
        provider = data.get("provider") or {}
        phone = provider.get("telephone")
        if phone:
            listing.phone = phone
        offers = data.get("offers") or {}
        if offers.get("price"):
            listing.price = parse_number(str(offers.get("price"))) or listing.price

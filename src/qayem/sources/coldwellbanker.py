"""Coldwell Banker Egypt — residential/commercial resale.

Discovery: sitemap https://ecms.coldwellbanker-eg.com/properties.xml
(~23.8k property URLs, id = trailing number, newest = highest id).
Resale classification: the per-listing "Sale Type" field on each detail
page (verified value: "Resale"); the two resale hub pages provide a hint
set for listings whose details we haven't fetched.
Detail fields: HTML table (Reference No./Bedrooms/Bathroom/Sale Type/
Finishing) + "Sale Price" block + JSON-LD `Residence`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http_client import FetchError
from .base import BaseSource, NormalizedListing

BASE = "https://coldwellbanker-eg.com"
SITEMAP_URL = "https://ecms.coldwellbanker-eg.com/properties.xml"
HUB_PATHS = [
    "/en/residential-resale-properties-egypt",
    "/en/commercial-resale-units",
]

_FINISH_MAP = {
    "fully finished": "finished",
    "finished": "finished",
    "semi finished": "semi_finished",
    "unfinshed": "core_shell",  # site's own typo for unfinished
    "unfinished": "core_shell",
    "core and shell": "core_shell",
}


def parse_detail_url(url: str) -> str | None:
    m = re.search(r"/properties/[^/]*?(\d+)/?$", url.rstrip("/"))
    return m.group(1) if m else None


def parse_detail(html: str, url: str) -> NormalizedListing | None:
    listing_id = parse_detail_url(url)
    if listing_id is None:
        return None
    soup = BeautifulSoup(html, "lxml")

    # label/value table
    fields: dict[str, str] = {}
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) == 2:
            fields[tds[0].get_text(" ", strip=True).strip().lower()] = tds[1].get_text(
                " ", strip=True
            ).strip()

    # Sale Price block
    price = None
    h4 = soup.find("h4", string=re.compile(r"Sale Price"))
    if h4 is not None:
        wrapper = h4.find_next("div", class_=re.compile("price-is"))
        if wrapper is not None:
            m = re.search(r"([\d,]+(?:\.\d+)?)", wrapper.get_text(" ", strip=True))
            if m:
                price = float(m.group(1).replace(",", ""))

    # area: "440.00 m2" heading
    area = None
    for h2 in soup.find_all("h2"):
        text = h2.get_text(" ", strip=True)
        if text.endswith("m2"):
            m = re.search(r"([\d.]+)", text)
            if m:
                area = float(m.group(1))
            break

    # JSON-LD Residence
    name = address = region = None
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if (data.get("@type") == "Residence") or (
            isinstance(data.get("@type"), list) and "Residence" in data.get("@type", [])
        ):
            name = data.get("name")
            addr = data.get("address") or {}
            address = addr.get("streetAddress")
            region = addr.get("addressRegion")
            break

    sale_type = fields.get("sale type")
    if sale_type:
        is_resale = sale_type.strip().lower() == "resale"
        evidence = f"Sale Type field: {sale_type}"
    elif fields:
        # unit detail rendered but no Sale Type row: primary/developer stock
        is_resale, evidence = None, "no Sale Type field on detail page"
    else:
        is_resale, evidence = None, "detail fields unavailable"

    finishing = fields.get("finishing")
    finishing_norm = _FINISH_MAP.get((finishing or "").lower()) or (
        (finishing or "").lower().replace(" ", "_") or None
    )

    return NormalizedListing(
        source_listing_id=listing_id,
        url=url,
        title=name,
        purpose="sale",
        is_resale=is_resale,
        resale_evidence=evidence,
        price=price,
        currency="EGP",
        area_m2=area,
        bedrooms=int(fields["bedrooms"]) if fields.get("bedrooms", "").isdigit() else None,
        bathrooms=int(fields["bathroom"]) if fields.get("bathroom", "").isdigit() else None,
        finishing=finishing_norm,
        city=(region or "").lower() or None,
        district=address,
        raw={"fields": fields},
    )


class ColdwellBankerSource(BaseSource):
    name = "coldwellbanker"

    def fetch(self) -> Iterator[NormalizedListing]:
        max_details: int | None = self.param("max_details", 200)
        hint_ids = self._fetch_resale_hint_ids()

        try:
            sitemap_xml = self.fetcher.get_text(SITEMAP_URL)
        except FetchError as exc:
            self.errors.append(f"sitemap: {exc}")
            return
        self.pages_fetched += 1
        urls = re.findall(r"<loc>(.*?)</loc>", sitemap_xml)
        urls = [u for u in urls if "/properties/" in u]
        # newest first (ids are monotonically increasing)
        urls.sort(key=lambda u: int(parse_detail_url(u) or 0), reverse=True)
        if not urls:
            self.errors.append("sitemap contained no property URLs")
            return

        fetched = 0
        for url in urls:
            if max_details is not None and fetched >= max_details:
                return  # truncated by budget: complete stays False
            try:
                html = self.fetcher.get_text(url)
            except FetchError as exc:
                self.errors.append(f"detail: {exc}")
                continue
            self.pages_fetched += 1
            fetched += 1
            parsed = parse_detail(html, url)
            if parsed is None:
                continue
            parsed.scope_key = "all"
            if parsed.is_resale is None and parsed.source_listing_id in hint_ids:
                parsed.is_resale = True
                parsed.resale_evidence = "listed on residential/commercial resale hub"
            yield parsed

        self.complete = not self.errors
        if self.complete:
            self.scopes_completed.add("all")

    def _fetch_resale_hint_ids(self) -> set[str]:
        ids: set[str] = set()
        for path in HUB_PATHS:
            try:
                html = self.fetcher.get_text(urljoin(BASE, path))
            except FetchError as exc:
                self.errors.append(f"hub {path}: {exc}")
                continue
            self.pages_fetched += 1
            for m in re.finditer(r'href="/en/properties/[^"]*?(\d+)"', html):
                ids.add(m.group(1))
        return ids

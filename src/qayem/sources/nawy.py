"""Nawy — resale units, and developer launch (primary) units.

Endpoint: /search?sale_type={resale|developer_sale}&page_number=N&category=property
Data: full unit objects server-rendered into `__NEXT_DATA__`
(loadedSearchResultsSSR.results). Resale units are resale by construction.
Developer-sale units are the developers' own current launch prices and plans; they
are stored as a separate source (`nawy_primary`, is_resale=False) and used only as
the launch-price benchmark, never as resale evidence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import urlencode

from ..http_client import BlockedError, FetchError, HTTPStatusError
from .base import BaseSource, NormalizedListing

FINISHING_MAP = {
    "finished": "finished",
    "fully_finished": "finished",
    "semi_finished": "semi_finished",
    "core_and_shell": "core_shell",
    "not_finished": "core_shell",
}


def extract_next_data(html: str) -> dict | None:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
        html,
        re.S,
    )
    return json.loads(match.group(1)) if match else None


def delivery_date(value) -> str | None:
    """'2026-08-20T00:00:00.000Z' → '2026-08-20'; implausible years are dropped."""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value) if isinstance(value, str) else None
    return match.group(0) if match and 2000 <= int(match.group(1)) <= 2040 else None


def parse_unit(unit: dict, primary: bool = False) -> NormalizedListing | None:
    unit_id = unit.get("id")
    if unit_id is None:
        return None
    plan = unit.get("paymentPlan") or {}
    compound = unit.get("compound") or {}
    developer = unit.get("developer") or {}
    area = unit.get("area") or {}
    title = unit.get("title")
    finishing = unit.get("finishing")
    installment_years = plan.get("numberOfInstallmentYears")

    return NormalizedListing(
        source_listing_id=str(unit_id),
        scope_key="all",
        url=unit.get("shareLink"),
        title=title,
        description=unit.get("subtitle"),
        purpose="sale",
        property_type=(unit.get("propertyType") or "").lower() or None,
        # resale by query construction; saleType double-checks it
        is_resale=not primary,
        resale_evidence=("developer launch: sale_type=developer_sale filter; unit saleType="
                         if primary else "sale_type=resale filter; unit saleType=") + str(unit.get("saleType")),
        price=plan.get("minPrice"),
        currency=plan.get("currency") or "EGP",
        is_installment=(not plan.get("isCash")) and plan.get("minInstallment") is not None,
        down_payment=plan.get("minDownPayment"),
        installment_months=round(installment_years * 12) if installment_years else None,
        area_m2=unit.get("unitArea"),
        bedrooms=unit.get("numberOfBedrooms"),
        bathrooms=unit.get("numberOfBathrooms"),
        delivery_date=delivery_date(unit.get("readyBy")),
        finishing=FINISHING_MAP.get((finishing or "").lower(), (finishing or "").lower() or None),
        compound=compound.get("name"),
        developer=developer.get("name"),
        district=area.get("name"),
        images=[unit["imageUrl"]] if unit.get("imageUrl") else [],
        raw=unit,
    )


def parse_primary_unit(unit: dict) -> NormalizedListing | None:
    return parse_unit(unit, primary=True)


class NawySource(BaseSource):
    name = "nawy"
    SALE_TYPE = "resale"
    SEARCH_URL = "https://www.nawy.com/search"

    def _get_page_verified(self, url: str) -> str:
        """Fetch one search page. A 404 here is ambiguous: it can be the real
        end of the inventory OR a transient edge hiccup (observed live).
        Re-check it before believing it — only a 404 that repeats on every
        retry is treated as the natural end."""
        import time

        for attempt in range(3):
            try:
                return self.fetcher.get_text(url)
            except HTTPStatusError as exc:
                if exc.status != 404:
                    raise
                if attempt < 2:
                    time.sleep(3.0)
        # 404 three times in a row → past the last page
        self.complete = True
        self.scopes_completed.add("all")
        raise HTTPStatusError(url, 404)

    MAX_CONSECUTIVE_FAILURES = 5

    def fetch(self) -> Iterator[NormalizedListing]:
        page = 1
        max_pages = self.param("max_pages")
        failures = 0
        while True:
            url = f"{self.SEARCH_URL}?{urlencode({'sale_type': self.SALE_TYPE, 'page_number': page, 'category': 'property'})}"
            try:
                html = self._get_page_verified(url)
            except HTTPStatusError as exc:
                if exc.status == 404 and self.complete:
                    return  # verified natural end — recorded, not an error
                self.errors.append(f"page {page}: {exc}")
                return
            except BlockedError as exc:
                self.errors.append(f"page {page}: {exc}")
                return  # never push through a WAF block
            except FetchError as exc:
                # A page that fails after all retries is skipped, not fatal: the run is
                # recorded partial (no removals) but the rest of the inventory is refreshed.
                self.errors.append(f"page {page}: {exc}")
                failures += 1
                if failures >= self.MAX_CONSECUTIVE_FAILURES:
                    return
                page += 1
                continue
            failures = 0
            self.pages_fetched += 1
            try:
                data = extract_next_data(html)
                ssr = data["props"]["pageProps"]["loadedSearchResultsSSR"]
            except Exception as exc:  # noqa: BLE001 - malformed/unexpected payload
                self.errors.append(f"page {page}: cannot parse __NEXT_DATA__: {exc}")
                return

            units = ssr.get("results") or []
            for unit in units:
                parsed = parse_unit(unit, primary=self.SALE_TYPE != "resale")
                if parsed is not None:
                    yield parsed

            total = ssr.get("total") or 0
            page_size = ssr.get("pageSize") or 12
            if not units or page * page_size >= total:
                self.complete = True
                self.scopes_completed.add("all")
                return
            if max_pages and page >= max_pages:
                return  # truncated by caller: complete stays False
            page += 1


class NawyPrimarySource(NawySource):
    """Developers' current launch units: the price a buyer would pay the developer today."""

    name = "nawy_primary"
    SALE_TYPE = "developer_sale"

"""AqarExit — Egyptian unit contract-transfer (تنازل) marketplace.

Every unit is a secondary-market transfer whose contract and receipts AqarExit
reviews ("متحقق بالمستندات"), and every unit page publishes the full payment
position: cash required now, the balance still owed to the developer, the
installment and the years left. That makes it the most complete payment data of
any source.

Inventory: `sitemap.xml` lists every live unit page (`/buy/opportunity/{uuid}`,
explicitly allowed by robots.txt) with a `lastmod`. The sitemap is the complete
inventory, so a unit absent from it is removed. Detail pages are fetched only
for units that are new or changed since their stored `lastmod`; the rest are
confirmed present without a fetch. The public /opportunities grid shows only
~340 of ~7,300 units and is not used.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup

from ..http_client import BlockedError, FetchError
from ..normalization import detect_property_type, parse_number
from .base import BaseSource, NormalizedListing

# Without "years left", the term is the balance ÷ the regular installment. Balloon and yearly
# payments make that run long; on units publishing both, a derived term of up to ten years
# puts the plan's present value within about ±13% (p10–p90) of the published one, so longer
# derived terms are not trusted.
DERIVED_TERM_MAX_MONTHS = 120
# No developer plan in Egypt runs this long; a larger "years left" is a typo (a unit publishing 30 years
# pays EGP 12.5M at EGP 175,250 a month: six years), so the term is derived instead.
PUBLISHED_TERM_MAX_YEARS = 15

BASE = "https://aqarexit.com"
SITEMAP_URL = f"{BASE}/sitemap.xml"
DETAIL_PATH = "/buy/opportunity/"

_URL_ENTRY = re.compile(r"<url>\s*<loc>(https://aqarexit\.com/buy/opportunity/([0-9a-f-]{36}))</loc>(.*?)</url>", re.S)
_LASTMOD = re.compile(r"<lastmod>([^<]+)</lastmod>")
FINISHING = {
    "تشطيب كامل": "finished", "متشطب": "finished", "كامل التشطيب": "finished", "مفروش": "furnished",
    "نص تشطيب": "semi_finished", "نصف تشطيب": "semi_finished", "بدون تشطيب": "core_shell",
    "على الطوب": "core_shell", "طوب أحمر": "core_shell",
}
FREQUENCY = {"شهري": 1, "ربع سنوي": 3, "نصف سنوي": 6, "سنوي": 12}


def parse_sitemap(xml: str) -> dict[str, str | None]:
    """→ {unit uuid: lastmod} for every unit page in the sitemap."""
    units: dict[str, str | None] = {}
    for _url, uid, rest in _URL_ENTRY.findall(xml):
        match = _LASTMOD.search(rest)
        units[uid] = match.group(1) if match else None
    return units


def _pairs(soup: BeautifulSoup) -> dict[str, str]:
    """Spec grid (<p>label</p><p><bdi>value</bdi></p>) and payment list (<dt>/<dd>)."""
    pairs: dict[str, str] = {}
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd is not None:
            pairs[dt.get_text(" ", strip=True)] = dd.get_text(" ", strip=True)
    for label in soup.find_all("p"):
        value = label.find_next_sibling("p")
        if value is not None and value.find("bdi") is not None and not label.find("bdi"):
            pairs.setdefault(label.get_text(" ", strip=True), value.get_text(" ", strip=True))
    return pairs


def _pick(pairs: dict[str, str], prefix: str) -> str | None:
    return next((value for label, value in pairs.items() if label.startswith(prefix)), None)


def _jsonld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return {}


def _images(product: dict) -> list[str]:
    """The unit's own photos, as the page's structured data lists them (the page also shows other units' photos)."""
    value = product.get("image") or []
    urls = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return list(dict.fromkeys(u for u in urls if isinstance(u, str) and u.startswith("https://")))


def images_from_page(html: str) -> list[str]:
    return _images(_jsonld(BeautifulSoup(html, "lxml")))


def parse_detail(html: str, uid: str, lastmod: str | None = None) -> NormalizedListing | None:
    soup = BeautifulSoup(html, "lxml")
    product = _jsonld(soup)
    pairs = _pairs(soup)
    extra = {p.get("name"): p.get("value") for p in product.get("additionalProperty") or [] if isinstance(p, dict)}
    h1 = soup.find("h1")
    compound = h1.get_text(" ", strip=True) if h1 else None
    subline = h1.find_next("p").get_text(" ", strip=True) if h1 and h1.find_next("p") else ""
    parts = [part.strip() for part in subline.split("·") if part.strip()]
    developer = parts[0] if parts else (product.get("brand") or {}).get("name")
    district = extra.get("المنطقة") or (parts[1] if len(parts) > 1 else None)

    cash_now = None
    cash_label = soup.find(string=re.compile("المطلوب كاش دلوقتي"))
    if cash_label is not None and cash_label.find_next("bdi") is not None:
        cash_now = parse_number(cash_label.find_next("bdi").get_text())
    if cash_now is None:
        cash_now = (product.get("offers") or {}).get("price")
    note = None
    if cash_label is not None:
        amount = cash_label.find_next("p")
        note_tag = amount.find_next("p") if amount is not None else None
        note = note_tag.get_text(" ", strip=True) if note_tag is not None and "أوفر" in note_tag.get_text() else None
    remaining = parse_number(_pick(pairs, "المتبقي للمطور")) or 0.0
    years = parse_number(_pick(pairs, "باقي على خلاص التقسيط"))
    installment_text = _pick(pairs, "القسط") or ""
    frequency = next((months for word, months in sorted(FREQUENCY.items(), key=lambda kv: -len(kv[0]))
                      if word in installment_text), None)
    if cash_now is None:
        return None

    kind_text = pairs.get("النوع") or extra.get("نوع الوحدة") or ""
    finishing_text = pairs.get("التشطيب") or ""
    status_text = pairs.get("حالة الاستلام") or extra.get("حالة الاستلام") or ""
    delivery_year = parse_number(str(extra.get("سنة الاستلام") or _pick(pairs, "الاستلام") or ""))
    verified = soup.find(string=re.compile("متحقق بالمستندات")) is not None
    code = soup.find(string=re.compile(r"^U-\d+$"))
    price = cash_now + remaining
    return NormalizedListing(
        source_listing_id=uid,
        scope_key="all",
        url=f"{BASE}{DETAIL_PATH}{uid}",
        title=f"{kind_text} — {compound}" if compound and kind_text else compound,
        description=product.get("description"),
        purpose="sale",
        property_type=detect_property_type(kind_text) or (kind_text.lower() or None),
        is_resale=True,
        resale_evidence="contract transfer (تنازل)" + ("; contract and receipts verified by AqarExit" if verified else ""),
        price=price,
        currency="EGP",
        is_installment=remaining > 0,
        down_payment=cash_now,
        installment_months=plan_months(years, remaining, parse_number(installment_text), frequency),
        area_m2=parse_number(pairs.get("المساحة")),
        bedrooms=int(parse_number(pairs.get("غرف")) or 0) or None,
        bathrooms=int(parse_number(pairs.get("حمامات")) or 0) or None,
        finishing=next((value for word, value in FINISHING.items() if word in finishing_text), None),
        delivery_status="ready_to_move" if re.search("فوري|جاهز|مستلم|تم الاستلام", status_text) else
        ("under_construction" if status_text else None),
        delivery_date=f"{int(delivery_year)}-06-30" if delivery_year and 2000 <= delivery_year <= 2040 else None,
        compound=compound,
        developer=developer,
        district=district,
        seller_type="owner",
        images=_images(product),
        raw={
            "lastmod": lastmod, "unit_code": code.strip() if code else None, "documents_verified": verified,
            "cash_required_now": cash_now, "remaining_to_developer": remaining,
            "installment": parse_number(installment_text), "installment_every_months": frequency,
            "years_left": years, "floor": _pick(pairs, "الدور"), "contract_year": _pick(pairs, "سنة التعاقد"),
            "contract_price_per_m2": parse_number(_pick(pairs, "سعر المتر بالتعاقد")),
            "overpayment_note": note, "delivery_year": delivery_year,
        },
    )


def plan_months(years: float | None, remaining: float | None, installment: float | None,
                frequency: int | None) -> int | None:
    """Months of installments left: published, or derived from the balance and the installment."""
    if not remaining or remaining <= 0:
        return None
    if years and years <= PUBLISHED_TERM_MAX_YEARS:
        return round(years * 12)
    if installment and installment > 0 and frequency:
        months = math.ceil(remaining / installment) * frequency
        return months if months <= DERIVED_TERM_MAX_MONTHS else None
    return None


def terms_from_raw(raw: dict | None) -> dict:
    """Backfill for stored units (the incremental crawl never refetches unchanged pages)."""
    raw = raw or {}
    months = plan_months(raw.get("years_left"), raw.get("remaining_to_developer"), raw.get("installment"),
                         raw.get("installment_every_months"))
    return {"installment_months": months} if months else {}


class AqarExitSource(BaseSource):
    name = "aqarexit"
    wants_known = True  # the engine passes {id: stored lastmod} so unchanged units are not refetched

    def fetch(self) -> Iterator[NormalizedListing]:
        known: dict[str, str | None] = self.param("known") or {}
        max_details = self.param("max_details")
        try:
            sitemap = parse_sitemap(self.fetcher.get_text(SITEMAP_URL))
        except FetchError as exc:
            self.errors.append(f"sitemap: {exc}")
            return
        self.pages_fetched += 1
        if len(sitemap) < 100:
            self.errors.append(f"sitemap lists only {len(sitemap)} units; refusing to treat it as complete")
            return
        # The sitemap is the whole inventory: everything in it is present tonight, and
        # removals are safe even if the detail budget runs out before every change is fetched.
        self.present_ids = set(sitemap)
        self.complete = True
        self.scopes_completed.add("all")

        new = [uid for uid in sitemap if uid not in known]
        changed = [uid for uid in sitemap if uid in known and known[uid] != sitemap[uid]]
        fetched = 0
        for uid in new + changed:
            if max_details is not None and fetched >= max_details:
                self.errors.append(f"detail budget reached; {len(new) + len(changed) - fetched} units left for the next run")
                return
            try:
                html = self.fetcher.get_text(f"{BASE}{DETAIL_PATH}{uid}")
            except BlockedError as exc:
                self.errors.append(f"detail {uid}: {exc}")
                return
            except FetchError as exc:
                self.errors.append(f"detail {uid}: {exc}")
                continue
            self.pages_fetched += 1
            fetched += 1
            parsed = parse_detail(html, uid, sitemap[uid])
            if parsed is not None:
                yield parsed

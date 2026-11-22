"""Public official reference data: Egypt fee schedules, CAPMAS and NUCA announcements (docs/STRATEGY.md 5.2 B).

Everything here reads only public pages (respecting robots.txt, stopping on any block) or checked-in
yearly statutory fee schedules. A missing or unreachable government page never stops publication.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

FEE_SCHEDULES = Path(__file__).resolve().parent / "data" / "fee_schedules.json"
CAPMAS_URL = "https://www.capmas.gov.eg/Pages/StaticPages.aspx?page_id=5035"
NUCA_URL = "https://www.newcities.gov.eg/"


def _text_of(html: str) -> str:
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return " ".join(cleaned.split())


def fee_schedules() -> dict:
    """Yearly registry, transfer and buying-cost schedules (Law 9/2022 & market norms)."""
    try:
        return json.loads(FEE_SCHEDULES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"year": 2026, "items": []}


def parse_capmas_inflation(html: str) -> dict | None:
    """Extract headline CPI/inflation figure when CAPMAS's public page publishes it."""
    text = _text_of(html)
    for pattern in (
        r"(?:Annual\s+Inflation|التضخم\s+السنوي)[^0-9]{0,40}(\d+(?:\.\d+)?)\s*%",
        r"(?:CPI|الرقم\s+القياسي)[^0-9]{0,40}(\d+(?:\.\d+)?)",
    ):
        if match := re.search(pattern, text, re.I):
            value = float(match.group(1))
            if 0 < value < 200:
                return {"metric": "capmas_inflation", "value": value, "source": "CAPMAS", "url": CAPMAS_URL}
    return None


def parse_nuca_announcements(html: str) -> list[dict]:
    """Recent public housing / land allotment notices from NUCA's home page."""
    found = []
    for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S):
        title = " ".join(re.sub(r"<[^>]+>", " ", label).split())
        if len(title) < 18 or len(title) > 220:
            continue
        if re.search(r"طرح|أراض|إسكان|سكن مصر|دار مصر|جنة|متر|مليون|allotment|housing|land", title, re.I):
            url = href if href.startswith("http") else NUCA_URL.rstrip("/") + "/" + href.lstrip("/")
            found.append({"title": title, "url": url})
            if len(found) >= 10:
                break
    return found


def fetch_official(client=None) -> dict:
    """Best-effort fetch of public CAPMAS and NUCA benchmarks; returns what answered 200."""
    import httpx
    from .config import USER_AGENT

    own = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    out: dict = {"day": date.today().isoformat(), "fetched_at": datetime.now(timezone.utc).isoformat(),
                 "capmas": None, "nuca": []}
    try:
        for name, url in (("capmas", CAPMAS_URL), ("nuca", NUCA_URL)):
            try:
                response = client.get(url)
                if response.status_code != 200:
                    continue
                if name == "capmas":
                    out["capmas"] = parse_capmas_inflation(response.text)
                else:
                    out["nuca"] = parse_nuca_announcements(response.text)
            except httpx.HTTPError:
                continue
    finally:
        if own:
            client.close()
    return out

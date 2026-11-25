"""Egypt's economic and market signals around the price guide (docs/DATA_SOURCES.md).

One nightly stage, `qayem fetch-signals`, reads every source that a script may read and keeps what each
says as dated figures (`market_signals`) and events (`market_events`):

- structured, parsed as data: CAPMAS's JSON API (headline indicators, release calendar), Binance P2P
  USDT/EGP (the market price of the dollar), the World Bank and DBnomics (IMF) APIs;
- unstructured, read by Claude Opus 5.5 at medium effort (`claude_cli`, never regular expressions):
  gold prices, NUCA's notices, the CBE's balance of payments sheet, Marsad Omran's rent indices, the FRA's
  financing statistics, the official real-estate platform's offers, and the property news.

Every figure Claude returns carries a quote; it is kept only when the quote is in the source and its
number is in the quote. A document already read (same address and content) is not sent again. A source
that fails, blocks or is unreachable is reported and skipped: it never stops the others or publication.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import io
import json
import sqlite3
import statistics
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from bs4 import BeautifulSoup
import httpx

from . import claude_cli, market
from .config import USER_AGENT

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_signals (
  name TEXT NOT NULL, period TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL, label TEXT NOT NULL,
  source TEXT NOT NULL, source_url TEXT, quote TEXT, day TEXT NOT NULL, fetched_at TEXT NOT NULL,
  PRIMARY KEY(name, period)
);
CREATE TABLE IF NOT EXISTS market_events (
  key TEXT PRIMARY KEY, kind TEXT NOT NULL, day TEXT NOT NULL, title TEXT NOT NULL, url TEXT, source TEXT NOT NULL,
  summary TEXT, figures TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_documents (
  url TEXT PRIMARY KEY, sha256 TEXT NOT NULL, fetched_at TEXT NOT NULL
);
"""

CAPMAS_API = "https://www.capmas.gov.eg:8080/api"
NUCA_PAGES = ("http://www.newcities.gov.eg/", "https://www.newcities.gov.eg/")  # https times out from Egypt
BINANCE_P2P = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
GOLD_URL = "https://www.isagha.com/"
CBE_BOP_LIST = ("https://www.cbe.org.eg/en/economic-research/time-series/downloadlist"
                "?category=232131B16F15454BB1E1933B2BFEB041")
WORLD_BANK = "https://api.worldbank.org/v2/country/EGY/indicator/{code}?format=json&mrv=5"
DBNOMICS = "https://api.db.nomics.world/v22/series/{series}?observations=1"
MARSAD_POSTS = "https://marsadomran.info/wp-json/wp/v2/posts"
FRA_POSTS = "https://fra.gov.eg/en/wp-json/wp/v2/fra_news"
PLATFORM_POSTS = "https://blogs.realestate.gov.eg/wp-json/wp/v2/news"  # the platform's news, not its guides
RSS_FEEDS = (("Daily News Egypt", "https://www.dailynewsegypt.com/feed/"),
             ("Enterprise", "https://enterpriseam.com/egypt/feed/"))  # Google News: robots.txt disallows its feeds
WP_NEWS = (("Amwal Al Ghad", "https://amwalalghad.com/wp-json/wp/v2/posts"),
           ("Al Borsa News", "https://www.alborsaanews.com/wp-json/wp/v2/posts"),
           ("Invest-Gate", "https://invest-gate.me/wp-json/wp/v2/posts"))
NEWS_DAYS = 3
EVENT_DAYS = 60

CAPMAS_NAMES = {"Annually inflation rate %": ("capmas_inflation_annual", "percent"),
                "Inflation rate %": ("capmas_inflation_year", "percent"),
                "Unemployment rate": ("capmas_unemployment", "percent"),
                "Annual Unemployment rate": ("capmas_unemployment_year", "percent"),
                "Contribution rate in Economic Activity": ("capmas_participation", "percent"),
                "Annual Operating rate": ("capmas_employment_year", "percent"),
                "Foreign Trade - Imports": ("capmas_imports", "usd_mn"),
                "Foreign Trade - Exports": ("capmas_exports", "usd_mn")}
ARABIC_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "إبريل": 4, "مايو": 5, "يونيو": 6,
                 "يونية": 6, "يوليو": 7, "يوليه": 7, "اغسطس": 8, "أغسطس": 8, "سبتمبر": 9, "اكتوبر": 10,
                 "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}
ARABIC_QUARTERS = {"الأول": 1, "الاول": 1, "الثانى": 2, "الثاني": 2, "الثالث": 3, "الرابع": 4}
WORLD_BANK_SERIES = {"FP.CPI.TOTL.ZG": ("wb_inflation", "percent", "Consumer price inflation (annual %)"),
                     "NY.GDP.MKTP.KD.ZG": ("wb_gdp_growth", "percent", "Real GDP growth (annual %)"),
                     "NY.GDP.PCAP.CD": ("wb_gdp_per_capita", "usd", "GDP per person (current USD)"),
                     "SP.POP.TOTL": ("wb_population", "count", "Population"),
                     "SP.URB.TOTL.IN.ZS": ("wb_urban_share", "percent", "Urban population (% of total)"),
                     "BX.TRF.PWKR.CD.DT": ("wb_remittances", "usd", "Personal remittances received (current USD)")}
DBNOMICS_SERIES = {"IMF/IFS/M.EG.PCPI_IX": ("imf_cpi_index", "index", "Consumer price index (IMF IFS)"),
                   "IMF/IFS/M.EG.FPOLM_PA": ("imf_policy_rate", "percent", "Monetary policy rate (IMF IFS)"),
                   "IMF/IFS/M.EG.FIDR_PA": ("imf_deposit_rate", "percent", "Average deposit rate (IMF IFS)"),
                   "IMF/IFS/M.EG.FILR_PA": ("imf_lending_rate", "percent", "Average lending rate (IMF IFS)")}


@dataclass
class Collected:
    signals: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    documents: list[tuple[str, str]] = field(default_factory=list)  # (url, sha256) read for good
    note: str = ""


@dataclass
class Context:
    client: httpx.Client
    connection: sqlite3.Connection
    extract: Callable[[str, dict, str], dict]
    today: date
    robots: dict = field(default_factory=dict)

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self.robots:
            parser = RobotFileParser()
            try:
                response = self.client.get(root + "/robots.txt")
                parser.parse(response.text.splitlines() if response.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])
            self.robots[root] = parser
        return self.robots[root].can_fetch(USER_AGENT, url)

    def get(self, url: str, **kwargs) -> httpx.Response:
        if not self.allowed(url):
            raise Blocked("robots.txt")
        response = self.client.get(url, **kwargs)
        if response.status_code in (202, 401, 403, 429, 503):
            raise Blocked(f"HTTP {response.status_code}")
        response.raise_for_status()
        return response

    def seen(self, url: str, sha: str) -> bool:
        row = self.connection.execute("SELECT sha256 FROM signal_documents WHERE url=?", (url,)).fetchone()
        return bool(row and row[0] == sha)


class Blocked(RuntimeError):
    """The source refused or robots.txt disallows the path: it is left alone (docs/STRATEGY.md 5.1)."""


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text if isinstance(text, bytes) else text.encode("utf-8")).hexdigest()


def slug(text: str) -> str:
    words = "".join(c if c.isalnum() else " " for c in (text or "").casefold()).split()
    return "-".join(words)[:60] or "all"


def signal(name: str, period: str, value: float, unit: str, label: str, source: str, url: str | None,
           quote: str | None = None) -> dict:
    return {"name": name, "period": period, "value": float(value), "unit": unit, "label": label, "source": source,
            "source_url": url, "quote": quote}


def month_period(text: str) -> str | None:
    """«YYYY-MM» if `text` is one (as Claude is asked to write it), else None."""
    parts = (text or "").strip().split("-")
    if len(parts) == 2 and len(parts[0]) == 4 and parts[0].isdigit() and parts[1].isdigit() and 1 <= int(parts[1]) <= 12:
        return f"{parts[0]}-{int(parts[1]):02d}"
    return None


def quarter_of(month: str | None) -> str | None:
    if not month:
        return None
    year, number = month.split("-")
    return f"{year}-Q{(int(number) - 1) // 3 + 1}"


def capmas_period(text: str) -> str:
    """CAPMAS's Arabic study period as «2026-10», «2026-Q2» or «2025» (the raw text when unknown)."""
    words = (text or "").split()
    year = next((w for w in words if len(w) == 4 and w.isdigit()), None)
    if not year:
        return (text or "").strip()
    for word in words:
        if word in ARABIC_MONTHS:
            return f"{year}-{ARABIC_MONTHS[word]:02d}"
        if word in ARABIC_QUARTERS:
            return f"{year}-Q{ARABIC_QUARTERS[word]}"
    return year


def named_district(name: str):
    """The guide district a neighbourhood's name is part of («Dokki» → Mohandessin & Dokki), else None.

    Only a district whose own name carries the neighbourhood's words counts: a neighbourhood that merely lies
    inside a wider district (Zamalek in Central Cairo) is not set against that district's prices.
    """
    place = market.match(name)
    words = set(market.fold(name).split())
    return place if place and words and words <= set(market.fold(place.name).split()) else None


def figures_checked(figures: list[dict], text: str) -> list[dict]:
    return [{**f, "checked": True} for f in figures if claude_cli.checked(f, text)]


# --- structured sources -----------------------------------------------------------------------

def capmas(ctx: Context) -> Collected:
    out = Collected()
    headers = {"Referer": "https://www.capmas.gov.eg/"}
    if not ctx.allowed("https://www.capmas.gov.eg/"):
        raise Blocked("robots.txt")
    response = ctx.client.get(f"{CAPMAS_API}/SelectedIndicator", headers=headers)
    response.raise_for_status()
    for item in response.json().get("data") or []:
        english = next((t for t in item.get("selectedIndicatorTranslations") or [] if t.get("locale") == "en"), {})
        title = " ".join((english.get("title") or item.get("title") or "").split())
        if not isinstance(item.get("value"), (int, float)) or not title:
            continue
        name, unit = CAPMAS_NAMES.get(title, (f"capmas_{slug(title).replace('-', '_')}",
                                              "percent" if item.get("unit") == "%" else "value"))
        # The Arabic study period is the one CAPMAS keeps current (the English one lags).
        out.signals.append(signal(name, capmas_period(item.get("studyPeriod") or ""), item["value"], unit, title,
                                  "CAPMAS", "https://www.capmas.gov.eg/"))
    calendar = ctx.client.get(f"{CAPMAS_API}/Calendar/GetHomeCalendar", headers=headers)
    if calendar.status_code == 200:
        for entry in calendar.json().get("data") or []:
            publication = entry.get("publication") or {}
            english = next(iter(publication.get("publicationTranslations") or []), {})
            title = english.get("name") or publication.get("name")
            day = (entry.get("date") or "")[:10]
            if title and day:
                out.events.append({"key": f"capmas_release:{day}:{publication.get('id')}", "kind": "capmas_release",
                                   "day": day, "title": title, "url": "https://www.capmas.gov.eg/", "source": "CAPMAS",
                                   "summary": None, "figures": []})
    return out


def binance(ctx: Context) -> Collected:
    """The median of the first ten P2P adverts each way: what the dollar (USDT) costs in pounds today."""
    out = Collected()
    day = ctx.today.isoformat()
    prices = {}
    for side in ("BUY", "SELL"):
        response = ctx.client.post(BINANCE_P2P, json={"asset": "USDT", "fiat": "EGP", "tradeType": side, "page": 1,
                                                      "rows": 10, "payTypes": [], "publisherType": None})
        response.raise_for_status()
        values = [float(entry["adv"]["price"]) for entry in response.json().get("data") or []
                  if entry.get("adv", {}).get("price")]
        if len(values) >= 3:
            prices[side] = statistics.median(values)
    labels = {"BUY": "USDT/EGP on Binance P2P, to buy dollars (median of 10 offers)",
              "SELL": "USDT/EGP on Binance P2P, to sell dollars (median of 10 offers)"}
    for side, value in prices.items():
        out.signals.append(signal(f"usdt_egp_p2p_{side.lower()}", day, round(value, 4), "egp", labels[side],
                                  "Binance P2P", "https://p2p.binance.com/en/trade/all-payments/USDT?fiat=EGP"))
    if len(prices) == 2:
        out.signals.append(signal("usdt_egp_p2p", day, round((prices["BUY"] + prices["SELL"]) / 2, 4), "egp",
                                  "USDT/EGP on Binance P2P (midpoint)", "Binance P2P",
                                  "https://p2p.binance.com/en/trade/all-payments/USDT?fiat=EGP"))
    return out


def world_bank(ctx: Context) -> Collected:
    out = Collected()
    for code, (name, unit, label) in WORLD_BANK_SERIES.items():
        url = WORLD_BANK.format(code=code)
        payload = ctx.get(url).json()
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and payload[1] else []
        latest = next((row for row in rows if row.get("value") is not None), None)
        if latest:
            out.signals.append(signal(name, str(latest["date"]), latest["value"], unit, label, "World Bank",
                                      f"https://data.worldbank.org/indicator/{code}?locations=EG"))
    return out


def dbnomics(ctx: Context) -> Collected:
    out = Collected()
    for series, (name, unit, label) in DBNOMICS_SERIES.items():
        response = ctx.client.get(DBNOMICS.format(series=series))
        if response.status_code != 200:
            continue
        docs = (response.json().get("series") or {}).get("docs") or []
        if not docs:
            continue
        pairs = [(p, v) for p, v in zip(docs[0].get("period") or [], docs[0].get("value") or [])
                 if isinstance(v, (int, float))]
        if pairs:
            period, value = pairs[-1]
            out.signals.append(signal(name, period, round(value, 4), unit, label, "IMF via DBnomics",
                                      f"https://db.nomics.world/{series}"))
    return out


# --- sources read by Claude -------------------------------------------------------------------

def _figure_items(names: list[str] | None, units: list[str] | None = None, extra: dict | None = None) -> dict:
    properties = {"name": {"type": "string", **({"enum": names} if names else {})},
                  "value": {"type": "number"},
                  "quote": {"type": "string", "description": "the exact words of the source that state the number"}}
    if units:
        properties["unit"] = {"type": "string", "enum": units}
    properties.update(extra or {})
    return {"type": "object", "required": list(properties), "additionalProperties": False, "properties": properties}


GOLD_SCHEMA = {"type": "object", "required": ["prices"], "additionalProperties": False, "properties": {
    "prices": {"type": "array", "maxItems": 6, "items": {
        "type": "object", "required": ["item", "buy", "sell", "quote"], "additionalProperties": False, "properties": {
            "item": {"type": "string", "enum": ["24k", "21k", "18k", "gold_pound"]},
            "buy": {"type": "number"}, "sell": {"type": "number"},
            "quote": {"type": "string", "description": "the exact words of the page with both prices"}}}}}}
GOLD_INSTRUCTIONS = """You read an Egyptian gold dealer's price page. Return today's gold prices in Egyptian pounds:
per gram for 24, 21 and 18 karat, and the gold pound (جنيه ذهب), each with the page's two prices (شراء = buy,
بيع = sell) exactly as written, and the words of the page that state them. Leave out silver and anything else."""


def gold(ctx: Context) -> Collected:
    out = Collected()
    text = claude_cli.page_text(ctx.get(GOLD_URL).text)
    result = ctx.extract(text, GOLD_SCHEMA, GOLD_INSTRUCTIONS)
    day = ctx.today.isoformat()
    for item in result["prices"]:
        quote = item["quote"]
        if not (claude_cli.quoted(quote, text) and claude_cli.number_in(item["buy"], quote)
                and claude_cli.number_in(item["sell"], quote)):
            continue
        unit, what = ("egp", "a gold pound (8 g, 21 karat)") if item["item"] == "gold_pound" else \
            ("egp_per_g", f"a gram of {item['item'][:2]}-karat gold")
        name = "gold_pound" if item["item"] == "gold_pound" else f"gold_{item['item']}"
        out.signals.append(signal(name, day, round((item["buy"] + item["sell"]) / 2, 2), unit,
                                  f"Price of {what} (midpoint of buy {item['buy']:g} and sell {item['sell']:g})",
                                  "iSagha", GOLD_URL, quote))
    return out


NUCA_SCHEMA = {"type": "object", "required": ["notices"], "additionalProperties": False, "properties": {
    "notices": {"type": "array", "maxItems": 12, "items": {
        "type": "object", "required": ["title", "kind", "link", "quote"], "additionalProperties": False, "properties": {
            "title": {"type": "string", "description": "the notice's title as written"},
            "kind": {"type": "string", "enum": ["land_offer", "housing_offer", "auction", "lottery", "tender", "other"]},
            "link": {"type": ["string", "null"], "description": "the notice's link, copied from the LINKS list"},
            "quote": {"type": "string", "description": "the exact words of the page naming the notice"}}}}}}
NUCA_INSTRUCTIONS = """You read the home page of Egypt's New Urban Communities Authority (هيئة المجتمعات العمرانية).
List its current public notices about land or housing for sale or allotment, auctions, lotteries and tenders: the title
as written, its kind, its link (copied exactly from LINKS, or null) and the page's words naming it. Leave out menus,
ministers' visits and general news."""


def nuca(ctx: Context) -> Collected:
    out = Collected()
    page, html = None, ""
    for url in NUCA_PAGES:
        try:
            response = ctx.client.get(url, timeout=20)
        except httpx.HTTPError:
            continue
        if response.status_code == 200:
            page, html = url, response.text
            break
    if not page:
        raise RuntimeError("NUCA's home page did not answer")
    soup = BeautifulSoup(html, "lxml")
    links = {}
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.get_text(" ", strip=True).split())
        href = anchor["href"].strip()
        if label and not href.startswith(("javascript:", "#", "mailto:")):
            links[urljoin(page, href)] = label
    text = claude_cli.page_text(html)
    digest = sha(text)
    if ctx.seen(page, digest):
        out.note = "unchanged"
        return out
    listing = "\n".join(f"{label} -> {url}" for url, label in links.items())
    result = ctx.extract(f"PAGE TEXT:\n{text}\n\nLINKS:\n{listing}", NUCA_SCHEMA, NUCA_INSTRUCTIONS)
    for notice in result["notices"]:
        if not claude_cli.quoted(notice["quote"], text):
            continue
        link = notice["link"] if notice["link"] in links else None
        out.events.append({"key": f"nuca:{sha(notice['title'])[:16]}", "kind": "nuca_notice", "day": ctx.today.isoformat(),
                           "title": notice["title"], "url": link or page, "source": "NUCA", "summary": notice["kind"],
                           "figures": []})
    out.documents.append((page, digest))
    return out


BOP_ITEMS = ["workers_remittances", "travel_receipts", "suez_canal_receipts", "fdi_in_egypt_net",
             "portfolio_in_egypt_net", "current_account", "overall_balance"]
BOP_LABELS = {"workers_remittances": "Workers' remittances", "travel_receipts": "Tourism (travel) receipts",
              "suez_canal_receipts": "Suez Canal receipts", "fdi_in_egypt_net": "Foreign direct investment in Egypt (net)",
              "portfolio_in_egypt_net": "Portfolio investment in Egypt (net)",
              "current_account": "Current account balance", "overall_balance": "Overall balance of payments"}
BOP_SCHEMA = {"type": "object", "required": ["quarter_end_month", "figures"], "additionalProperties": False, "properties": {
    "quarter_end_month": {"type": "string", "description": "the last month of the latest quarter in the sheet, as YYYY-MM"},
    "figures": {"type": "array", "maxItems": 7, "items": _figure_items(BOP_ITEMS)}}}
BOP_INSTRUCTIONS = """You read the Central Bank of Egypt's quarterly balance of payments sheet (US$ million), given
as rows of cells separated by « | ». For the LATEST quarter column only, return: workers' remittances, travel receipts,
Suez Canal receipts, net direct investment in Egypt, net portfolio investment in Egypt, the current account balance and
the overall balance. Copy each value exactly as in the sheet, and as the quote copy the sheet's whole row for it."""


def _cell(value) -> str:
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(round(value, 3))
    return " ".join(str(value).split())


def workbook_text(content: bytes) -> str:
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    lines = []
    for sheet in book.worksheets[:3]:
        lines.append(f"## {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [_cell(v) for v in row if v not in (None, "")]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _fiscal_years(name: str) -> tuple[float, ...]:
    return tuple(n for n in claude_cli.numbers(name.replace("_", " ").replace("-", " ")) if 2000 <= n <= 2100)


def cbe_bop(ctx: Context) -> Collected:
    out = Collected()
    soup = BeautifulSoup(ctx.get(CBE_BOP_LIST).text, "lxml")
    files = [urljoin(CBE_BOP_LIST, a["href"]) for a in soup.find_all("a", href=True)
             if a["href"].casefold().endswith(".xlsx") and "quarter" in a["href"].casefold()]
    dated = [(years, url) for url in files if len(years := _fiscal_years(urlsplit(url).path.rsplit("/", 1)[-1])) >= 2]
    if not dated:
        raise RuntimeError("no quarterly balance-of-payments sheet listed")
    url = max(dated)[1]
    response = ctx.get(url)
    text = workbook_text(response.content)
    digest = sha(response.content)
    if ctx.seen(url, digest):
        out.note = "unchanged"
        return out
    result = ctx.extract(text, BOP_SCHEMA, BOP_INSTRUCTIONS)
    quarter = quarter_of(month_period(result["quarter_end_month"]))
    if not quarter:
        raise RuntimeError("the latest quarter was not read")
    for figure in figures_checked(result["figures"], text):
        out.signals.append(signal(f"cbe_bop_{figure['name']}", quarter, figure["value"], "usd_mn",
                                  f"{BOP_LABELS[figure['name']]} (US$ million, quarter)", "Central Bank of Egypt", url,
                                  figure["quote"][:300]))
    out.documents.append((url, digest))
    return out


RENT_SCHEMA = {"type": "object", "required": ["city", "quarter_end_month", "figures"], "additionalProperties": False,
               "properties": {
    "city": {"type": "string", "description": "the city the index covers, in English (Cairo, Giza, Alexandria…)"},
    "quarter_end_month": {"type": "string", "description": "last month of the period the index covers, YYYY-MM"},
    "figures": {"type": "array", "maxItems": 40, "items": _figure_items(
        ["median_rent_month", "rent_per_m2_month", "change_on_quarter_pct", "change_on_year_pct"],
        extra={"area": {"type": "string", "description": "«city» for the whole city, else the neighbourhood's name as "
                                                         "written in English"}})}}}
RENT_INSTRUCTIONS = """You read a rent price index published by Marsad Omran (an Egyptian built-environment
observatory): median monthly asking rents of unfurnished apartments. Return the city, the last month of the period
covered, and every figure the text states: the median monthly rent in EGP, the monthly rent per square metre in EGP,
and percentage changes on the previous quarter or year, for the whole city (area «city») or a named neighbourhood.
Copy each number exactly and quote the sentence that states it."""


def _wp_posts(ctx: Context, url: str, params: dict) -> list[dict]:
    response = ctx.get(url, params=params)
    posts = response.json()
    return posts if isinstance(posts, list) else []


def _field(post: dict, name: str) -> str:
    value = post.get(name)
    return value.get("rendered", "") if isinstance(value, dict) else (value or "")


def marsad(ctx: Context) -> Collected:
    out = Collected()
    posts = _wp_posts(ctx, MARSAD_POSTS, {"per_page": 6, "search": "Rent Price Index",
                                          "_fields": "id,date,link,title,content"})
    for post in posts:
        title = claude_cli.page_text(_field(post, "title"))
        if "rent price index" not in title.casefold():
            continue
        link = post.get("link") or f"{MARSAD_POSTS}/{post.get('id')}"
        text = claude_cli.page_text(_field(post, "content"))
        digest = sha(text)
        if ctx.seen(link, digest) or not text:
            continue
        result = ctx.extract(f"{title}\n\n{text}", RENT_SCHEMA, RENT_INSTRUCTIONS)
        quarter = quarter_of(month_period(result["quarter_end_month"]))
        city = result["city"].strip()
        if not quarter or not city:
            continue
        figures = figures_checked(result["figures"], text)
        for figure in figures:
            area = figure["area"].strip()
            whole = area.casefold() == "city"
            place = None if whole else named_district(area)
            figure["district"] = place.key if place else None  # the guide district the neighbourhood names
            where = slug(city if whole else area)  # one signal per neighbourhood, never merged into a district
            unit = "percent" if figure["name"].endswith("_pct") else "egp_per_m2_month" \
                if figure["name"] == "rent_per_m2_month" else "egp_month"
            label = f"{figure['name'].replace('_', ' ')}: {city if area.casefold() == 'city' else area} ({city})"
            out.signals.append(signal(f"rent_{figure['name']}:{slug(city)}:{where}", quarter, figure["value"], unit,
                                      label, "Marsad Omran", link, figure["quote"][:300]))
        if figures:
            out.events.append({"key": f"rent_index:{slug(city)}:{quarter}", "kind": "rent_index",
                               "day": (post.get("date") or ctx.today.isoformat())[:10], "title": title, "url": link,
                               "source": "Marsad Omran", "summary": f"{city} rent price index, {quarter}",
                               "figures": figures})
        out.documents.append((link, digest))
    return out


FRA_ITEMS = ["mortgage_finance", "mortgage_clients", "nonbank_finance_total", "real_estate_funds", "consumer_finance"]
FRA_SCHEMA = {"type": "object", "required": ["posts"], "additionalProperties": False, "properties": {
    "posts": {"type": "array", "maxItems": 15, "items": {
        "type": "object", "required": ["post", "period_end_month", "figures"], "additionalProperties": False,
        "properties": {
            "post": {"type": "integer", "description": "the post's number in the list"},
            "period_end_month": {"type": "string", "description": "last month the figures cover, YYYY-MM"},
            "figures": {"type": "array", "maxItems": 8, "items": _figure_items(
                FRA_ITEMS, ["egp_bn", "egp_mn", "count"], {"basis": {
                    "type": "string", "enum": ["month", "year_to_date", "outstanding"],
                    "description": "one month's flow, the year so far, or the portfolio outstanding"}})}}}}}}
FRA_INSTRUCTIONS = """You read press releases of Egypt's Financial Regulatory Authority (FRA), numbered [1], [2]…
Only for releases that report financing statistics, return the last month covered and the figures stated outright:
mortgage finance granted (value), mortgage clients or contracts (count), total non-bank financing, real-estate funds and
consumer finance, each with its unit (egp_bn, egp_mn or count) as written, its basis (one month, the year so far, or the
portfolio outstanding) and the words that state it. Leave out licences, meetings and events."""


def _batch(posts: list[tuple[str, str, str]]) -> str:
    return "\n\n".join(f"[{n}] {title}\n{text[:3500]}" for n, (_, title, text) in enumerate(posts, 1))


def fra(ctx: Context) -> Collected:
    out = Collected()
    posts, links = [], set()
    # The monthly statistics releases («Financing Granted by FRA-Regulated Entities…», «FRA Statistics: …») are
    # found by the site's own search; the latest releases are read too.
    for query in ({"per_page": 8}, {"per_page": 4, "search": "Financing Granted", "orderby": "relevance"},
                  {"per_page": 4, "search": "FRA Statistics", "orderby": "relevance"}):
        for post in _wp_posts(ctx, FRA_POSTS, {"_fields": "id,date,link,title,content", **query}):
            link = post.get("link") or f"{FRA_POSTS}/{post.get('id')}"
            text = claude_cli.page_text(_field(post, "content"))
            if text and link not in links and not ctx.seen(link, sha(text)):
                links.add(link)
                posts.append((link, claude_cli.page_text(_field(post, "title")), text))
    if not posts:
        out.note = "no new releases"
        return out
    result = ctx.extract(_batch(posts), FRA_SCHEMA, FRA_INSTRUCTIONS)
    for item in result["posts"]:
        if not 1 <= item["post"] <= len(posts):
            continue
        link, title, text = posts[item["post"] - 1]
        month = month_period(item["period_end_month"])
        figures = figures_checked(item["figures"], f"{title} {text}")
        for figure in figures if month else []:
            value, unit = (figure["value"] * 1000, "egp_mn") if figure["unit"] == "egp_bn" else (figure["value"], figure["unit"])
            basis = {"month": "in the month", "year_to_date": "in the year to date", "outstanding": "outstanding"}[figure["basis"]]
            out.signals.append(signal(f"fra_{figure['name']}_{figure['basis']}", month, value, unit,
                                      f"FRA: {figure['name'].replace('_', ' ')} {basis} "
                                      f"({'EGP million' if unit == 'egp_mn' else unit})",
                                      "Financial Regulatory Authority", link, figure["quote"][:300]))
        if figures and month:
            out.events.append({"key": f"fra:{month}:{sha(link)[:10]}", "kind": "fra_statistics", "day": ctx.today.isoformat(),
                               "title": title, "url": link, "source": "Financial Regulatory Authority",
                               "summary": None, "figures": figures})
    out.documents.extend((link, sha(text)) for link, _, text in posts)
    return out


OFFER_FIGURES = ["price_per_m2", "unit_price", "down_payment", "interest_rate_pct", "units", "area_m2",
                 "installment_years", "monthly_installment"]
OFFER_SCHEMA = {"type": "object", "required": ["offers"], "additionalProperties": False, "properties": {
    "offers": {"type": "array", "maxItems": 15, "items": {
        "type": "object", "required": ["post", "kind", "city", "use", "figures"], "additionalProperties": False,
        "properties": {
            "post": {"type": "integer"},
            "kind": {"type": "string", "enum": ["land_offer", "housing_offer", "mortgage_terms"]},
            "city": {"type": ["string", "null"], "description": "the city in English, or null"},
            "use": {"type": ["string", "null"], "description": "residential, commercial, mixed, services… or null"},
            "figures": {"type": "array", "maxItems": 10, "items": _figure_items(OFFER_FIGURES)}}}}}}
OFFER_INSTRUCTIONS = """You read posts of Egypt's official real-estate platform, numbered [1], [2]… Only for posts that
announce a concrete government offer — New Urban Communities Authority land for sale or auction, a social or middle-income
housing offering, or the mortgage terms of such an offering — return its kind, city, use and the figures stated outright
(price per m² in EGP, unit price, down payment, interest rate in percent, number of units, area in m², instalment years,
monthly instalment), each with the words that state it. Leave out guides, explainers and marketing articles."""


def platform(ctx: Context) -> Collected:
    out = Collected()
    posts = []
    for post in _wp_posts(ctx, PLATFORM_POSTS, {"per_page": 20, "_fields": "id,date,link,title,content"}):
        title = claude_cli.page_text(_field(post, "title"))
        text = claude_cli.page_text(_field(post, "content"))
        key = post.get("link") or f"{PLATFORM_POSTS}/{post.get('id')}"
        if text and not ctx.seen(key, sha(text)):
            posts.append((key, title, text))
    if not posts:
        out.note = "no new posts"
        return out
    result = ctx.extract(_batch(posts), OFFER_SCHEMA, OFFER_INSTRUCTIONS)
    for offer in result["offers"]:
        if not 1 <= offer["post"] <= len(posts):
            continue
        key, title, text = posts[offer["post"] - 1]
        figures = figures_checked(offer["figures"], f"{title} {text}")
        if not figures:
            continue
        city = (offer["city"] or "").strip()
        place = market.match(city) if city else None
        out.events.append({"key": f"{offer['kind']}:{sha(key)[:16]}", "kind": offer["kind"],
                           "day": ctx.today.isoformat(), "title": title, "url": key,
                           "source": "Egyptian Real Estate Platform",
                           "summary": ", ".join(x for x in (city, offer["use"]) if x) or None,
                           "figures": [{**f, "district": place.key if place else None} for f in figures]})
        for figure in figures:
            if offer["kind"] == "land_offer" and figure["name"] == "price_per_m2" and city:
                out.signals.append(signal(f"nuca_land_ppm:{place.key if place else slug(city)}:{slug(offer['use'] or 'all')}",
                                          ctx.today.strftime("%Y-%m"), figure["value"], "egp_per_m2",
                                          f"NUCA land offer, {city} ({offer['use'] or 'all uses'}), EGP per m²",
                                          "Egyptian Real Estate Platform", key, figure["quote"][:300]))
    out.documents.extend((key, sha(text)) for key, _, text in posts)
    return out


NEWS_UNITS = ["egp", "egp_mn", "egp_bn", "egp_trn", "usd", "usd_mn", "usd_bn", "percent", "count", "egp_per_m2", "m2"]
NEWS_SCHEMA = {"type": "object", "required": ["events"], "additionalProperties": False, "properties": {
    "events": {"type": "array", "maxItems": 20, "items": {
        "type": "object", "required": ["item", "title_en", "summary_en", "topic", "figures"], "additionalProperties": False,
        "properties": {
            "item": {"type": "integer", "description": "the news item's number in the list"},
            "title_en": {"type": "string"}, "summary_en": {"type": "string", "description": "one neutral sentence"},
            "topic": {"type": "string", "enum": ["sales", "prices", "rents", "rates", "policy", "supply", "land",
                                                 "mortgage", "foreign_demand", "costs", "other"]},
            "figures": {"type": "array", "maxItems": 6, "items": _figure_items(
                None, NEWS_UNITS, {"label": {"type": "string", "description": "what the number measures, in English"}})}}}}}}
NEWS_INSTRUCTIONS = """You screen news items about Egypt, numbered [1], [2]… Keep only items that report a fact about
Egypt's property market or what moves it: developers' or market sales, prices, rents, interest or mortgage rates,
housing or land policy and laws, new supply, foreign buyers, building-material costs. For each, give an English title,
one neutral sentence of summary, its topic, and the figures the item itself states (value and unit exactly as written,
what it measures, and the item's words that state it). No opinions, no advice, nothing the item does not say."""


def _rss(ctx: Context, source: str, url: str) -> list[dict]:
    root = ElementTree.fromstring(ctx.get(url).content)
    items = []
    for item in root.iter("item"):
        title, link = (item.findtext("title") or "").strip(), (item.findtext("link") or "").strip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if title and link:
            items.append({"source": source, "title": title, "url": link, "published": published,
                          "text": claude_cli.page_text(item.findtext("description") or "")[:600]})
    return items


def _wp_news(ctx: Context, source: str, url: str) -> list[dict]:
    items = []
    for post in _wp_posts(ctx, url, {"per_page": 20, "_fields": "date_gmt,date,link,title,excerpt"}):
        try:
            published = datetime.fromisoformat(post.get("date_gmt") or post["date"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        items.append({"source": source, "title": claude_cli.page_text(_field(post, "title")), "url": post.get("link"),
                      "published": published, "text": claude_cli.page_text(_field(post, "excerpt"))[:600]})
    return items


def news(ctx: Context) -> Collected:
    out = Collected()
    since = datetime.combine(ctx.today - timedelta(days=NEWS_DAYS), datetime.min.time(), tzinfo=timezone.utc)
    items, failures = [], []
    for reader, feeds in ((_rss, RSS_FEEDS), (_wp_news, WP_NEWS)):
        for source, url in feeds:
            try:
                items += reader(ctx, source, url)
            except (httpx.HTTPError, ElementTree.ParseError, ValueError, Blocked) as exc:
                failures.append(f"{source}: {type(exc).__name__}")
    fresh, seen_urls = [], set()
    for item in sorted(items, key=lambda i: i["published"], reverse=True):
        if item["url"] and item["url"] not in seen_urls and item["published"] >= since \
                and not ctx.seen(item["url"], sha(item["title"])):
            seen_urls.add(item["url"])
            fresh.append(item)
    fresh = fresh[:60]
    out.note = "; ".join(failures)
    if not fresh:
        return out
    listing = "\n\n".join(f"[{n}] {i['source']} | {i['published']:%Y-%m-%d} | {i['title']}\n{i['text']}"
                          for n, i in enumerate(fresh, 1))
    result = ctx.extract(listing, NEWS_SCHEMA, NEWS_INSTRUCTIONS)
    for event in result["events"]:
        if not 1 <= event["item"] <= len(fresh):
            continue
        item = fresh[event["item"] - 1]
        figures = figures_checked(event["figures"], f"{item['title']} {item['text']}")
        out.events.append({"key": f"news:{sha(item['url'])[:16]}", "kind": "news", "day": f"{item['published']:%Y-%m-%d}",
                           "title": item["title"], "url": item["url"], "source": item["source"],
                           "summary": event["summary_en"], "figures": figures, "topic": event["topic"],
                           "title_en": event["title_en"]})
    out.documents.extend((i["url"], sha(i["title"])) for i in fresh)
    return out


COLLECTORS: dict[str, Callable[[Context], Collected]] = {
    "capmas": capmas, "binance": binance, "world_bank": world_bank, "dbnomics": dbnomics, "gold": gold,
    "nuca": nuca, "cbe_bop": cbe_bop, "marsad": marsad, "fra": fra, "platform": platform, "news": news}
READ_BY_CLAUDE = {"gold", "nuca", "cbe_bop", "marsad", "fra", "platform", "news"}


# --- storage --------------------------------------------------------------------------------------

def ensure(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def store(connection: sqlite3.Connection, collected: Collected, today: date) -> tuple[int, int]:
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        for item in collected.signals:
            connection.execute(
                "INSERT INTO market_signals(name,period,value,unit,label,source,source_url,quote,day,fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name,period) DO UPDATE SET value=excluded.value, "
                "unit=excluded.unit, label=excluded.label, source_url=excluded.source_url, quote=excluded.quote, "
                "day=excluded.day, fetched_at=excluded.fetched_at",
                (item["name"], item["period"], item["value"], item["unit"], item["label"], item["source"],
                 item["source_url"], item["quote"], today.isoformat(), now))
        for event in collected.events:
            extra = {k: event[k] for k in ("topic", "title_en") if k in event}
            figures = json.dumps({"figures": event["figures"], **extra}, ensure_ascii=False)
            connection.execute(
                "INSERT INTO market_events(key,kind,day,title,url,source,summary,figures,fetched_at) VALUES "
                "(?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET title=excluded.title, url=excluded.url, "
                "summary=excluded.summary, figures=excluded.figures, day=excluded.day",
                (event["key"], event["kind"], event["day"], event["title"], event["url"], event["source"],
                 event["summary"], figures, now))
        connection.executemany("INSERT INTO signal_documents(url,sha256,fetched_at) VALUES (?,?,?) "
                               "ON CONFLICT(url) DO UPDATE SET sha256=excluded.sha256, fetched_at=excluded.fetched_at",
                               [(url, digest, now) for url, digest in collected.documents])
    return len(collected.signals), len(collected.events)


def run(connection: sqlite3.Connection, *, only: set[str] | None = None, client: httpx.Client | None = None,
        extract: Callable[[str, dict, str], dict] | None = None, today: date | None = None) -> list[dict]:
    """Read every source (or `only` these); returns one outcome per source."""
    ensure(connection)
    today = today or datetime.now(timezone.utc).date()
    own = client is None
    client = client or httpx.Client(timeout=40, follow_redirects=True,
                                    headers={"User-Agent": USER_AGENT, "Accept-Language": "en,ar"})
    ctx = Context(client, connection, extract or claude_cli.extract, today)
    claude_down = None
    outcomes = []
    try:
        for name, collect in COLLECTORS.items():
            if only and name not in only:
                continue
            if name in READ_BY_CLAUDE and claude_down:
                outcomes.append({"source": name, "status": "skipped", "reason": claude_down})
                continue
            try:
                collected = collect(ctx)
                signals_count, events_count = store(connection, collected, today)
                outcomes.append({"source": name, "status": "ok", "signals": signals_count, "events": events_count,
                                 **({"note": collected.note} if collected.note else {})})
            except claude_cli.ClaudeUnavailable as exc:
                claude_down = str(exc)
                outcomes.append({"source": name, "status": "skipped", "reason": claude_down})
            except Blocked as exc:
                outcomes.append({"source": name, "status": "blocked", "reason": str(exc)})
            except Exception as exc:  # one source never stops the others
                outcomes.append({"source": name, "status": "failed", "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
    finally:
        if own:
            client.close()
    return outcomes


def published(connection: sqlite3.Connection, today: date | None = None) -> dict:
    """The latest value of every signal and the recent events, for the website and the article agent."""
    empty = {"latest": {}, "events": [], "calendar": []}
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='market_signals'").fetchone():
        return empty
    today = today or datetime.now(timezone.utc).date()
    latest = {}
    for name, period, value, unit, label, source, url in connection.execute(
            "SELECT name, period, value, unit, label, source, source_url FROM market_signals s "
            "WHERE period=(SELECT max(period) FROM market_signals WHERE name=s.name) ORDER BY name"):
        latest[name] = {"period": period, "value": value, "unit": unit, "label": label, "source": source, "url": url}
    since = (today - timedelta(days=EVENT_DAYS)).isoformat()
    events, calendar = [], []
    for key, kind, day, title, url, source, summary, figures in connection.execute(
            "SELECT key, kind, day, title, url, source, summary, figures FROM market_events WHERE day>=? "
            "ORDER BY day DESC, key", (since,)):
        detail = json.loads(figures or "{}")
        entry = {"key": key, "kind": kind, "day": day, "title": title, "url": url, "source": source, "summary": summary,
                 "figures": detail.get("figures") or [], **{k: detail[k] for k in ("topic", "title_en") if k in detail}}
        if kind == "capmas_release":
            if day >= today.isoformat():
                calendar.append({k: entry[k] for k in ("day", "title", "source")})
        elif len(events) < 40:
            events.append(entry)
    return {"latest": latest, "events": events, "calendar": sorted(calendar, key=lambda c: c["day"])[:10]}

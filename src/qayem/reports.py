"""Listed developers' published results: new report PDFs, downloaded and read for their key figures.

The investor-relations pages below publish earnings releases and presentations as plain links, so
they are read like any other public page (robots.txt respected, one request every few seconds, a
block stops the run). Sites that block automated access (Emaar Misr answers 403) are not read: Qayem
never gets past protection (docs/STRATEGY.md 5.1). Each new PDF's text is sent to the configured GLM
model through Pi for a handful of figures; a figure is kept as "checked" only when its number appears
in the PDF's own text, otherwise it waits for review. Quarterly reports trigger articles (8.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .config import USER_AGENT


@dataclass(frozen=True)
class Source:
    developer: str  # the website's developer key
    name: str
    page: str
    pattern: str  # which linked PDFs are results (not governance reports or forms)


SOURCES = (
    Source("sodic", "SODIC", "https://www.sodic.com/investor-relations", r"earning|result|presentation"),
    Source("madinetmasr", "Madinet Masr", "https://ir.madinetmasr.com/", r"-ER|ERP|earning|result|presentation"),
    Source("palmhills", "Palm Hills Developments", "https://ir.palmhillsdevelopments.com/", r"presentation|result|earning"),
    Source("talaatmoustafa", "Talaat Moustafa Group", "https://talaatmoustafa.com/investor-relations/",
           r"result|earning|presentation|financial"),
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS developer_reports (
  url TEXT PRIMARY KEY, developer TEXT NOT NULL, title TEXT NOT NULL, fetched_at TEXT NOT NULL, sha256 TEXT,
  pages INTEGER, period TEXT, figures TEXT, status TEXT NOT NULL, error TEXT
);
"""
EXTRACTION = {
    "type": "object", "required": ["period", "figures"], "additionalProperties": False,
    "properties": {
        "period": {"type": ["string", "null"], "description": "Reporting period, e.g. 'Q3 2026', '9M 2026', 'H1 2026'"},
        "figures": {"type": "array", "maxItems": 12, "items": {
            "type": "object", "required": ["name", "value", "unit", "quote"], "additionalProperties": False,
            "properties": {"name": {"type": "string", "enum": [
                "contracted_sales", "net_sales", "units_sold", "units_delivered", "revenue", "net_profit",
                "average_price_per_m2", "cash_collections", "land_bank_m2"]},
                "value": {"type": "number"}, "unit": {"type": "string", "enum": ["egp", "egp_bn", "egp_mn", "units", "m2", "egp_per_m2"]},
                "quote": {"type": "string", "description": "the exact words of the report that state the figure"}}}}}}
INSTRUCTIONS = """You read an Egyptian listed real-estate developer's earnings release or investor presentation.
Return the reporting period and only the figures the text states outright (contracted sales, net sales, units sold or
delivered, revenue, net profit, average price per m², cash collections, land bank). Copy the number exactly as written,
with its unit, and quote the words that state it. Never estimate or compute. If a figure is not stated, leave it out."""
MAX_BYTES = 40_000_000


def ensure(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def allowed(client: httpx.Client, url: str, cache: dict) -> bool:
    parts = urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    if root not in cache:
        parser = RobotFileParser()
        try:
            response = client.get(root + "/robots.txt")
            parser.parse(response.text.splitlines() if response.status_code == 200 else [])
        except httpx.HTTPError:
            parser.parse([])
        cache[root] = parser
    return cache[root].can_fetch(USER_AGENT, url)


def links(html: str, base: str, pattern: str) -> list[tuple[str, str]]:
    found = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>', html, flags=re.S | re.I):
        url = urljoin(base, href.strip())
        title = " ".join(re.sub(r"<[^>]+>", " ", label).split()) or Path(urlsplit(url).path).name
        if re.search(pattern, url + " " + title, re.I) and not re.search(r"dummy|governance|حوكمة", url + title, re.I):
            found.append((url, title[:200]))
    return list(dict.fromkeys(found))


def pdf_text(data: bytes, pages: int = 12) -> tuple[str, int]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:pages])
    return text, len(reader.pages)


def checked(figure: dict, text: str) -> bool:
    """The figure's number is written in the report itself (as 12.3, 12,300 or 12300)."""
    value = figure["value"]
    plain = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    candidates = {f"{value:g}", f"{value:,.0f}".replace(",", ""), f"{value:.1f}", f"{value:.2f}"}
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", plain) for c in candidates)


def run(connection: sqlite3.Connection, folder: Path, *, extract=None, limit: int = 6, min_interval: float = 4.0) -> list[dict]:
    """Download and read up to `limit` new reports. `extract(text) -> dict` defaults to Pi/GLM."""
    ensure(connection)
    if extract is None:
        from .ai import run_pi
        instructions = folder / "instructions.md"
        folder.mkdir(parents=True, exist_ok=True)
        instructions.write_text(INSTRUCTIONS, encoding="utf-8")
        extract = lambda text: run_pi(text[:60_000], EXTRACTION, instructions)  # noqa: E731
    known = {row[0] for row in connection.execute("SELECT url FROM developer_reports")}
    robots: dict = {}
    out = []
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for source in SOURCES:
            try:
                if not allowed(client, source.page, robots):
                    out.append({"developer": source.developer, "status": "skipped", "error": "robots.txt"})
                    continue
                page = client.get(source.page)
                if page.status_code in (403, 429):
                    out.append({"developer": source.developer, "status": "blocked"})
                    continue
                page.raise_for_status()
            except httpx.HTTPError as exc:
                out.append({"developer": source.developer, "status": "failed", "error": type(exc).__name__})
                continue
            time.sleep(min_interval)
            for url, title in links(page.text, source.page, source.pattern):
                if url in known or len(out) >= limit or not allowed(client, url, robots):
                    continue
                record = {"url": url, "developer": source.developer, "title": title,
                          "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "failed"}
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    if len(response.content) > MAX_BYTES:
                        raise ValueError("report too large")
                    text, pages = pdf_text(response.content)
                    record.update(sha256=hashlib.sha256(response.content).hexdigest(), pages=pages)
                    target = folder / source.developer / Path(urlsplit(url).path).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(response.content)
                    result = extract(text) if text.strip() else {"period": None, "figures": []}
                    figures = [{**f, "checked": checked(f, text)} for f in result.get("figures", [])]
                    record.update(period=result.get("period"), figures=json.dumps(figures, ensure_ascii=False),
                                  status="checked" if figures and all(f["checked"] for f in figures)
                                  else "needs_review" if figures else "no_figures")
                except Exception as exc:  # one bad report never stops the others
                    record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                connection.execute(
                    "INSERT OR REPLACE INTO developer_reports(url,developer,title,fetched_at,sha256,pages,period,figures,"
                    "status,error) VALUES (:url,:developer,:title,:fetched_at,:sha256,:pages,:period,:figures,:status,:error)",
                    {"sha256": None, "pages": None, "period": None, "figures": None, "error": None, **record})
                connection.commit()
                out.append({k: record.get(k) for k in ("developer", "title", "period", "status", "error")})
                time.sleep(min_interval)
    return out


def published(connection: sqlite3.Connection) -> list[dict]:
    """Checked reports, newest first, for the website and the article agent."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='developer_reports'").fetchone():
        return []
    rows = connection.execute("SELECT developer, title, url, period, figures, fetched_at FROM developer_reports "
                              "WHERE status='checked' ORDER BY fetched_at DESC LIMIT 40").fetchall()
    return [{"developer": d, "title": t, "url": u, "period": p, "figures": json.loads(f or "[]"), "fetched_at": a}
            for d, t, u, p, f, a in rows]

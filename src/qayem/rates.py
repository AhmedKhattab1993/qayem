"""The Central Bank of Egypt's published figures: exchange rates, policy rates and inflation.

Read from cbe.org.eg's public pages (robots.txt allows them) once a night. Exchange rates turn the
guide's prices into USD, SAR and AED for buyers abroad (docs/STRATEGY.md, 6); policy-rate and
inflation changes trigger articles (8.1).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import re

import httpx

from .config import USER_AGENT

FX_URL = "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates"
KEY_URL = "https://www.cbe.org.eg/en"
CURRENCIES = {"US Dollar": "usd", "Euro": "eur", "Pound Sterling": "gbp", "Saudi Riyal": "sar",
              "UAE Dirham": "aed", "Kuwaiti Dinar": "kwd", "Qatari Riyal": "qar"}
KEY_FIGURES = {"Overnight Deposit Rate": "overnight_deposit", "Overnight Lending Rate": "overnight_lending",
               "MAIN OPERATION": "main_operation", "HEADLINE INFLATION RATE": "headline_inflation",
               "CORE INFLATION RATE": "core_inflation"}
NUMBER = r"(-?\d+(?:\.\d+)?)"


def text_of(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&amp;", "&").split())


def parse_fx(html: str) -> tuple[str | None, dict[str, float]]:
    """EGP per unit of each currency: the midpoint of the CBE's buy and sell rates."""
    text = text_of(html)
    day = None
    if found := re.search(r"Rates for Date:\s*(\d{2})/(\d{2})/(\d{4})", text):
        day = f"{found.group(3)}-{found.group(2)}-{found.group(1)}"
    rates = {}
    for label, key in CURRENCIES.items():
        if found := re.search(rf"{re.escape(label)}\s+{NUMBER}\s+{NUMBER}", text):
            buy, sell = float(found.group(1)), float(found.group(2))
            if 0 < buy <= sell < 10_000:
                rates[key] = round((buy + sell) / 2, 4)
    return day, rates


def parse_key_figures(html: str) -> dict[str, float]:
    """Policy rates and inflation (percent) from the CBE home page's key statistics."""
    text = text_of(html)
    figures = {}
    for label, key in KEY_FIGURES.items():
        if found := re.search(rf"{re.escape(label)}\s+{NUMBER}%", text, flags=re.I):
            value = float(found.group(1))
            if -50 < value < 100:
                figures[key] = value
    return figures


def fetch(client: httpx.Client | None = None) -> dict:
    """Today's figures. Raises when the exchange rates cannot be read: a rate is never guessed."""
    own = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                                    follow_redirects=True)
    try:
        fx = client.get(FX_URL)
        fx.raise_for_status()
        day, rates = parse_fx(fx.text)
        key = client.get(KEY_URL)
        figures = parse_key_figures(key.text) if key.status_code == 200 else {}
    finally:
        if own:
            client.close()
    if "usd" not in rates:
        raise RuntimeError("The CBE exchange-rate page did not list the US dollar rate")
    return {"day": day or date.today().isoformat(), "fx": rates, "key": figures, "source": "Central Bank of Egypt",
            "source_url": FX_URL, "fetched_at": datetime.now(timezone.utc).isoformat()}

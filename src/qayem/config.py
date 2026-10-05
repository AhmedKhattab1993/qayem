"""Shared configuration: HTTP identity, politeness defaults, database location."""

import os
from pathlib import Path

# Full Chrome UA — several sources (Aqarmap's CloudFront WAF, GPM) behave
# differently for bare clients; tier-1 sites all pass with this.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en",
}

# Politeness: minimum seconds between requests to the same host, plus random
# jitter. Semsar/GPM are old servers; Aqarmap sits behind a touchy WAF.
DEFAULT_MIN_INTERVAL = 2.0
DEFAULT_JITTER = 1.0
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 4  # transport errors and 5xx, with exponential backoff

DEFAULT_DB_PATH = "qayem.db"

# Sources the website, the fair-value model, the nightly crawl and enrichment use. AqarExit is
# the only complete record of the secondary market; other sources' rows stay in the database
# but are not shown, fitted, crawled or enriched.
DEFAULT_SOURCES = ("aqarexit",)


def active_sources() -> frozenset[str] | None:
    """Sources in use: QAYEM_SOURCES=aqarexit,nawy overrides the default; QAYEM_SOURCES=all means every source (None)."""
    value = os.environ.get("QAYEM_SOURCES", "").strip().casefold()
    if value == "all":
        return None
    names = [name.strip() for name in value.split(",") if name.strip()] if value else DEFAULT_SOURCES
    return frozenset(names)


# Price benchmarks: crawled nightly and read by the website only to compare resale against the
# developers' current prices — never shown as listings, fitted or enriched. Nawy's developer-sale
# units carry each developer's current price and payment plan per unit.
DEFAULT_BENCHMARK_SOURCES = ("nawy_primary",)


def benchmark_sources() -> frozenset[str]:
    """QAYEM_BENCHMARK_SOURCES=nawy_primary overrides the default; QAYEM_BENCHMARK_SOURCES=none turns them off."""
    value = os.environ.get("QAYEM_BENCHMARK_SOURCES", "").strip().casefold()
    if value == "none":
        return frozenset()
    names = [name.strip() for name in value.split(",") if name.strip()] if value else DEFAULT_BENCHMARK_SOURCES
    return frozenset(names)


def crawled_sources() -> frozenset[str] | None:
    """Sources in use plus the benchmarks (None: every source)."""
    sources = active_sources()
    return None if sources is None else sources | benchmark_sources()


def db_path() -> Path:
    """Database location, overridable via QAYEM_DB env var."""
    return Path(os.environ.get("QAYEM_DB", DEFAULT_DB_PATH))

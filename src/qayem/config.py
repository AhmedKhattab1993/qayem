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


def db_path() -> Path:
    """Database location, overridable via QAYEM_DB env var."""
    return Path(os.environ.get("QAYEM_DB", DEFAULT_DB_PATH))

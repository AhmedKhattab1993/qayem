"""Polite shared HTTP fetcher: per-host rate limiting, retries, block detection.

Every source goes through this so request pacing, browser-like headers, and
WAF handling stay consistent. A 403/429 (bot block) aborts immediately —
retrying against a WAF only escalates it.
"""

from __future__ import annotations

import random
import time

import httpx

from .config import (
    DEFAULT_HEADERS,
    DEFAULT_JITTER,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
)


class FetchError(Exception):
    """A page could not be fetched."""

    def __init__(self, url: str, message: str):
        self.url = url
        super().__init__(f"{message} ({url})")


class BlockedError(FetchError):
    """The WAF blocked us (403/429). Never retried; the run must stop."""

    def __init__(self, url: str, status: int):
        self.status = status
        super().__init__(url, f"blocked by WAF, HTTP {status}")


class HTTPStatusError(FetchError):
    def __init__(self, url: str, status: int):
        self.status = status
        super().__init__(url, f"HTTP {status}")


# Response bodies that mean a bot challenge even behind a 200/503.
_CHALLENGE_MARKERS = (
    "just a moment",
    "attention required",
    "التحقق الأمني",
    "cf-chl",
    "challenge-platform",
)


def backoff(attempt: int) -> float:
    """Seconds to wait before retry `attempt + 1`: 3, 9, 27, 60, 60… — rides out
    minute-long outages without hammering a struggling server."""
    return min(60.0, 3.0 * 3 ** attempt)


class Fetcher:
    def __init__(
        self,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        jitter: float = DEFAULT_JITTER,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        headers: dict[str, str] | None = None,
    ):
        self.min_interval = min_interval
        self.jitter = jitter
        self.retries = retries
        self.requests_made = 0
        self._last_hit: dict[str, float] = {}
        self._client = httpx.Client(
            headers={**DEFAULT_HEADERS, **(headers or {})},
            timeout=timeout,
            follow_redirects=True,
        )

    def _wait_slot(self, url: str) -> None:
        host = httpx.URL(url).host
        now = time.monotonic()
        elapsed = now - self._last_hit.get(host, 0.0)
        wait = self.min_interval + random.uniform(0, self.jitter) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        """GET a page, rate-limited per host. Returns the response for 2xx.
        Raises BlockedError for 403/429, HTTPStatusError for other non-2xx
        after retries, FetchError for transport failures."""
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait_slot(url)
            self.requests_made += 1
            try:
                resp = self._client.get(url)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(backoff(attempt))
                    continue
                raise FetchError(url, f"transport error: {exc}") from exc

            if 200 <= resp.status_code < 300:
                self._check_challenge(url, resp)
                return resp
            if resp.status_code in (403, 429):
                raise BlockedError(url, resp.status_code)
            if resp.status_code >= 500:
                last_exc = HTTPStatusError(url, resp.status_code)
                if attempt < self.retries:
                    time.sleep(backoff(attempt))
                    continue
                raise last_exc
            raise HTTPStatusError(url, resp.status_code)
        raise last_exc or FetchError(url, "unreachable")  # pragma: no cover

    @staticmethod
    def _check_challenge(url: str, resp: httpx.Response) -> None:
        head = resp.text[:4000].lower()
        for marker in _CHALLENGE_MARKERS:
            if marker in head:
                raise BlockedError(url, resp.status_code)

    def get_text(self, url: str, encoding: str | None = None) -> str:
        """GET and decode. `encoding` forces a codec (e.g. Semsar's
        windows-1256) instead of trusting the server's header."""
        resp = self.get(url)
        if encoding:
            return resp.content.decode(encoding, errors="replace")
        return resp.text

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

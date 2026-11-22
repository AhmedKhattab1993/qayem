"""Scheduled crawling: the production crawl plan and source health.

`qayem crawl` runs every scope in PLAN with a per-scope time budget, so one slow
or blocked source can never stall the others. `qayem health` judges each source
from its run history: a source is healthy only if it produced listings recently
and its latest yield has not collapsed against its own recent runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import crawled_sources
from .models import ParseRun


@dataclass(frozen=True)
class Scope:
    source: str
    params: dict
    budget_minutes: int
    min_interval: float | None = None  # seconds between requests; None → the global default
    every_days: int = 1  # a market source is refreshed every other night, so a night's crawl stays in budget
    offset: int = 0  # which night of the cycle (day number modulo every_days)

    def due(self, day: date) -> bool:
        return day.toordinal() % self.every_days == self.offset

    @property
    def label(self) -> str:
        details = " ".join(f"{k}={v}" for k, v in sorted(self.params.items()))
        return f"{self.source} {details}".strip()


OPENSOOQ_CITIES = ("cairo", "giza", "alexandria")
OPENSOOQ_CATEGORIES = ("apartments", "villas", "buildings", "townhouses", "farms-chalets")

# Complete scopes wherever the source allows it: only a scope that reaches its natural
# end may mark unseen listings as removed, which is what lifecycle analytics need.
PLAN: tuple[Scope, ...] = (
    Scope("nawy", {}, 100, min_interval=3.0),
    Scope("nawy_primary", {}, 110, min_interval=3.0),
    # sitemap-driven and incremental: only new or changed unit pages are fetched
    Scope("aqarexit", {}, 120),
    Scope("gpm", {"max_details": 5000}, 60),
    # Market sources (price-guide aggregates only) alternate nights: Aqarmap one night, OpenSooq and
    # Semsar the next. Each listing is still re-observed well inside the 14-day confirmation window.
    *(Scope("aqarmap", {"city": city}, 30, every_days=2, offset=0) for city in ("cairo", "giza", "alexandria")),
    *(Scope("opensooq", {"city": city, "category": category}, 8, every_days=2, offset=1)
      for city in OPENSOOQ_CITIES for category in ("apartments", "villas")),
    *(Scope("semsar", {"category": category}, 25, every_days=2, offset=1) for category in ("apartments", "villas")),
    # ~24k sitemap URLs need one detail fetch each; the newest slice is refreshed nightly.
    Scope("coldwellbanker", {"max_details": 400}, 40),
)

def active_plan(day: date | None = None) -> tuple[Scope, ...]:
    """The scopes of the sources in use, the price benchmarks and the market sources. With `day`,
    only the scopes due that night."""
    sources = crawled_sources()
    return tuple(scope for scope in PLAN if (sources is None or scope.source in sources)
                 and (day is None or scope.due(day)))


def stale_after(source: str) -> timedelta:
    """A source crawled every other night is stale only after it missed its night."""
    every = max((scope.every_days for scope in PLAN if scope.source == source), default=1)
    return STALE_AFTER + timedelta(days=every - 1)


STALE_AFTER = timedelta(hours=36)
ABANDONED_AFTER = timedelta(hours=6)
DROP_RATIO = 0.5  # latest yield below half of the recent median → likely a parser or access break
# A price benchmark may be published from its last good crawl for this long (the site shows its date);
# listing sources are published only while healthy, so stale listings never look current.
BENCHMARK_MAX_AGE = timedelta(days=7)


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def close_abandoned_runs(session: Session, now: datetime) -> int:
    """Runs left 'running' by a killed or suspended process are marked failed."""
    runs = session.execute(select(ParseRun).where(ParseRun.status == "running")).scalars().all()
    closed = 0
    for run in runs:
        if utc(run.started_at) and now - utc(run.started_at) > ABANDONED_AFTER:
            run.status = "failed"
            run.finished_at = now
            run.errors = (run.errors or []) + ["abandoned: the process ended before the run finished"]
            closed += 1
    return closed


@dataclass
class SourceHealth:
    source: str
    state: str  # ok | running | stale | failing | dropped | never
    last_run: datetime | None
    last_status: str | None
    last_success: datetime | None
    last_seen: int
    typical_seen: float | None
    detail: str

    def as_dict(self) -> dict:
        return {"source": self.source, "state": self.state, "detail": self.detail,
                "last_run": self.last_run.isoformat() if self.last_run else None,
                "last_status": self.last_status,
                "last_success": self.last_success.isoformat() if self.last_success else None,
                "last_seen": self.last_seen, "typical_seen": self.typical_seen}


def _key(run: ParseRun) -> str:
    params = {k: v for k, v in (run.params or {}).items() if k not in ("max_pages", "max_details", "details")}
    return f"{run.source}:{sorted(params.items())}"


def source_health(session: Session, now: datetime, sources: list[str] | None = None) -> list[SourceHealth]:
    names = sources or sorted({scope.source for scope in active_plan()})
    report = []
    for name in names:
        runs = session.execute(
            select(ParseRun).where(ParseRun.source == name).order_by(ParseRun.started_at.desc()).limit(60)
        ).scalars().all()
        if not runs:
            report.append(SourceHealth(name, "never", None, None, None, 0, None, "no run recorded"))
            continue
        last = runs[0]
        successes = [r for r in runs if r.status in ("completed", "partial") and (r.seen or 0) > 0]
        last_success = utc(successes[0].finished_at or successes[0].started_at) if successes else None
        # compare the latest scope's yield with its own previous runs (same scope parameters)
        same_scope = [r for r in successes if _key(r) == _key(successes[0])] if successes else []
        typical = median(r.seen for r in same_scope[1:6]) if len(same_scope) > 1 else None
        latest_seen = successes[0].seen if successes else 0
        recent = [r for r in runs if r.status != "running"][:2]
        if last.status == "running" and utc(last.started_at) and now - utc(last.started_at) <= ABANDONED_AFTER:
            state, detail = "running", f"run in progress since {utc(last.started_at):%H:%M} UTC"
        elif not successes:
            state, detail = "failing", "no run has produced listings"
        elif len(recent) == 2 and all(r.status == "failed" for r in recent):
            state, detail = "failing", f"last two runs failed: {(recent[0].errors or ['unknown'])[0]}"
        elif now - last_success > stale_after(name):
            state, detail = "stale", f"last listings {int((now - last_success).total_seconds() // 3600)} h ago"
        elif typical and latest_seen < DROP_RATIO * typical:
            state, detail = "dropped", f"latest run saw {latest_seen} listings, typically {typical:.0f}"
        else:
            state, detail = "ok", f"{latest_seen} listings in the latest run"
        report.append(SourceHealth(name, state, utc(last.started_at), last.status, last_success,
                                   latest_seen, typical, detail))
    return report


def publishable(report: list[SourceHealth], now: datetime, benchmarks: frozenset[str] = frozenset()) -> list[str]:
    """Sources fit to publish: healthy (ok or running) ones, and benchmarks whose last listings are under a week old.

    One blocked or failing source is then left out of the catalogue instead of holding back every other source.
    """
    keep = []
    for item in report:
        if item.state in ("ok", "running"):
            keep.append(item.source)
        elif item.source in benchmarks and item.last_success and now - item.last_success <= BENCHMARK_MAX_AGE:
            keep.append(item.source)
    return keep

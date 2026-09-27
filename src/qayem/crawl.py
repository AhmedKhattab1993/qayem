"""Scheduled crawling: the production crawl plan and source health.

`qayem crawl` runs every scope in PLAN with a per-scope time budget, so one slow
or blocked source can never stall the others. `qayem health` judges each source
from its run history: a source is healthy only if it produced listings recently
and its latest yield has not collapsed against its own recent runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ParseRun


@dataclass(frozen=True)
class Scope:
    source: str
    params: dict
    budget_minutes: int
    min_interval: float | None = None  # seconds between requests; None → the global default

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
    *(Scope("opensooq", {"city": city, "category": category}, 15)
      for city in OPENSOOQ_CITIES for category in OPENSOOQ_CATEGORIES),
    *(Scope("aqarmap", {"city": city}, 45) for city in ("cairo", "giza", "alexandria")),
    *(Scope("semsar", {"category": category}, 60) for category in ("apartments", "villas", "chalets")),
    # ~24k sitemap URLs need one detail fetch each; the newest slice is refreshed nightly.
    Scope("coldwellbanker", {"max_details": 400}, 40),
)

STALE_AFTER = timedelta(hours=36)
ABANDONED_AFTER = timedelta(hours=6)
DROP_RATIO = 0.5  # latest yield below half of the recent median → likely a parser or access break


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
    names = sources or sorted({scope.source for scope in PLAN})
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
        elif now - last_success > STALE_AFTER:
            state, detail = "stale", f"last listings {int((now - last_success).total_seconds() // 3600)} h ago"
        elif typical and latest_seen < DROP_RATIO * typical:
            state, detail = "dropped", f"latest run saw {latest_seen} listings, typically {typical:.0f}"
        else:
            state, detail = "ok", f"{latest_seen} listings in the latest run"
        report.append(SourceHealth(name, state, utc(last.started_at), last.status, last_success,
                                   latest_seen, typical, detail))
    return report

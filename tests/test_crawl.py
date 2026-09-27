"""Scheduled crawl: time budgets, crash safety, abandoned runs, source health."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from qayem import cli
from qayem.crawl import PLAN, close_abandoned_runs, source_health
from qayem.db import init_db
from qayem.models import ParseRun, Property
from qayem.sources import SOURCE_REGISTRY
from qayem.sources.base import BaseSource, NormalizedListing

NOW = datetime(2026, 9, 26, 3, 0, tzinfo=timezone.utc)


@pytest.fixture()
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'crawl.db'}")
    init_db(engine)
    return engine


def make_source(listings: int, error: Exception | None = None, clock: list | None = None):
    class Fake(BaseSource):
        name = "fake"

        def fetch(self):
            for index in range(listings):
                yield NormalizedListing(source_listing_id=str(index), scope_key="all", price=1e6, area_m2=100)
                if clock is not None:
                    clock[0] += 3600  # each listing takes an hour of wall time
            if error:
                raise error
            self.complete = True
            self.scopes_completed.add("all")

    return Fake


def run(engine, monkeypatch, source, budget=None):
    monkeypatch.setitem(SOURCE_REGISTRY, "fake", source)
    return cli._run_source(engine, "fake", {}, dry_run=False, min_interval=0, budget_minutes=budget)


def test_plan_covers_every_registered_source():
    assert {scope.source for scope in PLAN} == set(SOURCE_REGISTRY)
    assert all(scope.budget_minutes > 0 for scope in PLAN)


def test_complete_run_marks_removals_and_budget_stops_early(engine, monkeypatch):
    assert run(engine, monkeypatch, make_source(3)) == "completed"
    clock = [0.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])
    assert run(engine, monkeypatch, make_source(3, clock=clock), budget=30) == "partial"
    with Session(engine) as session:
        last = session.execute(select(ParseRun).order_by(ParseRun.id.desc())).scalars().first()
        assert last.seen == 2 and "time budget" in last.errors[0]
        # a budget-stopped run never marks the unseen listings as removed
        assert session.query(Property).filter_by(status="removed").count() == 0


def test_a_crashing_source_is_recorded_as_failed(engine, monkeypatch):
    assert run(engine, monkeypatch, make_source(2, RuntimeError("markup changed"))) == "failed"
    with Session(engine) as session:
        last = session.execute(select(ParseRun)).scalars().one()
        assert last.status == "failed" and "markup changed" in last.errors[0]


def test_abandoned_runs_are_closed(engine):
    with Session(engine) as session:
        session.add(ParseRun(source="nawy", status="running", started_at=NOW - timedelta(hours=9)))
        session.add(ParseRun(source="gpm", status="running", started_at=NOW - timedelta(minutes=20)))
        session.commit()
        assert close_abandoned_runs(session, NOW) == 1
        statuses = {run.source: run.status for run in session.query(ParseRun)}
        assert statuses == {"nawy": "failed", "gpm": "running"}


def test_health_states(engine):
    def add(session, source, status, hours_ago, seen, params=None):
        started = NOW - timedelta(hours=hours_ago)
        session.add(ParseRun(source=source, status=status, started_at=started, finished_at=started,
                             seen=seen, params=params or {}, errors=None if status != "failed" else ["HTTP 403"]))

    with Session(engine) as session:
        for hours in (72, 48, 24):
            add(session, "nawy", "completed", hours, 12_000)
        add(session, "nawy", "completed", 2, 12_500)
        for hours in (72, 48):
            add(session, "aqarmap", "completed", hours, 1_300)
        add(session, "aqarmap", "partial", 1, 200)                 # yield collapsed
        add(session, "semsar", "completed", 80, 600)               # stale
        add(session, "gpm", "completed", 30, 400)
        add(session, "gpm", "failed", 20, 0)
        add(session, "gpm", "failed", 1, 0)                        # failing twice in a row
        add(session, "opensooq", "failed", 30, 0)
        add(session, "opensooq", "running", 1, 0)                  # a run in progress is not a failure
        session.commit()
        states = {h.source: h.state for h in source_health(
            session, NOW, ["nawy", "aqarmap", "semsar", "gpm", "aqarexit", "opensooq"])}
    assert states == {"nawy": "ok", "aqarmap": "dropped", "semsar": "stale", "gpm": "failing", "aqarexit": "never",
                      "opensooq": "running"}


def test_confirmed_presence_protects_listings_from_removal(engine, monkeypatch):
    assert run(engine, monkeypatch, make_source(3)) == "completed"  # listings 0, 1, 2

    class Incremental(BaseSource):
        name = "fake"
        wants_known = True

        def fetch(self):
            assert set(self.param("known")) == {"0", "1", "2"}
            self.present_ids = {"0", "1"}  # 2 has left the inventory
            self.complete = True
            self.scopes_completed.add("all")
            yield NormalizedListing(source_listing_id="0", scope_key="all", price=2e6, area_m2=100)

    assert run(engine, monkeypatch, Incremental) == "completed"
    with Session(engine) as session:
        status = {p.source_listing_id: p.status for p in session.query(Property)}
    assert status == {"0": "active", "1": "active", "2": "removed"}


def test_a_source_cannot_run_twice_at_once(engine, monkeypatch, tmp_path):
    monkeypatch.setenv("QAYEM_DB", str(tmp_path / "crawl.db"))
    held = cli.source_lock("fake")
    try:
        assert run(engine, monkeypatch, make_source(1)) == "skipped"
    finally:
        held.close()
    assert run(engine, monkeypatch, make_source(1)) == "completed"


def test_repeating_pages_are_reported_and_never_remove(engine, monkeypatch):
    class Repeating(BaseSource):
        name = "fake"

        def fetch(self):
            for _ in range(50):  # the same 5 listings, page after page
                for index in range(5):
                    yield NormalizedListing(source_listing_id=str(index), scope_key="all", price=1e6, area_m2=100)
            self.complete = True
            self.scopes_completed.add("all")

    assert run(engine, monkeypatch, make_source(10)) == "completed"  # listings 0-9
    assert run(engine, monkeypatch, Repeating) == "partial"
    with Session(engine) as session:
        assert session.query(Property).filter_by(status="removed").count() == 0  # 5-9 unseen, not removed
        run_row = session.execute(select(ParseRun).order_by(ParseRun.id.desc())).scalars().first()
        assert "paging repeats" in run_row.errors[0]

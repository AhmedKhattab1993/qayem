"""Cloud API parity, data privacy, and interrupted publication using disposable databases."""
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from qayem.cloud_export import export_sql, retention_sql
from qayem.cloud_web import create_cloud_app
from qayem.web import create_app
from test_web import database  # the same deliberately mixed, private-data-containing fixture

SCHEMA = Path(__file__).resolve().parents[1] / "cloudflare" / "schema.sql"


class SQLite:
    def __init__(self, path):
        self.path = path

    async def all(self, sql, params=()):
        assert len(params) <= 100  # D1's binding budget, including long multi-term searches
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, params)]


@pytest.fixture()
def clients(database, tmp_path):
    export = tmp_path / "export.sql"
    export_sql(database, export, version="first")
    published = tmp_path / "public.db"
    with sqlite3.connect(published) as db:
        db.executescript(SCHEMA.read_text())
        db.executescript(export.read_text())
    with TestClient(create_app(database, tmp_path / "no-assets", sources=None)) as local:
        with TestClient(create_cloud_app(SQLite(published))) as cloud:
            yield local, cloud, published, export


@pytest.mark.parametrize("path", [
    "/api/health", "/api/overview", "/api/catalog", "/api/units",
    *[f"/api/units?sort={sort}&page_size=3&page=2" for sort in
      ("opportunity", "launch_gap", "peer_gap", "price_asc", "price_desc", "area_desc", "cash_ppm_asc")],
    "/api/units?resale=all", "/api/units?launch=true", "/api/units?terms=plan",
    "/api/units?q=Garden", "/api/units?q=القاهرة%20الجديدة", "/api/units?q=%25",
    "/api/units?district=New%20Cairo&compound=garden", "/api/units?developer=Nile",
    "/api/units?source=nawy&property_type=apartment&level=strong",
    "/api/units?price_max=5000000", "/api/units?cash_max=4000000&sort=price_desc", "/api/units?signing_max=1500000",
    "/api/units?area_min=100&area_max=160", "/api/units?bedrooms_min=3", "/api/units?bedrooms_min=0",
    "/api/units?delivery=ready", "/api/units?delivery=2028", "/api/units?sort=newest&newer_than=10",
    "/api/units?delivery=soon", "/api/units?price_max=-1", "/api/units?cash_max=nan",
    "/api/units/1", "/api/units/17", "/api/units/30", "/api/units/24",
    "/api/compounds", "/api/compounds?sort=name", "/api/compounds?sort=gap_asc",
    *[f"/api/{kind}?sort={sort}&page_size=1&page=2" for kind in ("compounds", "developers")
      for sort in ("units", "gap_asc", "gap_desc", "opportunities", "name")],
    "/api/compounds?district=New%20Cairo&q=garden", "/api/compounds/garden",
    "/api/developers", "/api/developers?sort=opportunities", "/api/developers?q=Garden",
    "/api/developers/nile", "/api/districts/new-cairo",
    "/api/lookup?url=https%3A%2F%2Fexample.test%2Fdeal", "/api/lookup?url=https%3A%2F%2Fexample.test%2Flaunch%2F0",
    "/api/evaluate?compound=Garden&property_type=apartment&area=120&price=4200000&finishing=finished",
    "/api/evaluate?compound=Garden&property_type=apartment&area=120&price=9500000&down_payment=1000000&installment_years=6&delivery=2029",
    "/api/evaluate?compound=missing&property_type=villa&area=200&price=8000000",
    "/api/evaluate?compound=Garden&property_type=apartment&area=nan&price=4200000",
    "/api/units?page_size=101", "/api/unknown",
    "/api/units?q=" + "%20".join(["a"] * 100),
])
def test_every_published_route_matches_local_calculations(clients, path):
    local, cloud, _, _ = clients
    old, new = local.get(path), cloud.get(path)
    assert new.status_code == old.status_code
    assert new.json() == old.json()


def test_publication_contains_no_phone_or_raw_payload(clients):
    _, cloud, _, export = clients
    text = export.read_text()
    assert "PRIVATE" not in text and "+201012345678" not in text and "phone_reveal_key" not in text
    assert "description" in cloud.get("/api/units/30").json()["unit"]


def test_incomplete_import_cannot_replace_the_active_catalogue(clients):
    _, cloud, path, export = clients
    statements = export.read_text().replace("'first'", "'second'").splitlines()
    # A failed transfer lost one row, but even an erroneously retried activation remains guarded.
    statements = [s for s in statements if not s.startswith("INSERT OR REPLACE INTO units VALUES ('second',1,")]
    with sqlite3.connect(path) as db:
        db.executescript("\n".join(statements))
        assert db.execute("SELECT value FROM state WHERE key='active'").fetchone()[0] == "first"
        assert db.execute("SELECT ready FROM datasets WHERE version='second'").fetchone()[0] == 0
    assert cloud.get("/api/health").status_code == 200


def test_empty_cloud_database_returns_retryable_unavailable(tmp_path):
    path = tmp_path / "empty.db"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA.read_text())
    with TestClient(create_cloud_app(SQLite(path))) as client:
        response = client.get("/api/health")
        assert response.status_code == 503 and response.headers["Retry-After"] == "5"


def test_retention_protects_an_older_active_version_after_rollback(clients):
    _, _, path, export = clients
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        for index in range(4):
            version = f"copy{index}"
            db.executescript(export.read_text().replace("'first'", repr(version)))
            db.execute("UPDATE datasets SET generated_at=? WHERE version=?", (f"2026-10-0{index+5}", version))
        # 'first' is the oldest version, rolled back to; it was exported with today's date
        db.execute("UPDATE datasets SET generated_at='2026-10-01' WHERE version='first'")
        db.execute("UPDATE state SET value='first' WHERE key='active'")
        db.executescript(retention_sql(2))
        assert {row[0] for row in db.execute("SELECT version FROM datasets")} == {"first", "copy2", "copy3"}
        assert db.execute("SELECT count(*) FROM units WHERE version='first'").fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM documents WHERE version='copy0'").fetchone()[0] == 0


def test_budget_sql_matches_the_local_rule_for_every_published_figure():
    from qayem.cloud_web import budget_clauses
    from qayem.web_common import within
    records = [{"id": i, "price": price, "area_m2": area, "bedrooms": beds,
                "payment": {"cash_equivalent": cash, "remaining": remaining},
                "delivery": {"bucket": bucket, "date": when, "years": None}}
               for i, (price, area, beds, cash, remaining, bucket, when) in enumerate([
                   (5e6, 120, 3, 4e6, 3e6, "2_3y", "2028-06-30"), (3e6, 90, 2, 3e6, 0, "ready", None),
                   (9e6, 200, None, None, None, "unknown", None), (7e6, 150, 0, 5e6, 6e6, "3y_plus", "2031-01-01")], 1)]
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE units (id INTEGER, price REAL, area REAL, public TEXT)")
        db.executemany("INSERT INTO units VALUES (?,?,?,?)",
                       [(r["id"], r["price"], r["area_m2"], json.dumps(r)) for r in records])
        for limits in [{"price_max": 5e6}, {"cash_max": 4e6}, {"signing_max": 2e6}, {"area_min": 100, "area_max": 160},
                       {"bedrooms_min": 2}, {"bedrooms_min": 0}, {"delivery": "ready"}, {"delivery": "2028"},
                       {"delivery": "2040"}, {"newer_than": 2}]:
            clauses, params = budget_clauses(**limits)
            found = {row[0] for row in db.execute(f"SELECT id FROM units WHERE {' AND '.join(clauses)}", params)}
            assert found == {r["id"] for r in records if within(r, **limits)}, limits

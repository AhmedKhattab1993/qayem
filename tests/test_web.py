"""Website behavior using a disposable database; production data is never changed."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qayem.db import init_db
from qayem.models import ParseRun, Property, PropertyVersion
from qayem.web import create_app

SEEN = datetime(2026, 9, 21, tzinfo=timezone.utc)
BASE = {
    "source": "nawy", "title": "Garden apartment", "purpose": "sale", "currency": "EGP",
    "property_type": "apartment", "district": "New Cairo", "city": "Cairo", "bedrooms": 2, "bathrooms": 2,
    "is_installment": False, "is_resale": True, "status": "active", "finishing": "finished",
    "delivery_date": "2025-01-01", "url": "https://example.test/listing", "phone": "+201012345678",
    "raw": {"phone_reveal_key": "PRIVATE"}, "first_seen_at": SEEN, "last_seen_at": SEEN,
}
# (compound, developer, cash EGP/m²): two developers in one district, one priced far higher.
COMPOUNDS = [("Garden", "Nile Developments", 50_000), ("Lake", "Delta", 80_000)]


def rows() -> list[dict]:
    out = []
    for compound, developer, ppm in COMPOUNDS:
        for index in range(8):
            area = 100 + 10 * index
            out.append({"compound": compound, "developer": developer, "area_m2": area,
                        "price": ppm * area * (0.97 + 0.02 * (index % 4)), "down_payment": ppm * area,
                        "url": f"https://example.test/{compound.lower()}/{index}"})
    # ids 1-8: Garden, 9-16: Lake
    special = [
        # 17: a Garden unit priced 30% under its compound, cash
        {"compound": "Garden", "developer": "Nile", "area_m2": 120, "price": 35_000 * 120, "url": "https://www.example.test/deal/"},
        # 18: a Garden unit on a six-year plan: headline above cash value
        {"compound": "Garden", "developer": "Nile Developments", "area_m2": 120, "price": 9_500_000,
         "is_installment": True, "down_payment": 1_000_000, "installment_months": 72},
        # 19: classifieds listing without payment terms
        {"source": "semsar", "compound": "Garden", "developer": None, "area_m2": 120, "price": 6_000_000},
        # 20: installments with no term
        {"source": "gpm", "compound": "Lake", "developer": "Delta", "area_m2": 120, "price": 9_600_000,
         "is_installment": True, "down_payment": 2_000_000},
        # 21: unmodelled class; 22: unidentified resale
        {"property_type": "office", "compound": "Lake", "area_m2": 80, "price": 5_000_000},
        {"is_resale": None, "compound": "Lake", "developer": "Delta", "area_m2": 100, "price": 8_000_000},
        # 23: a typo-sized price
        {"compound": "Garden", "developer": "Nile", "area_m2": 120, "price": 150_000},
        # 24-29: ineligible
        {"price": 10}, {"district": None, "compound": None}, {"purpose": "rent"}, {"currency": "USD"},
        {"status": "removed"}, {"area_m2": 2_147_483_647},
        # 30: unsafe values
        {"compound": "Garden", "developer": "Nile", "area_m2": 120, "price": 6_000_000, "bedrooms": 1200,
         "url": "javascript:alert(1)", "description": "<b>Call +201012345678</b> <script>alert('x')</script>"},
        # 31-32: the developer's launch units in a new phase of Garden (primary market)
        *({"source": "nawy_primary", "compound": "Garden - New Phase", "developer": "Nile", "area_m2": 120,
           "price": 12_000_000, "is_installment": True, "down_payment": 600_000, "installment_months": 96,
           "is_resale": False, "delivery_date": "2029-06-30", "url": f"https://example.test/launch/{i}"}
          for i in range(2)),
    ]
    return out + special


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    with Session(engine) as session:
        for index, overrides in enumerate(rows(), 1):
            session.add(Property(**(BASE | {"id": index, "source_listing_id": str(index)} | overrides)))
        session.add(ParseRun(source="nawy", status="partial", started_at=SEEN))
        session.add(ParseRun(source="gpm", status="completed", started_at=SEEN))
        session.add(PropertyVersion(property_id=1, captured_at=SEEN, change_type="updated",
                                    payload={"price": 1}, changed_fields={
                                        "delivery_date": {"old": "2024-01-01", "new": "2025-01-01"}}))
        session.commit()
    engine.dispose()
    return path


@pytest.fixture()
def client(database: Path, tmp_path: Path) -> TestClient:
    with TestClient(create_app(database, tmp_path / "no-build")) as test_client:
        yield test_client


def unit(client: TestClient, unit_id: int) -> dict:
    return client.get(f"/api/units/{unit_id}").json()["unit"]


def test_inventory_and_eligibility(client: TestClient):
    listing = client.get("/api/units", params={"page_size": 100}).json()
    ids = {item["id"] for item in listing["items"]}
    assert 22 not in ids and len(ids) == listing["total"] == 23
    assert client.get("/api/units", params={"resale": "all"}).json()["total"] == 24
    for ineligible in range(24, 30):
        assert client.get(f"/api/units/{ineligible}").status_code == 404
    overview = client.get("/api/overview").json()
    assert (overview["total_records"], overview["total_eligible"], overview["total_resale"]) == (32, 24, 23)
    assert overview["history_ready"] is False
    assert overview["scope"]["sources"][0] == {"id": "nawy", "name": "Nawy", "count": 21, "share": 0.913}


def test_valuation_uses_compound_and_developer_not_just_area(client: TestClient):
    garden, deal = unit(client, 3), unit(client, 17)
    assert garden["valuation"]["grade"] == "A"
    assert 45_000 < garden["valuation"]["fair_ppm"] < 55_000
    assert garden["valuation"]["verdict"] == "within"
    lake_unit = unit(client, 12)
    assert lake_unit["compound"]["name"] == "Lake"
    assert 70_000 < lake_unit["valuation"]["fair_ppm"] < 88_000
    # Same district, same class, but priced against its own compound: a Lake-level price is not "below".
    assert garden["developer"] == {"key": "nile", "name": "Nile Developments"}
    developers = {d["key"]: d for d in client.get("/api/developers").json()["items"]}
    assert developers["delta"]["premium_vs_district"] > 0 > developers["nile"]["premium_vs_district"]
    assert deal["valuation"]["verdict"] == "below" and deal["valuation"]["deviation"] < -0.2


def test_payment_terms_drive_cash_equivalent(client: TestClient):
    assert unit(client, 1)["payment"]["terms"] == "cash"
    plan = unit(client, 18)
    assert plan["payment"]["terms"] == "plan"
    assert plan["payment"]["cash_equivalent"] < plan["price"]
    assert plan["valuation"]["basis"] == "cash_equivalent"
    assert plan["valuation"]["fair_headline"] > plan["valuation"]["fair_value"]
    unknown = unit(client, 19)
    assert unknown["payment"]["terms"] == "unknown" and unknown["valuation"]["verdict"] is None
    assert "payment_terms" in unknown["unknowns"]
    partial = unit(client, 20)
    assert partial["payment"]["terms"] == "partial"
    assert partial["valuation"]["status"] == "valued" and partial["valuation"]["verdict"] is None
    assert unit(client, 21)["valuation"]["status"] == "not_modelled"
    assert unit(client, 23)["valuation"]["verdict"] == "suspect"


def test_units_filters_and_sorting(client: TestClient):
    below = client.get("/api/units", params={"verdict": "below"}).json()
    assert [item["id"] for item in below["items"]] == [17]
    ranked = client.get("/api/units", params={"sort": "value", "page_size": 3}).json()["items"]
    assert ranked[0]["id"] == 17 and all(i["valuation"]["verdict"] != "suspect" for i in ranked)
    assert client.get("/api/units", params={"compound": "lake", "terms": "partial"}).json()["total"] == 1
    assert client.get("/api/units", params={"source": "GPM"}).json()["total"] == 1
    assert client.get("/api/units", params={"developer": "Nile Developments"}).json()["total"] >= 8
    assert client.get("/api/units", params={"q": "%' OR 1=1 --"}).json()["total"] == 0


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page_size": 101}, {"sort": "price;DROP TABLE properties"}, {"resale": "false"},
    {"verdict": "cheap"}, {"grade": "Z"},
])
def test_invalid_query_values_return_422(client: TestClient, params: dict):
    assert client.get("/api/units", params=params).status_code == 422


def test_detail_is_sanitized_and_explains_itself(client: TestClient):
    detail = client.get("/api/units/30").json()
    text = json.dumps(detail)
    assert "PRIVATE" not in text and "phone" not in text and '"raw"' not in text and "images" not in text
    assert detail["unit"]["source_url"] is None and detail["unit"]["bedrooms"] is None
    assert "+201012345678" not in detail["unit"]["description"] and "<script>" not in detail["unit"]["description"]
    assert [level["level"] for level in detail["breakdown"]["levels"]] == ["class", "district", "developer", "compound"]
    assert {a["factor"] for a in detail["breakdown"]["adjustments"]} == {"type", "finishing", "delivery", "plan", "size"}
    assert all(c["compound"]["key"] == "garden" for c in detail["comparables"])
    assert client.get("/api/units/999999").status_code == 404


def test_compounds_developers_and_districts(client: TestClient):
    compounds = client.get("/api/compounds", params={"district": "new cairo"}).json()
    assert {c["key"] for c in compounds["items"]} == {"garden", "lake"}
    assert compounds["district"]["name"] == "New Cairo"
    lake = client.get("/api/compounds/lake").json()
    assert lake["compound"]["developer"]["key"] == "delta"
    assert lake["compound"]["classes"][0]["grade"] == "A"
    assert lake["developer"]["key"] == "delta" and lake["district"]["key"] == "new-cairo"
    nile = client.get("/api/developers/nile").json()
    assert nile["delivery_changes"]["postponed"] == 1
    assert client.get("/api/compounds/nowhere").status_code == 404
    catalog = client.get("/api/catalog").json()
    assert {"garden", "lake"} <= {c["key"] for c in catalog["compounds"]}


def test_launch_prices_are_a_benchmark_not_inventory(client: TestClient):
    assert client.get("/api/units", params={"resale": "all", "page_size": 100}).json()["total"] == 24
    assert client.get("/api/units/31").status_code == 404
    garden = client.get("/api/compounds/garden").json()["compound"]
    assert garden["launch"]["units"] == 2 and garden["launch"]["phases"] == ["Garden - New Phase"]
    assert garden["launch"]["median_plan_years"] == 8.0
    # launch cash-equivalent vs the resale model's value for the same unit on the same plan
    assert garden["launch"]["median_spread"] > 0
    assert client.get("/api/developers/nile").json()["launch"]["units"] == 2
    assert client.get("/api/overview").json()["launch"]["compared"] == 2


def test_evaluate_values_a_described_unit(client: TestClient):
    params = {"property_type": "apartment", "area": 120, "price": 7_200_000, "compound": "lake",
              "down_payment": 2_000_000, "installment_years": 5, "delivery": "2028", "finishing": "finished"}
    result = client.get("/api/evaluate", params=params).json()
    assert result["inputs"]["compound"]["name"] == "Lake" and result["inputs"]["developer"]["key"] == "delta"
    assert result["payment"]["terms"] == "plan" and result["payment"]["cash_equivalent"] < 7_200_000
    assert result["valuation"]["grade"] == "A" and result["valuation"]["verdict"] == "below"
    cash = client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000,
                                                "compound": "Garden"}).json()
    assert cash["payment"]["terms"] == "cash" and cash["valuation"]["verdict"] == "within"
    fallback = client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000,
                                                    "compound": "Unknown Heights", "district": "New Cairo"}).json()
    assert fallback["notes"] == ["compound_not_found"] and fallback["valuation"]["grade"] in {"B", "C"}
    outside = client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000,
                                                   "district": "New Cairo"}).json()
    assert outside["valuation"]["status"] == "insufficient"  # no evidence outside compounds: refuse, don't guess
    assert client.get("/api/evaluate", params={**params, "down_payment": 9_000_000}).status_code == 422
    assert client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000}).status_code == 422
    assert client.get("/api/evaluate", params={**params, "delivery": "soon"}).status_code == 422


def test_lookup_matches_normalized_links_only(client: TestClient):
    assert client.get("/api/lookup", params={"url": "https://example.test/deal"}).json() == {"id": 17}
    assert client.get("/api/lookup", params={"url": "https://example.test/listing"}).status_code == 404


def test_requests_cannot_write_the_source_database(client: TestClient, database: Path):
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    for route in ("health", "overview", "catalog", "units", "units/1", "compounds", "developers"):
        assert client.get(f"/api/{route}").status_code == 200
    assert client.post("/api/units", json={"price": 1}).status_code in (404, 405)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        connection = client.app.state.catalog.connect()
        try:
            connection.execute("DELETE FROM properties")
        finally:
            connection.close()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_database_without_delivery_date_column_still_serves(database: Path):
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE properties DROP COLUMN delivery_date")
    with TestClient(create_app(database)) as client:
        assert unit(client, 1)["delivery"] == {"bucket": "unknown", "date": None, "years": None}


def test_missing_database_is_actionable_and_never_created(tmp_path: Path):
    missing = tmp_path / "nonexistent" / "qayem.db"
    with TestClient(create_app(missing)) as client:
        for route in ("health", "units", "overview", "catalog"):
            response = client.get(f"/api/{route}")
            assert response.status_code == 503 and "QAYEM_DB" in response.json()["detail"]
    assert not missing.exists() and not missing.parent.exists()


def test_cache_refreshes_when_an_external_ingestion_changes_wal(database: Path):
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode = WAL")
        with TestClient(create_app(database, refresh_seconds=0)) as client:
            assert client.get("/api/overview").json()["total_resale"] == 23
            writer.execute("UPDATE properties SET is_resale = 0 WHERE id = 1")
            writer.commit()
            assert client.get("/api/overview").json()["total_resale"] == 22
            assert client.get("/api/units").json()["total"] == 22


def test_refits_are_throttled_while_a_crawl_is_writing(database: Path):
    with TestClient(create_app(database, refresh_seconds=3600)) as client:
        assert client.get("/api/overview").json()["total_resale"] == 23
        with sqlite3.connect(database) as writer:
            writer.execute("UPDATE properties SET is_resale = 0 WHERE id = 1")
        assert client.get("/api/overview").json()["total_resale"] == 23  # served from the last fit


def test_spa_routes_and_unknown_api_remain_separate(database: Path, tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Qayem</title>")
    (dist / "brand.svg").write_text("<svg></svg>")
    (dist / "leak.db").symlink_to(database)
    with TestClient(create_app(database, dist)) as client:
        for route in ("/", "/evaluate", "/units", "/compounds/garden", "/developers", "/methodology"):
            assert client.get(route).status_code == 200
            assert "Qayem" in client.get(route).text
        assert client.get("/brand.svg").status_code == 200
        assert client.get("/missing.js").status_code == 404
        assert client.get("/leak.db").status_code == 404
        for route in ("/api", "/api/not-a-route", "/api/properties"):
            response = client.get(route)
            assert response.status_code == 404
            assert response.headers["content-type"].startswith("application/json")
        assert client.get("/%2e%2e/fixture.db").status_code == 404


def test_listing_whose_price_is_only_the_down_payment_is_hidden(database: Path):
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO property_enrichments (property_id, status, done, claimed_at, description_hash, "
            "model, reasoning_effort, flags) VALUES (17, 'done', 1, '2026-09-27', 'x', 'gpt-6-sol', 'low', "
            "'[\"price_is_down_payment\"]')")
    with TestClient(create_app(database)) as client:
        assert client.get("/api/units/17").status_code == 404
        assert client.get("/api/overview").json()["total_eligible"] == 23

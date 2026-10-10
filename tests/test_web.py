"""Website behavior using a disposable database; production data is never changed."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qayem.db import init_db
from qayem.models import ParseRun, Property, PropertyVersion
from qayem.web import create_app
from qayem.web_common import within
from qayem.website_data import opportunity_key

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
         "url": "javascript:alert(1)",
         "images": ["javascript:alert(1)", "http://example.test/a.jpg", "https://example.test/b.jpg", "https://example.test/b.jpg"],
         "description": "<b>Call +201012345678</b> <script>alert('x')</script>"},
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
    # the two developer-launch rows are a price benchmark, not indexed records
    assert (overview["total_records"], overview["total_eligible"], overview["total_resale"]) == (30, 24, 23)
    assert overview["history_ready"] is False
    assert overview["scope"]["sources"][0] == {"id": "nawy", "name": "Nawy", "count": 21, "share": 0.913}


def test_a_unit_is_compared_with_the_developer_and_with_similar_units_not_valued(client: TestClient):
    deal, typical = unit(client, 17), unit(client, 3)
    assert "valuation" not in deal  # no fair price: comparisons with what can be bought now
    # 17 is 30% under the similar Garden units and 35% under the developer, both listed and in today's money
    assert deal["opportunity"] == {"level": "strong", "score": pytest.approx(-0.325, abs=1e-3),
                                   "signals": ["developer", "peers"]}
    assert deal["peers"]["rank"] == 2 and deal["peers"]["count"] == 12  # only the EGP 150,000 typo is cheaper
    assert deal["peers"]["gap"] == pytest.approx(-0.30, abs=1e-3)
    assert typical["opportunity"]["level"] == "in_line"
    # the developer is 50% dearer as listed, but only 6% in today's money: the smaller gap counts
    assert typical["launch"]["headline_gap"] < -0.49 and typical["launch"]["gap"] == typical["launch"]["cash_gap"]
    lake = unit(client, 12)
    assert lake["opportunity"]["signals"] == ["peers"] and lake["launch"] is None  # priced against Lake, not Garden
    assert lake["peers"]["count"] == 8
    assert unit(client, 23)["opportunity"]["level"] == "check"  # 97% under everything: a listing error
    assert typical["developer"] == {"key": "nile", "name": "Nile Developments", "name_ar": None}


def test_payment_terms_drive_cash_equivalent(client: TestClient):
    assert unit(client, 1)["payment"]["terms"] == "cash"
    plan = unit(client, 18)
    assert plan["payment"]["terms"] == "plan"
    assert plan["payment"]["cash_equivalent"] < plan["price"]
    # 60% dearer than its peers as listed, 2% in today's money: neither cheaper nor pricier on both
    assert plan["peers"]["headline_gap"] > 0.5 and plan["peers"]["cash_gap"] < 0.05
    assert plan["opportunity"]["level"] == "in_line"
    unknown = unit(client, 19)
    assert unknown["payment"]["terms"] == "unknown" and unknown["opportunity"]["level"] == "unrated"
    assert "payment_terms" in unknown["unknowns"]
    partial = unit(client, 20)
    assert partial["payment"]["terms"] == "partial" and partial["opportunity"]["level"] == "unrated"
    assert unit(client, 21)["opportunity"]["level"] == "unrated"  # the only office: nothing to compare with


def test_units_filters_and_sorting(client: TestClient):
    strong = client.get("/api/units", params={"level": "strong"}).json()
    assert [item["id"] for item in strong["items"]] == [17]
    ranked = client.get("/api/units", params={"page_size": 100}).json()["items"]  # by opportunity by default
    levels = [item["opportunity"]["level"] for item in ranked]
    assert ranked[0]["id"] == 17 and levels.index("check") > levels.index("in_line")
    assert levels[-3:] == ["unrated"] * 3
    peers = client.get("/api/units", params={"sort": "peer_gap", "page_size": 100}).json()["items"]
    assert peers[0]["id"] == 17 and 23 not in {item["id"] for item in peers}
    assert client.get("/api/units", params={"compound": "lake", "terms": "partial"}).json()["total"] == 1
    assert client.get("/api/units", params={"source": "GPM"}).json()["total"] == 1
    assert client.get("/api/units", params={"developer": "Nile Developments"}).json()["total"] >= 8
    assert client.get("/api/units", params={"q": "%' OR 1=1 --"}).json()["total"] == 0


def test_units_fit_a_buyers_budget_and_needs(client: TestClient):
    every = client.get("/api/units", params={"page_size": 100}).json()["items"]

    def ids(**params):
        return {item["id"] for item in client.get("/api/units", params={"page_size": 100, **params}).json()["items"]}

    def paid(item):
        remaining = item["payment"]["remaining"]
        return None if remaining is None else item["price"] - remaining

    assert ids(price_max=5_000_000) == {i["id"] for i in every if i["price"] <= 5_000_000}
    # unknown terms have no cash value or signing amount, so they never fit a limit on either
    assert ids(cash_max=4_000_000) == {i["id"] for i in every
                                       if i["payment"]["cash_equivalent"] is not None
                                       and i["payment"]["cash_equivalent"] <= 4_000_000}
    signing = ids(signing_max=1_500_000)
    assert signing == {i["id"] for i in every if paid(i) is not None and paid(i) <= 1_500_000}
    assert 19 not in signing and 20 not in signing  # unknown and partial terms
    assert ids(area_min=100, area_max=160) == {i["id"] for i in every if 100 <= i["area_m2"] <= 160}
    assert ids(bedrooms_min=3) == {i["id"] for i in every if (i["bedrooms"] or -1) >= 3}
    ready = ids(delivery="ready")
    assert ready == {i["id"] for i in every if i["delivery"]["bucket"] == "ready"}
    assert ready <= ids(delivery="2030")
    newest = client.get("/api/units", params={"sort": "newest", "newer_than": 10, "page_size": 100}).json()["items"]
    assert [i["id"] for i in newest] == sorted((i["id"] for i in every if i["id"] > 10), reverse=True)
    assert client.get("/api/units", params={"delivery": "soon"}).status_code == 422


def test_bedrooms_and_delivery_limits_never_match_what_a_listing_does_not_publish():
    def record(bedrooms=None, bucket="unknown", when=None):
        return {"id": 1, "price": 5e6, "area_m2": 120, "bedrooms": bedrooms,
                "payment": {"cash_equivalent": None, "remaining": None},
                "delivery": {"bucket": bucket, "date": when, "years": None}}

    assert within(record(bedrooms=3), bedrooms_min=3) and within(record(bedrooms=0), bedrooms_min=0)
    assert not within(record(bedrooms=2), bedrooms_min=3) and not within(record(), bedrooms_min=0)
    assert within(record(bucket="ready"), delivery="ready") and within(record(bucket="ready"), delivery="2027")
    assert within(record(bucket="2_3y", when="2028-06-30"), delivery="2028")
    assert not within(record(bucket="2_3y", when="2028-06-30"), delivery="2027")
    assert not within(record(bucket="2_3y", when="2028-06-30"), delivery="ready")
    assert not within(record(), delivery="2040")  # an unpublished date is not "ready by 2040"


def test_a_unit_cheaper_on_both_comparisons_outranks_one_checked_once():
    def record(id_, signals, score):
        return {"id": id_, "opportunity": {"level": "strong", "signals": signals, "score": score}}
    # a steeper gap on one comparison does not beat clearing both
    once, both = record(1, ["peers"], -0.50), record(2, ["developer", "peers"], -0.30)
    assert sorted([once, both], key=opportunity_key) == [both, once]


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page_size": 101}, {"sort": "price;DROP TABLE properties"}, {"resale": "false"},
    {"level": "cheap"}, {"sort": "value"},
])
def test_invalid_query_values_return_422(client: TestClient, params: dict):
    assert client.get("/api/units", params=params).status_code == 422


def test_detail_is_sanitized_and_explains_itself(client: TestClient):
    detail = client.get("/api/units/30").json()
    text = json.dumps(detail)
    assert "PRIVATE" not in text and "phone" not in text and '"raw"' not in text
    # photos as the source published them: https links only, each once
    assert detail["unit"]["images"] == ["https://example.test/b.jpg"] and detail["unit"]["photo"] == "https://example.test/b.jpg"
    assert detail["unit"]["source_url"] is None and detail["unit"]["bedrooms"] is None
    assert "+201012345678" not in detail["unit"]["description"] and "<script>" not in detail["unit"]["description"]
    # the similar units it is ranked against, nearest in size first
    assert [c["area_m2"] for c in detail["comparables"]][:3] == [120, 120, 120]
    # every similar unit is listed (the page shows the nearest six until asked), each with its seller's contract year
    assert len(detail["comparables"]) == 11 and all(c["compound"]["key"] == "garden" for c in detail["comparables"])
    assert all("contract_year" in c for c in detail["comparables"])
    assert client.get("/api/units/999999").status_code == 404


def test_compounds_developers_and_districts(client: TestClient):
    compounds = client.get("/api/compounds", params={"district": "new cairo"}).json()
    assert {c["key"] for c in compounds["items"]} == {"garden", "lake"}
    assert compounds["district"]["name"] == "New Cairo"
    # The website shows districts in Arabic, so an Arabic district search finds them too.
    arabic = client.get("/api/compounds", params={"q": "القاهرة الجديدة"}).json()
    assert {c["key"] for c in arabic["items"]} >= {"garden", "lake"}
    lake =client.get("/api/compounds/lake").json()
    assert lake["compound"]["developer"]["key"] == "delta"
    apartments = lake["compound"]["classes"][0]
    assert apartments["class"] == "apartment" and apartments["median_asking_ppm"] == 80_000
    assert apartments["developer_ppm"] is None  # Delta is not selling in Lake
    assert lake["developer"]["key"] == "delta" and lake["district"]["key"] == "new-cairo"
    garden = client.get("/api/compounds/garden").json()["compound"]
    assert garden["opportunities"]["strong"] == 1 and garden["good_count"] == 1
    assert [c["key"] for c in client.get("/api/compounds", params={"sort": "opportunities"}).json()["items"]][0] == "garden"
    ranked = client.get("/api/compounds", params={"sort": "gap_asc"}).json()["items"]
    assert [c["key"] for c in ranked] == ["garden"]  # only compounds with a developer price are ranked
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
    assert garden["launch"]["median_plan_years"] == 8.0 and garden["launch"]["median_headline_ppm"] == 100_000
    # the median like-for-like resale unit against the developer, on the less favourable basis
    assert garden["launch"]["compared"] == 12 and garden["launch"]["median_gap"] < 0
    assert garden["classes"][0]["developer_ppm"] == 100_000
    assert client.get("/api/developers/nile").json()["launch"]["units"] == 2
    assert client.get("/api/overview").json()["launch"]["matched"] == 2


def test_each_resale_unit_is_compared_with_the_developers_price_for_a_similar_unit(client: TestClient):
    garden = unit(client, 3)  # 120 m², cash, finished, delivered
    launch = garden["launch"]
    assert launch["units"] == 2 and launch["plan_years"] == 8.0 and launch["delivery_year"] == 2029
    # both sides in today's money: the launch plan is discounted like the resale balance
    assert launch["developer_price"] == 12_000_000 and launch["developer_cash"] < 12_000_000
    assert launch["cash_gap"] == pytest.approx(garden["payment"]["cash_equivalent"] / launch["developer_cash"] - 1, abs=1e-3)
    assert launch["headline_gap"] == pytest.approx(garden["price"] / 12_000_000 - 1, abs=1e-3)
    assert launch["gap"] == max(launch["cash_gap"], launch["headline_gap"])
    assert unit(client, 12)["launch"] is None  # Lake: the developer has no current launch
    ranked = client.get("/api/units", params={"sort": "launch_gap", "page_size": 100}).json()["items"]
    assert ranked and all(item["compound"]["key"] == "garden" for item in ranked)
    gaps = [item["launch"]["gap"] for item in ranked]
    assert gaps == sorted(gaps)
    only = client.get("/api/units", params={"launch": "true", "page_size": 100}).json()["items"]
    # the ranking leaves out prices too far from anything to be real (unit 23: EGP 150,000)
    left_out = {item["id"] for item in only} - {item["id"] for item in ranked}
    assert left_out == {23} and unit(client, 23)["opportunity"]["level"] == "check"


def test_a_contract_price_unit_shows_how_the_developers_price_moved_since_it_was_signed(database: Path):
    with sqlite3.connect(database) as writer:
        writer.execute("""UPDATE properties SET source = 'aqarexit', raw = '{"contract_year": "2024"}' WHERE id = 3""")
        writer.execute("""UPDATE properties SET raw = '{"contract_year": "2024"}' WHERE id = 4""")  # Nawy: not a contract price
    with TestClient(create_app(database)) as client:
        garden = unit(client, 3)
        assert garden["contract_year"] == 2024
        since = garden["launch"]["since_contract"]
        # the developer lists similar units at 100,000/m² today (EGP 12M for 120 m²)
        assert since["year"] == 2024 and since["contract_ppm"] == garden["price_per_m2"]
        assert since["change"] == pytest.approx(100_000 / garden["price_per_m2"] - 1, abs=1e-3)
        years = (datetime(2026, 9, 21) - datetime(2024, 7, 1)).days / 365.25
        assert since["annual"] == pytest.approx((1 + since["change"]) ** (1 / years) - 1, abs=1e-3)
        assert unit(client, 4)["contract_year"] is None and unit(client, 4)["launch"]["since_contract"] is None


def test_spellings_resolve_to_one_compound_with_its_arabic_name(database: Path):
    from qayem.valuation import alias_key
    with sqlite3.connect(database) as writer:
        writer.execute("UPDATE properties SET compound = 'جاردن', developer = 'نايل' WHERE id IN (5, 6, 7, 8)")
        writer.execute("UPDATE properties SET compound = 'التجمع الخامس' WHERE id = 16")
        for key, kind, compound, compound_ar, reference, confidence in (
                (alias_key("جاردن", "نايل"), "compound", "Garden", "جاردن", "Garden - New Phase", "high"),
                (alias_key("Garden", "Nile Developments"), "compound", "Garden", "جاردن", "Garden - New Phase", "high"),
                (alias_key("التجمع الخامس", "Delta"), "not_compound", None, None, None, "high"),
                (alias_key("Lake", "Delta"), "compound", "Lake Towers", None, None, "low")):
            writer.execute(
                "INSERT INTO entity_aliases (key, status, kind, compound, compound_ar, developer, developer_ar, "
                "reference, confidence, listings, attempts) VALUES (?, 'done', ?, ?, ?, 'Nile Developments', 'نايل', ?, ?, 1, 1)",
                (key, kind, compound, compound_ar, reference, confidence))
    with TestClient(create_app(database)) as client:
        garden = client.get("/api/compounds/garden").json()["compound"]
        assert garden["name"] == "Garden" and garden["name_ar"] == "جاردن"
        assert garden["units"] == 13  # every Garden unit, whichever spelling (four are now Arabic)
        assert unit(client, 5)["compound"]["key"] == "garden"
        assert unit(client, 5)["developer"]["name_ar"] == "نايل"
        assert unit(client, 16)["compound"] is None  # a district is not a compound
        assert unit(client, 12)["compound"]["name"] == "Lake"  # low-confidence answers are not applied
        # the launch units are placed through the Nawy name the spellings resolve to
        assert garden["launch"]["units"] == 2


def test_a_launch_named_by_sub_project_joins_its_compound_through_its_alias(database: Path):
    from qayem.valuation import alias_key
    with sqlite3.connect(database) as writer:
        writer.execute("UPDATE properties SET compound = 'Sunrise - Garden' WHERE source = 'nawy_primary'")
    with TestClient(create_app(database)) as client:
        assert client.get("/api/compounds/garden").json()["compound"]["launch"] is None  # no name or prefix match
    with sqlite3.connect(database) as writer:
        writer.execute(
            "INSERT INTO entity_aliases (key, status, kind, compound, developer, reference, confidence, listings, "
            "attempts) VALUES (?, 'done', 'compound', 'Garden', 'Nile', 'Sunrise - Garden', 'high', 2, 1)",
            (alias_key("Sunrise - Garden", "Nile"),))
    with TestClient(create_app(database)) as client:
        assert client.get("/api/compounds/garden").json()["compound"]["launch"]["units"] == 2
        assert unit(client, 3)["launch"]["units"] == 2


def test_evaluate_compares_a_described_unit(client: TestClient):
    params = {"property_type": "apartment", "area": 120, "price": 7_200_000, "compound": "lake",
              "down_payment": 2_000_000, "installment_years": 5, "delivery": "2028", "finishing": "finished"}
    result = client.get("/api/evaluate", params=params).json()
    assert result["status"] == "compared" and "valuation" not in result
    assert result["inputs"]["compound"]["name"] == "Lake" and result["inputs"]["developer"]["key"] == "delta"
    assert result["payment"]["terms"] == "plan" and result["payment"]["cash_equivalent"] < 7_200_000
    # EGP 60,000/m² against Lake units at 80,000: cheaper both as listed and in today's money
    assert result["peers"]["headline_gap"] == pytest.approx(-0.25, abs=0.02)
    assert result["opportunity"]["level"] in ("good", "strong") and result["launch"] is None
    assert len(result["comparables"]) == 8  # all the similar units, nearest in size first
    garden = client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000,
                                                 "compound": "Garden", "finishing": "finished"}).json()
    assert garden["payment"]["terms"] == "cash" and garden["opportunity"]["signals"] == ["developer", "peers"]
    assert garden["opportunity"]["level"] == "in_line"
    unsure = client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000,
                                                 "compound": "Garden"}).json()
    assert unsure["opportunity"]["signals"] == ["peers"]  # finishing unknown: not like for like with the developer
    unknown = client.get("/api/evaluate", params={"property_type": "apartment", "area": 120, "price": 6_000_000,
                                                  "compound": "Unknown Heights"}).json()
    assert unknown["status"] == "compound_not_found" and unknown["opportunity"]["level"] == "unrated"
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


def test_changed_database_is_served_from_the_last_fit_while_it_refits(database: Path):
    with TestClient(create_app(database, refresh_seconds=0.01)) as client:
        catalog = client.app.state.catalog
        assert client.get("/api/overview").json()["total_resale"] == 23
        with sqlite3.connect(database) as writer:
            writer.execute("UPDATE properties SET is_resale = 0 WHERE id = 1")
        time.sleep(0.05)
        assert client.get("/api/overview").json()["total_resale"] == 23  # never blocks on the refit
        for _ in range(200):
            if client.get("/api/overview").json()["total_resale"] == 22:
                break
            time.sleep(0.05)
        assert client.get("/api/overview").json()["total_resale"] == 22
        assert not catalog._refreshing


def test_only_the_configured_sources_are_shown_and_fitted(database: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QAYEM_SOURCES", "gpm")
    with TestClient(create_app(database)) as client:
        overview = client.get("/api/overview").json()
        assert [source["id"] for source in overview["sources"]] == ["gpm"]
        assert {item["source"] for item in client.get("/api/units").json()["items"]} == {"gpm"}
        assert overview["launch"]["compared"] == 0  # launch benchmarks come from nawy_primary
        assert client.get("/api/units/1").status_code == 404  # a Nawy listing


def test_aqarexit_is_the_default_source(monkeypatch: pytest.MonkeyPatch):
    from qayem.config import active_sources
    monkeypatch.delenv("QAYEM_SOURCES")
    assert active_sources() == {"aqarexit"}
    monkeypatch.setenv("QAYEM_SOURCES", "aqarexit, Nawy")
    assert active_sources() == {"aqarexit", "nawy"}


@pytest.mark.parametrize("developer, peers, level", [
    ((-0.30, -0.40), (-0.20, -0.20), "strong"),   # every comparison ≥15% under, one ≥25%
    ((-0.30, -0.10), None, "good"),              # the less favourable basis is 10% under
    ((-0.12, -0.50), (0.12, 0.20), "mixed"),     # cheaper than the developer, dearer than similar units
    ((0.15, 0.30), None, "pricier"),             # dearer on both bases
    ((0.40, -0.20), None, "in_line"),            # dearer only on one basis: not pricier
    ((-0.08, -0.60), None, "in_line"),           # cheaper only on one basis: not a deal
    (None, (-0.65, -0.70), "check"),             # too far below everything to be real
    (None, None, "unrated"),
])
def test_opportunity_levels_need_both_bases_to_agree(developer, peers, level):
    from qayem.website_data import opportunity
    record = {
        "launch": {"cash_gap": developer[0], "headline_gap": developer[1], "gap": max(developer), "same_finishing": True}
        if developer else None,
        "peers": {"cash_gap": peers[0], "headline_gap": peers[1], "gap": max(peers), "cheapest_gap": 0.1}
        if peers else None,
    }
    assert opportunity(record)["level"] == level


def test_a_unit_far_below_even_the_cheapest_similar_unit_is_checked_first():
    from qayem.website_data import opportunity
    # 51% under the median of similar units passes, but 30% under the cheapest of them is an outlier to verify
    peers = {"cash_gap": -0.51, "headline_gap": -0.63, "gap": -0.51, "cheapest_gap": -0.30}
    assert opportunity({"launch": None, "peers": peers})["level"] == "check"
    assert opportunity({"launch": None, "peers": {**peers, "cheapest_gap": -0.10}})["level"] == "strong"


def test_the_developer_comparison_counts_only_with_the_same_finishing():
    from qayem.website_data import opportunity
    launch = {"cash_gap": -0.5, "headline_gap": -0.5, "gap": -0.5, "same_finishing": False}
    assert opportunity({"launch": launch, "peers": None})["level"] == "unrated"

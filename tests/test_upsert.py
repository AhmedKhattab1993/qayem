"""Tests for the upsert/removal sync engine."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qayem.db import init_db
from qayem.models import Property, PropertyEnrichment, PropertyVersion
from qayem.sources.base import NormalizedListing
from qayem.upsert import (
    canonicalize_property_types, content_hash, description_hash, listing_text, mark_removals, renormalize,
    upsert_listing,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def listing(pid="L1", price=1_000_000.0, title="Flat in Cairo", scope="all") -> NormalizedListing:
    return NormalizedListing(
        source_listing_id=pid,
        scope_key=scope,
        url=f"https://example.test/{pid}",
        title=title,
        purpose="sale",
        price=price,
        currency="EGP",
        area_m2=120.0,
        bedrooms=3,
        is_resale=True,
    )


def _get(session, source, pid) -> Property:
    return (
        session.query(Property)
        .filter_by(source=source, source_listing_id=pid)
        .one()
    )


def test_create_update_unchanged(session):
    assert upsert_listing(session, "nawy", listing()) == "created"
    session.flush()

    prop = _get(session, "nawy", "L1")
    assert prop.status == "active"
    assert prop.first_seen_at is not None

    # same content → unchanged
    assert upsert_listing(session, "nawy", listing()) == "unchanged"
    session.flush()

    # changed price → updated with a diff version
    assert upsert_listing(session, "nawy", listing(price=950_000.0)) == "updated"
    session.flush()

    versions = (
        session.query(PropertyVersion)
        .filter_by(property_id=prop.id)
        .order_by(PropertyVersion.id)
        .all()
    )
    assert [v.change_type for v in versions] == ["created", "updated"]
    assert versions[1].changed_fields == {"price": {"old": 1_000_000.0, "new": 950_000.0}}
    assert _get(session, "nawy", "L1").price == 950_000.0


def test_guarded_removal_and_relist(session):
    # first run sees L1 and L2
    upsert_listing(session, "gpm", listing("L1"))
    upsert_listing(session, "gpm", listing("L2"))
    session.flush()

    # simulate time passing: their last_seen is now in the past
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    for p in session.query(Property).all():
        p.last_seen_at = past
    session.flush()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    # second run sees only L1 → L2 is gone
    assert upsert_listing(session, "gpm", listing("L1")) == "unchanged"
    session.flush()
    assert mark_removals(session, "gpm", "all", cutoff) == 1
    session.flush()

    l2 = _get(session, "gpm", "L2")
    assert l2.status == "removed"
    assert l2.removed_at is not None
    removals = session.query(PropertyVersion).filter_by(property_id=l2.id).all()
    assert [v.change_type for v in removals] == ["created", "removed"]

    # row is kept, not deleted
    assert _get(session, "gpm", "L2") is not None

    # removal is scoped per source: another source with the same id is untouched
    upsert_listing(session, "nawy", listing("L2"))
    session.flush()
    assert _get(session, "nawy", "L2").status == "active"

    # L2 shows up again in gpm → relisted
    assert upsert_listing(session, "gpm", listing("L2")) == "relisted"
    session.flush()
    l2 = _get(session, "gpm", "L2")
    assert l2.status == "active"
    assert l2.removed_at is None
    types = [v.change_type for v in session.query(PropertyVersion).filter_by(property_id=l2.id)]
    assert types == ["created", "removed", "relisted"]


def test_removal_cutoff_spares_seen_listings(session):
    upsert_listing(session, "semsar", listing("L1"))
    session.flush()
    prop = _get(session, "semsar", "L1")
    past = datetime.now(timezone.utc) - timedelta(hours=5)
    prop.last_seen_at = past
    session.flush()

    # cutoff before the listing was re-seen, then re-seen now → kept
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    assert upsert_listing(session, "semsar", listing("L1")) == "unchanged"
    session.flush()
    assert mark_removals(session, "semsar", "all", cutoff) == 0
    assert _get(session, "semsar", "L1").status == "active"


def test_removal_scope_isolation(session):
    """A completed run for one scope (e.g. one category) must never mark
    listings from other scopes removed."""
    upsert_listing(session, "semsar", listing("A1", scope="cat:765"))
    upsert_listing(session, "semsar", listing("A2", scope="cat:765"))
    upsert_listing(session, "semsar", listing("B1", scope="cat:766"))
    session.flush()

    past = datetime.now(timezone.utc) - timedelta(hours=2)
    for p in session.query(Property).all():
        p.last_seen_at = past
    session.flush()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    # a complete run covering only cat:765, seeing only A1
    assert upsert_listing(session, "semsar", listing("A1", scope="cat:765")) == "unchanged"
    session.flush()

    assert mark_removals(session, "semsar", "cat:765", cutoff) == 1  # A2 gone
    session.flush()
    assert _get(session, "semsar", "A2").status == "removed"
    assert _get(session, "semsar", "A1").status == "active"
    # a complete cat:766 run sees B1 → B1 stays; and it must NOT touch A1/A2
    assert upsert_listing(session, "semsar", listing("B1", scope="cat:766")) == "unchanged"
    session.flush()
    assert mark_removals(session, "semsar", "cat:766", cutoff) == 0
    assert _get(session, "semsar", "B1").status == "active"


def test_new_empty_field_keeps_existing_hashes_stable():
    legacy = listing()
    assert content_hash(legacy) == content_hash(legacy.model_copy(update={"delivery_date": None}))
    assert content_hash(legacy) != content_hash(legacy.model_copy(update={"delivery_date": "2027-01-01"}))


def test_renormalize_rewrites_rows_without_version_rows(session):
    stored = listing().model_copy(update={"raw": {"id": "L1", "ready": "2028-03-01"}})
    upsert_listing(session, "nawy", stored)
    session.flush()
    seen = _get(session, "nawy", "L1").last_seen_at

    def parse(raw):
        return stored.model_copy(update={"delivery_date": raw["ready"]})

    assert renormalize(session, "nawy", parse) == (1, 1)
    session.flush()
    prop = _get(session, "nawy", "L1")
    assert prop.delivery_date == "2028-03-01" and prop.last_seen_at == seen
    assert session.query(PropertyVersion).count() == 1
    # the next crawl of the same payload is recognised as unchanged
    assert upsert_listing(session, "nawy", parse(stored.raw)) == "unchanged"


def test_init_db_adds_columns_to_an_existing_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE properties DROP COLUMN delivery_date")
    init_db(engine)
    with sqlite3.connect(path) as connection:
        assert "delivery_date" in {row[1] for row in connection.execute("PRAGMA table_info(properties)")}


def test_backfill_fills_only_empty_columns_and_next_parse_records_no_version(tmp_path):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from qayem.db import init_db
    from qayem.models import Property, PropertyEnrichment, PropertyVersion
    from qayem.sources.base import NormalizedListing
    from qayem.sources.semsar import parse_description
    from qayem.upsert import backfill_from_description, upsert_listing

    engine = create_engine(f"sqlite:///{tmp_path / 'qayem.db'}")
    init_db(engine)
    text = "شقة للبيع (تمليك) في القاهرة مصر، 3 غرف، 120 م² بالتقسيط متشطب سوبر لوكس . مقدم دفعة أولى 500,000 جنيه"
    old_parse = NormalizedListing(source_listing_id="S1", description=text, price=2_000_000, bedrooms=4)
    with Session(engine) as session:
        upsert_listing(session, "semsar", old_parse)
        session.commit()
        assert backfill_from_description(session, "semsar", parse_description) == (1, 1)
        session.commit()
        prop = session.execute(select(Property)).scalar_one()
        assert (prop.finishing, prop.down_payment, prop.is_installment) == ("super_lux", 500_000, True)
        assert prop.bedrooms == 4  # a known value is never overwritten
        new_parse = NormalizedListing(
            source_listing_id="S1", description=text, price=2_000_000, bedrooms=4,
            finishing="super_lux", down_payment=500_000, is_installment=True)
        assert upsert_listing(session, "semsar", new_parse) == "unchanged"
        session.commit()
        assert session.scalar(select(func.count()).select_from(PropertyVersion)) == 1  # only "created"


def stored_fill(session, prop, text, applied):
    """A description-enrichment record as earlier runs left it (no new ones are made)."""
    session.add(PropertyEnrichment(
        property_id=prop.id, status="done", done=True, claimed_at=prop.first_seen_at,
        description_hash=description_hash(text), model="glm-5.3-flash",
        reasoning_effort="low", applied=applied,
    ))


def test_stored_fills_survive_updates_only_while_the_text_is_unchanged(session):
    def text_listing(price, title="Listing"):
        return NormalizedListing(source_listing_id="A1", title=title, description="شقة 120 متر",
                                 price=price, property_type=None, purpose="sale", currency="EGP")

    upsert_listing(session, "opensooq", text_listing(1_000_000))
    session.flush()
    prop = session.query(Property).one()
    prop.property_type = "apartment"
    stored_fill(session, prop, listing_text("Listing", "شقة 120 متر"), {"property_type": "apartment"})
    session.commit()

    upsert_listing(session, "opensooq", text_listing(900_000))
    session.commit()
    assert session.query(Property).one().property_type == "apartment"

    upsert_listing(session, "opensooq", text_listing(800_000, title="Changed"))
    session.commit()
    assert session.query(Property).one().property_type is None


def test_fills_recorded_before_titles_were_sent_still_reapply(session):
    upsert_listing(session, "opensooq", NormalizedListing(
        source_listing_id="A1", title="T", description="شقة", price=1.0))
    session.flush()
    prop = session.query(Property).one()
    prop.property_type = "apartment"
    stored_fill(session, prop, "شقة", {"property_type": "apartment"})
    session.commit()
    upsert_listing(session, "opensooq", NormalizedListing(
        source_listing_id="A1", title="T", description="شقة", price=2.0))
    session.commit()
    assert session.query(Property).one().property_type == "apartment"


def test_type_text_kept_verbatim_becomes_its_canonical_type(session):
    for pid, kind in (("P1", "بنتهاوس"), ("P2", "apartment"), ("P3", "مجهول")):
        upsert_listing(session, "aqarexit", NormalizedListing(source_listing_id=pid, title=kind, property_type=kind))
    upsert_listing(session, "nawy", NormalizedListing(source_listing_id="N1", title="x", property_type="بنتهاوس"))
    session.commit()
    assert canonicalize_property_types(session, "aqarexit") == 1
    types = {(p.source, p.source_listing_id): p.property_type for p in session.query(Property)}
    assert types == {("aqarexit", "P1"): "penthouse", ("aqarexit", "P2"): "apartment",
                     ("aqarexit", "P3"): "مجهول", ("nawy", "N1"): "بنتهاوس"}
    assert session.query(PropertyVersion).filter_by(change_type="updated").count() == 0

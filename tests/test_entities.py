"""Compound/developer spelling resolution, with the model replaced by canned answers."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from qayem import entities
from qayem.db import init_db
from qayem.models import EntityAlias, Property
from qayem.valuation import alias_key, fold

SEEN = datetime(2026, 9, 21, tzinfo=timezone.utc)


def listing(index: int, source: str, compound: str, developer: str | None, district: str = "New Cairo") -> Property:
    return Property(id=index, source=source, source_listing_id=str(index), purpose="sale", status="active",
                    compound=compound, developer=developer, district=district, first_seen_at=SEEN, last_seen_at=SEEN)


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QAYEM_SOURCES", "aqarexit")
    engine = create_engine(f"sqlite:///{tmp_path / 'entities.db'}")
    init_db(engine)
    with Session(engine) as session:
        session.add_all([
            listing(1, "aqarexit", "باديا", "بالم هيلز", "6 أكتوبر"),
            listing(2, "aqarexit", "بادية", "بالم هيلز", "6 أكتوبر"),
            listing(3, "aqarexit", "Badya", "Palm hills", "6 أكتوبر"),
            listing(4, "aqarexit", "Badya ", "Palm Hills", "6 أكتوبر"),
            listing(5, "aqarexit", "التجمع الخامس", "مالك", "التجمع الخامس"),
            listing(6, "nawy", "Badya", "Palm Hills Developments", "October Gardens"),
            listing(7, "nawy_primary", "Badya", "Palm Hills Developments", "October Gardens"),
            listing(8, "nawy_primary", "Sarai", "Madinet Masr", "New Cairo"),
        ])
        session.commit()
    return engine


def test_spellings_fold_letter_variants_but_not_different_words():
    assert fold("كمبوند سراى") == fold("سراي") == "سراي"
    assert fold("بادية") == fold("باديه") != fold("باديا")
    assert alias_key("Badya ", "Palm Hills") == alias_key("badya", "Palm Hills Developments")
    assert alias_key(None, "Palm Hills") is None


def test_pairs_come_from_the_sources_in_use_and_the_reference_from_nawy(engine):
    pairs = entities.spelling_pairs(engine)
    # AqarExit's spellings and the launch names of the benchmark (Nawy resale is not in use)
    assert {pair.compound for pair in pairs} == {"باديا", "بادية", "Badya", "التجمع الخامس", "Sarai"}
    assert next(p for p in pairs if p.compound == "Badya").listings == 3
    ref = entities.reference(engine)
    assert ref.compounds["Badya"] == {"developer": "Palm Hills Developments", "area": "October Gardens", "units": 2}
    assert set(ref.developers) == {"Palm Hills Developments", "Madinet Masr"}


def answer(index: int, **fields) -> dict:
    return {"id": index, "kind": "compound", "compound": "Badya", "compound_ar": "باديا",
            "developer": "Palm Hills", "developer_ar": "بالم هيلز", "reference": "Badya", "confidence": "high"} | fields


def test_answers_are_validated_before_they_are_stored(engine):
    pairs = entities.spelling_pairs(engine)
    ref = entities.reference(engine)
    index = {pair.compound: i for i, pair in enumerate(pairs)}
    canned = {"items": [
        answer(index["Badya"]),
        answer(index["باديا"], reference="Badya Palm Hills"),  # not a Nawy name
        answer(index["بادية"], reference="Sarai", developer="Madinet Masr"),  # agrees with its own developer
        answer(index["التجمع الخامس"], kind="not_compound", compound=None, reference=None),
        answer(index["Sarai"], compound="Sarai", developer="Madinet Masr", reference="Sarai"),
    ]}
    result = entities.resolve_batch(engine, pairs, ref, [], invoke=lambda prompt: canned)
    assert (result.done, result.failed) == (5, 0)
    with Session(engine) as session:
        rows = {row.compound_text: row for row in session.execute(select(EntityAlias)).scalars()}
    assert rows["Badya"].reference == "Badya"
    assert rows["Badya"].developer == "Palm Hills Developments"  # Nawy's spelling of a matched developer
    assert rows["باديا"].reference is None and rows["باديا"].notes == ["reference_not_listed"]
    assert rows["بادية"].reference == "Sarai"  # a reference agreeing with its developer is kept
    assert rows["التجمع الخامس"].kind == "not_compound" and rows["التجمع الخامس"].compound is None


def test_uncertain_or_conflicting_references_are_dropped(engine):
    ref = entities.reference(engine)
    pair = entities.spelling_pairs(engine)[0]
    unsure = entities.validated(answer(0, confidence="medium"), pair, ref)
    assert unsure["reference"] is None and unsure["notes"] == ["reference_not_certain"]
    conflict = entities.validated(answer(0, developer="Madinet Masr"), pair, ref)
    assert conflict["reference"] is None and conflict["notes"] == ["reference_developer_differs"]


def test_unanswered_pairs_fail_and_are_retried_up_to_the_cap(engine):
    ref = entities.reference(engine)
    for attempt in range(entities.MAX_ATTEMPTS):
        pending = entities.pending(engine)
        assert len(pending) == 5, attempt
        entities.resolve_batch(engine, pending, ref, [], invoke=lambda prompt: {"items": []})
    assert entities.pending(engine) == []
    with Session(engine) as session:
        assert {row.status for row in session.execute(select(EntityAlias)).scalars()} == {"failed"}


def test_a_failed_call_is_recorded_not_raised(engine):
    def broken(prompt):
        raise RuntimeError("Pi exited with status 1")
    result = entities.resolve_batch(engine, entities.pending(engine), entities.reference(engine), [], invoke=broken)
    assert result.done == 0 and result.error == "Pi exited with status 1"


def test_run_sends_only_new_pairs(engine):
    calls = []

    def invoke(prompt):
        calls.append(prompt)
        pairs = entities.pending(engine)
        return {"items": [answer(i) for i in range(len(pairs))]}
    entities.run(engine, invoke=invoke, workers=1)
    assert len(calls) == 1 and "reference:\nBadya | Palm Hills Developments | October Gardens" in calls[0]
    entities.run(engine, invoke=invoke, workers=1)
    assert len(calls) == 1  # nothing new to resolve


def test_a_nawy_launch_is_not_placed_in_a_compound_in_another_area(engine):
    ref = entities.reference(engine)
    launch = entities.Pair("sarai|madinetmasr", "Sarai", "Madinet Masr", "New Cairo", 1)
    moved = entities.validated(answer(0, compound="Badya", developer="Madinet Masr", reference="Sarai"), launch, ref)
    assert moved["compound"] == "Sarai" and "parent_area_differs" in moved["notes"]
    # a seller's spelling with its own area is not held to Nawy's area for a same-named compound
    seller = entities.Pair("sarai|madinetmasr", "Sarai", "Madinet Masr", "القاهرة الجديدة", 1)
    kept = entities.validated(answer(0, compound="Badya", developer="Madinet Masr", reference=None), seller, ref)
    assert kept["compound"] == "Badya"

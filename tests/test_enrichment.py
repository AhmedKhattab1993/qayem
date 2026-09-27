"""The enrichment job never needs a live Codex call in these tests."""

import json
import subprocess
from threading import Event, Thread

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from qayem import enrichment
from qayem.db import get_engine, init_db
from qayem.models import Property, PropertyEnrichment
from qayem.sources.base import NormalizedListing
from qayem.upsert import upsert_listing


def task(pid=1, description="", missing=enrichment.INFERABLE_FIELDS, title="", price=None):
    return enrichment.Task(pid, title, description, tuple(missing), price)


def facts(**values):
    return [{"field": field, "value": str(value)} for field, value in values.items()]


def answer_file(command, listings):
    output = command[command.index("--output-last-message") + 1]
    with open(output, "w", encoding="utf-8") as file:
        json.dump({"listings": listings}, file)


def test_batch_invocation_uses_the_benchmarked_configuration(monkeypatch):
    tasks = [task(7, "شقة 120 متر", title="للبيع"), task(8, "فيلا")]
    captured = {}

    def fake_run(command, **kwargs):
        if command[:3] == ["codex", "features", "list"]:
            return subprocess.CompletedProcess(command, 0, "apps  stable  true\nsqlite  removed  true\n", "")
        captured["command"], captured["prompt"] = command, kwargs["input"]
        answer_file(command, [
            {"id": 7, "facts": facts(property_type="apartment")},
            {"id": 99, "facts": facts(property_type="villa")},  # not requested
        ])
        return subprocess.CompletedProcess(command, 0, "", "")

    enrichment._lean_flags.cache_clear()
    monkeypatch.setattr(enrichment.subprocess, "run", fake_run)
    assert enrichment.invoke_codex(tasks) == {7: [{"field": "property_type", "value": "apartment"}]}
    command = captured["command"]
    assert command[command.index("--model") + 1] == "gpt-6-sol"
    assert 'model_reasoning_effort="low"' in command
    assert f'model_instructions_file="{enrichment.SPEC_PATH}"' in command
    assert 'web_search="disabled"' in command
    assert command[command.index("--disable") + 1] == "apps" and "sqlite" not in command
    assert "--sandbox" in command and "read-only" in command
    payload = json.loads(captured["prompt"].split("\n", 1)[1])
    assert payload == [
        {"id": 7, "title": "للبيع", "description": "شقة 120 متر"},
        {"id": 8, "title": "", "description": "فيلا"},
    ]
    assert enrichment.SPEC_PATH.is_file()
    enrichment._lean_flags.cache_clear()


def test_timeout_is_retried_before_recording_failure(monkeypatch):
    calls = []

    def flaky_run(command, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        answer_file(command, [])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(enrichment, "_lean_flags", lambda: ())
    monkeypatch.setattr(enrichment.subprocess, "run", flaky_run)
    monkeypatch.setattr(enrichment.time, "sleep", lambda _: None)
    assert enrichment.invoke_codex([task()]) == {}
    assert calls == [600, 600]


def test_values_must_be_grounded_in_the_listing_text():
    values, notes = enrichment.validated_facts(facts(
        property_type="villa", finishing="finished", bathrooms=2, compound="Hyde Park",
    ), task(description="Penthouse, semi-finished, 2 bathrooms"))
    assert values == {"bathrooms": 2} and notes == []

    values, _ = enrichment.validated_facts(facts(
        property_type="apartment", delivery_status="ready_to_move", compound="هايد بارك",
    ), task(title="شقتك إستلام فوري", description="للبيع بهايد بارك التجمع الخامس"))
    assert values == {"property_type": "apartment", "delivery_status": "ready_to_move",
                      "compound": "هايد بارك"}

    generic, _ = enrichment.validated_facts(
        facts(compound="كمبوند ساكن وعايش"), task(description="داخل كمبوند ساكن وعايش"))
    assert generic == {}


def test_money_and_plan_terms_must_match_the_text():
    text = "مطلوب 2 مليون ونص والباقي على 5 سنين ونص، مقدم مليون و400 ألف"
    values, _ = enrichment.validated_facts(
        facts(price=2_500_000, installment_months=66, down_payment=1_400_000), task(description=text))
    assert values == {"price": 2_500_000.0, "installment_months": 66, "down_payment": 1_400_000.0}
    assert enrichment.validated_facts(
        facts(down_payment=10), task(description="10 ٪ مقدم"))[0] == {}
    assert enrichment.validated_facts(
        facts(installment_months=120), task(description="تقسيط على 8 سنوات"))[0] == {}


def test_down_payment_equal_to_listing_price_is_refused_and_noted():
    values, notes = enrichment.validated_facts(
        facts(down_payment=450_000), task(description="مقدم 450الف فقط", price=450_000))
    assert values == {}
    assert notes == ["price_is_down_payment"]


def test_multi_unit_ads_apply_nothing():
    values, notes = enrichment.validated_facts(
        facts(is_multi_unit="true", property_type="apartment"),
        task(description="شقق للبيع مساحات تبدأ من 120 متر"))
    assert values == {} and notes == ["multi_unit"]


def test_room_counts_need_their_own_number():
    one_bath = task(description="غرفتين وصالة وحمام ومطبخ")
    assert enrichment.validated_facts(facts(bathrooms=1, bedrooms=2), one_bath)[0] == {
        "bathrooms": 1, "bedrooms": 2}
    balcony = task(description="3 غرف نوم + مطبخ + حمام + 2 بلكونة")
    assert enrichment.validated_facts(facts(bathrooms=2), balcony)[0] == {}
    words = task(description="أربع غرف وثلاثة حمام")
    assert enrichment.validated_facts(facts(bathrooms=3), words)[0] == {"bathrooms": 3}


def test_only_missing_fields_are_applied():
    values, _ = enrichment.validated_facts(
        facts(property_type="apartment", area_m2=120),
        task(description="شقة 120 متر", missing=("area_m2",)))
    assert values == {"area_m2": 120.0}


SALE = dict(purpose="sale", currency="EGP", price=2_000_000)


def seed(engine, count, **columns):
    values = {"source": "opensooq", "description": "شقة 120 متر", **SALE, **columns}
    with Session(engine) as session:
        session.add_all(
            Property(source_listing_id=str(i), status="active", **values) for i in range(count)
        )
        session.commit()


def test_claims_a_batch_at_a_time_and_never_reinvokes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'qayem.db'}")
    init_db(engine)
    seed(engine, enrichment.BATCH_SIZE + 2)

    first = enrichment.claim_batch(engine)
    second = enrichment.claim_batch(engine)
    assert len(first) == enrichment.BATCH_SIZE and len(second) == 2
    assert enrichment.claim_batch(engine) == []

    monkeypatch.setattr(enrichment, "invoke_codex", lambda tasks: {
        t.property_id: facts(property_type="apartment", area_m2=120) for t in tasks
    })
    results = enrichment.process_batch(engine, second)
    assert [r.applied for r in results] == [2, 2]
    with Session(engine) as session:
        prop = session.get(Property, second[0].property_id)
        record = session.get(PropertyEnrichment, second[0].property_id)
        assert prop.property_type == "apartment" and prop.area_m2 == 120
        assert record.status == "done" and record.applied == {
            "property_type": "apartment", "area_m2": 120.0}
        assert (record.model, record.reasoning_effort, record.prompt_version) == ("gpt-6-sol", "low", "v2")
        assert record.flags is None and record.error is None
    assert enrichment.claim_batch(engine) == []


def test_unanswered_listings_are_asked_once_more_then_fail(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, 3)
    tasks = enrichment.claim_batch(engine)
    calls = []

    def partial(batch):
        calls.append([t.property_id for t in batch])
        return {batch[0].property_id: facts(property_type="apartment")}

    monkeypatch.setattr(enrichment, "invoke_codex", partial)
    results = enrichment.process_batch(engine, tasks)
    ids = [t.property_id for t in tasks]
    assert calls == [ids, ids[1:]]
    assert [r.status for r in results] == ["done", "done", "failed"]
    assert results[2].error == "Codex returned no answer for this listing"


def test_failures_are_retried_on_later_runs_up_to_the_attempt_cap(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, 3)
    monkeypatch.setattr(enrichment.shutil, "which", lambda _: "/usr/bin/codex")
    calls = []

    def fail(tasks):
        calls.append(len(tasks))
        raise RuntimeError("Codex exited with status 1")

    monkeypatch.setattr(enrichment, "invoke_codex", fail)
    for attempt in range(1, enrichment.MAX_ATTEMPTS + 1):
        results = enrichment.run_batches(engine, 0)
        assert [r.status for r in results] == ["failed"] * 3  # once per run, never twice
    assert calls == [3] * enrichment.MAX_ATTEMPTS
    assert enrichment.claim_batch(engine) == []  # attempts exhausted
    with Session(engine) as session:
        assert {r.attempts for r in session.query(PropertyEnrichment)} == {enrichment.MAX_ATTEMPTS}

    # an operator can still force a retry
    monkeypatch.setattr(enrichment, "invoke_codex", lambda tasks: {
        t.property_id: facts(property_type="apartment") for t in tasks
    })
    retried = enrichment.run_batches(engine, 0, retry_failed=True)
    assert [r.applied for r in retried] == [1, 1, 1]
    assert enrichment.run_batches(engine, 0, retry_failed=True) == []


def test_circuit_breaker_stops_a_run_after_consecutive_failed_batches(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, enrichment.BATCH_SIZE * 5)
    monkeypatch.setattr(enrichment.shutil, "which", lambda _: "/usr/bin/codex")

    def fail(_tasks):
        raise RuntimeError("Codex exited with status 1")

    monkeypatch.setattr(enrichment, "invoke_codex", fail)
    reasons = []
    results = enrichment.run_batches(engine, 0, workers=1, on_stop=reasons.append)
    assert len(results) == enrichment.BATCH_SIZE * enrichment.CIRCUIT_BREAKER
    assert reasons == ["2 batches in a row failed: Codex exited with status 1"]


def test_time_budget_stops_new_batches(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, enrichment.BATCH_SIZE * 2)
    monkeypatch.setattr(enrichment.shutil, "which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(enrichment, "invoke_codex", lambda tasks: {})
    reasons = []
    assert enrichment.run_batches(engine, 0, deadline=0, on_stop=reasons.append) == []
    assert reasons == ["time budget reached"]


def test_abandoned_claims_are_taken_again(tmp_path):
    from datetime import timedelta
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, 2)
    assert len(enrichment.claim_batch(engine)) == 2
    assert enrichment.claim_batch(engine) == []
    with Session(engine) as session:
        record = session.get(PropertyEnrichment, 1)
        record.claimed_at = enrichment.utcnow() - enrichment.STALE_CLAIM - timedelta(minutes=1)
        session.commit()
    assert [t.property_id for t in enrichment.claim_batch(engine)] == [1]
    with Session(engine) as session:
        assert session.get(PropertyEnrichment, 1).attempts == 2


def test_health_reports_backlog_and_failures(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, 12)
    assert enrichment.enrichment_health(engine)["state"] == "stale"  # waiting, never enriched
    monkeypatch.setattr(enrichment.shutil, "which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(enrichment, "invoke_codex", lambda tasks: {})  # every listing unanswered
    enrichment.run_batches(engine, 0)
    health = enrichment.enrichment_health(engine)
    assert health["state"] == "failing" and health["failed_24h"] == 12
    assert health["detail"].startswith("12 of 12 listings failed")


def test_source_updates_keep_inference_only_for_unchanged_text(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'qayem.db'}")
    init_db(engine)

    def listing(price, description, title="Listing"):
        return NormalizedListing(
            source_listing_id="A1", title=title, description=description,
            price=price, property_type=None, purpose="sale", currency="EGP",
        )

    with Session(engine) as session:
        upsert_listing(session, "opensooq", listing(1_000_000, "شقة 120 متر"))
        session.commit()
    tasks = enrichment.claim_batch(engine)
    assert len(tasks) == 1
    monkeypatch.setattr(enrichment, "invoke_codex", lambda batch: {
        t.property_id: facts(property_type="apartment") for t in batch
    })
    assert enrichment.process_batch(engine, tasks)[0].applied == 1

    with Session(engine) as session:
        upsert_listing(session, "opensooq", listing(900_000, "شقة 120 متر"))
        session.commit()
        assert session.execute(select(Property.property_type)).scalar_one() == "apartment"

    with Session(engine) as session:
        upsert_listing(session, "opensooq", listing(800_000, "شقة 120 متر", title="Changed"))
        session.commit()
        assert session.execute(select(Property.property_type)).scalar_one() is None


def test_records_made_before_titles_were_sent_still_reapply(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qayem.db'}")
    init_db(engine)
    listing = NormalizedListing(source_listing_id="A1", title="T", description="شقة", price=1.0)
    with Session(engine) as session:
        upsert_listing(session, "opensooq", listing)
        session.flush()
        prop = session.execute(select(Property)).scalar_one()
        prop.property_type = "apartment"
        session.add(PropertyEnrichment(
            property_id=prop.id, status="done", done=True, claimed_at=prop.first_seen_at,
            description_hash=enrichment.description_hash("شقة"), model="gpt-6-luna",
            reasoning_effort="low", applied={"property_type": "apartment"},
        ))
        session.commit()
        upsert_listing(session, "opensooq", NormalizedListing(
            source_listing_id="A1", title="T", description="شقة", price=2.0))
        session.commit()
        assert session.execute(select(Property.property_type)).scalar_one() == "apartment"


def test_scheduler_runs_one_batch_then_resumes(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, enrichment.BATCH_SIZE + 2)
    monkeypatch.setattr(enrichment.shutil, "which", lambda command: "/usr/bin/codex")
    monkeypatch.setattr(enrichment, "invoke_codex", lambda tasks: {
        t.property_id: facts(property_type="apartment") for t in tasks
    })
    assert len(enrichment.run_batches(engine, 1)) == enrichment.BATCH_SIZE
    assert len(enrichment.run_batches(engine, 1)) == 2
    assert enrichment.run_batches(engine, 1) == []
    with Session(engine) as session:
        assert session.query(PropertyEnrichment).filter_by(done=True).count() == enrichment.BATCH_SIZE + 2
        assert session.query(Property).filter_by(property_type="apartment").count() == enrichment.BATCH_SIZE + 2


def test_slow_batch_does_not_hold_the_next_one(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, enrichment.BATCH_SIZE * 2 + 1)
    gate, later_started = Event(), Event()
    results = []

    def fake_invoke(tasks):
        if tasks[0].property_id == 1:
            gate.wait(timeout=5)
        else:
            later_started.set()
        return {}

    monkeypatch.setattr(enrichment.shutil, "which", lambda command: "/usr/bin/codex")
    monkeypatch.setattr(enrichment, "invoke_codex", fake_invoke)
    worker = Thread(target=lambda: results.extend(enrichment.run_batches(engine, 0, workers=2)))
    worker.start()
    try:
        assert later_started.wait(timeout=3)
    finally:
        gate.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert len(results) == enrichment.BATCH_SIZE * 2 + 1


def test_only_listings_the_website_could_show_are_sent(tmp_path):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    rows = {
        "keep": dict(source="opensooq", description="شقة 120 متر استلام فوري"),
        "templated": dict(source="nawy", description="Apartment for sale in X in New Cairo by Y."),
        "rent": dict(source="opensooq", description="شقة 120 متر", purpose="rent"),
        "usd": dict(source="opensooq", description="شقة 120 متر", currency="USD"),
        "cheap": dict(source="opensooq", description="شقة 120 متر", price=5_000),
        "shop": dict(source="opensooq", description="محل 120 متر", property_type="shop"),
        "only_rooms_missing": dict(
            source="opensooq", description="3 غرف", property_type="apartment", area_m2=120,
            is_resale=True, finishing="lux", delivery_status="ready_to_move", compound="X",
            down_payment=100_000, installment_months=60),
        "no_signal": dict(source="opensooq", description="للتواصل واتساب فقط",
                          property_type="apartment", area_m2=90),
    }
    with Session(engine) as session:
        for key, columns in rows.items():
            session.add(Property(source_listing_id=key, status="active", **{**SALE, **columns}))
        session.commit()
    tasks = enrichment.claim_batch(engine, dry_run=True)
    with Session(engine) as session:
        assert [session.get(Property, t.property_id).source_listing_id for t in tasks] == ["keep"]
    assert enrichment.count_eligible(engine) == 1


def test_newest_listings_come_first_and_since_limits(tmp_path):
    from datetime import datetime, timezone
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    with Session(engine) as session:
        for day in (1, 3, 2):
            session.add(Property(
                source="opensooq", source_listing_id=str(day), status="active",
                description="شقة 120 متر", first_seen_at=datetime(2026, 9, day, tzinfo=timezone.utc), **SALE))
        session.commit()
    order = [t.property_id for t in enrichment.claim_batch(engine, dry_run=True)]
    assert order == [2, 3, 1]  # ids of days 3, 2, 1
    since = datetime(2026, 9, 2, tzinfo=timezone.utc)
    assert [t.property_id for t in enrichment.claim_batch(engine, dry_run=True, since=since)] == [2, 3]


def test_revoke_undoes_old_prompt_fills_but_keeps_current_ones(tmp_path):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, 3, property_type="apartment", finishing="lux")
    with Session(engine) as session:
        now = enrichment.utcnow()
        session.add_all([
            PropertyEnrichment(property_id=1, status="done", done=True, claimed_at=now,
                               description_hash="x", model="gpt-6-luna", reasoning_effort="low",
                               applied={"property_type": "apartment", "finishing": "super_lux"}),
            PropertyEnrichment(property_id=2, status="done", done=True, claimed_at=now,
                               description_hash="x", model="gpt-6-sol", reasoning_effort="low",
                               prompt_version=enrichment.PROMPT_VERSION,
                               applied={"property_type": "apartment"}),
        ])
        session.commit()
    preview = enrichment.revoke_outdated(engine, dry_run=True)
    assert preview == [{"property_id": 1, "field": "property_type", "value": "apartment",
                        "model": "gpt-6-luna"}]
    assert enrichment.revoke_outdated(engine) == preview
    with Session(engine) as session:
        assert session.get(Property, 1).property_type is None
        assert session.get(Property, 1).finishing == "lux"  # changed since: not the old fill
        assert session.get(Property, 2).property_type == "apartment"
        assert session.get(PropertyEnrichment, 1) is None
        assert session.get(PropertyEnrichment, 2) is not None
    assert enrichment.revoke_outdated(engine) == []


def test_flags_are_stored_with_a_readable_note(tmp_path, monkeypatch):
    engine = get_engine(tmp_path / "qayem.db")
    init_db(engine)
    seed(engine, 1, description="مقدم 450الف فقط", price=450_000)
    tasks = enrichment.claim_batch(engine)
    monkeypatch.setattr(enrichment, "invoke_codex", lambda batch: {
        t.property_id: facts(down_payment=450_000) for t in batch})
    enrichment.process_batch(engine, tasks)
    with Session(engine) as session:
        record = session.get(PropertyEnrichment, tasks[0].property_id)
        assert record.flags == ["price_is_down_payment"]
        assert record.error == "Listing price equals the stated down payment"

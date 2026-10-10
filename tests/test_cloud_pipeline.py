"""Recovery and interrupted cloud publication use disposable databases only."""
import json
from pathlib import Path
import sqlite3

import pytest

from qayem import cloud_pipeline as pipeline
from qayem.cloud_export import export_sql
from test_web import database


def test_checkpoint_includes_committed_wal_history_and_restores_it(tmp_path):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE properties(id INTEGER PRIMARY KEY, description TEXT)")
        db.execute("CREATE TABLE history(id INTEGER, price INTEGER)")
        db.execute("INSERT INTO properties VALUES (1,'private canonical text')")
        db.execute("INSERT INTO history VALUES (1,100)")
        db.commit()
        packed, metadata = pipeline.make_checkpoint(source, tmp_path / "packed")
    restored = tmp_path / "restored.db"
    pipeline.restore_checkpoint(packed, metadata, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT price FROM history").fetchone()[0] == 100
        assert db.execute("SELECT description FROM properties").fetchone()[0] == "private canonical text"


def test_corrupt_checkpoint_never_replaces_the_database(tmp_path):
    source = tmp_path / "live.db"
    source.write_bytes(b"do not replace this")
    packed = tmp_path / "bad.gz"
    packed.write_bytes(b"not a valid checkpoint")
    with pytest.raises(RuntimeError, match="checksum"):
        pipeline.restore_checkpoint(packed, {"compressed_sha256": "0" * 64}, source)
    assert source.read_bytes() == b"do not replace this"


def test_unchanged_checkpoint_reuses_compression_and_only_uploads_changed_logs(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE properties(id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO properties VALUES (1)")

    class Bridge:
        def __init__(self):
            self.objects, self.pointers, self.uploads = {}, [], []

        def request(self, method, path, *, file):
            assert method == "PUT"
            self.objects[path] = file.read_bytes()
            self.uploads.append(path)

        def json(self, method, path, body):
            assert (method, path) == ("PUT", "/canonical")
            self.pointers.append(body)

    bridge = Bridge()
    job = pipeline.Pipeline("run-1", bridge=bridge, database=source)
    job.log.write_text("crawl complete\n")
    job.checkpoint()
    first_pointer = bridge.pointers[0]
    first_objects = bridge.objects.copy()
    with monkeypatch.context() as patch:
        patch.setattr(pipeline.gzip, "open", lambda *_args, **_kwargs: pytest.fail("unchanged DB recompressed"))
        job.checkpoint()
        assert bridge.objects == first_objects
        assert bridge.pointers == [first_pointer]
        assert len(bridge.uploads) == 2
        assert job.checkpoint_slot == 1
        job.log.write_text("crawl complete\nno AI work pending\n")
        job.checkpoint()
        assert bridge.objects["/objects/canonical/run-1/0.db.gz"] == first_objects["/objects/canonical/run-1/0.db.gz"]
        assert bridge.objects["/objects/runs/run-1/pipeline.log"] != first_objects["/objects/runs/run-1/pipeline.log"]
        assert bridge.pointers == [first_pointer]
        assert len(bridge.uploads) == 3
        assert bridge.uploads[-1] == "/objects/runs/run-1/pipeline.log"

    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO properties VALUES (2)")
    job.checkpoint()
    assert len(bridge.pointers) == 2
    assert bridge.pointers[-1]["key"] == "canonical/run-1/1.db.gz"
    assert bridge.pointers[-1]["sha256"] != first_pointer["sha256"]
    assert job.checkpoint_slot == 0
    restored = tmp_path / "restored.db"
    pipeline.restore_checkpoint(job.directory / "checkpoint.db.gz", bridge.pointers[-1], restored)
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT count(*) FROM properties").fetchone()[0] == 2


def test_failed_checkpoint_pointer_is_retried_before_it_can_be_skipped(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE properties(id INTEGER PRIMARY KEY)")

    class Bridge:
        def __init__(self):
            self.uploads, self.pointer_attempts = [], 0

        def request(self, method, path, *, file):
            self.uploads.append(path)

        def json(self, method, path, body):
            self.pointer_attempts += 1
            if self.pointer_attempts == 1:
                raise RuntimeError("R2 temporarily unavailable")

    bridge = Bridge()
    job = pipeline.Pipeline("run-1", bridge=bridge, database=source)
    job.log.touch()
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        job.checkpoint()
    assert job.checkpoint_metadata is None and job.checkpoint_slot == 0
    job.checkpoint()
    assert bridge.uploads.count("/objects/canonical/run-1/0.db.gz") == 2
    assert bridge.pointer_attempts == 2 and job.checkpoint_slot == 1
    job.checkpoint()
    assert bridge.pointer_attempts == 2


def test_staging_export_is_bounded_and_cannot_activate_a_partial_version(database, tmp_path):
    sql = tmp_path / "catalog.sql"
    export_sql(database, sql, version="first")
    public = tmp_path / "public.db"
    with sqlite3.connect(public) as db:
        db.executescript((Path(__file__).parents[1] / "cloudflare/schema.sql").read_text())
        db.executescript(sql.read_text())
        export_sql(database, sql, version="second")
        batches = list(pipeline.stage_batches(sql, "second"))
        for batch in batches:
            assert len(batch) <= 40
            assert len(json.dumps(batch, ensure_ascii=False).encode()) <= pipeline.MAX_BATCH_BYTES + 1000
            for statement in batch:
                assert statement.startswith("INSERT OR REPLACE INTO") and " VALUES ('second'," in statement
                db.execute(statement)
        assert db.execute("SELECT value FROM state WHERE key='active'").fetchone()[0] == "first"
        assert db.execute("SELECT ready FROM datasets WHERE version='second'").fetchone()[0] == 0
        # Delivery retries are idempotent and keep the preceding published snapshot available.
        for statement in batches[-1]:
            db.execute(statement)
        assert db.execute("SELECT value FROM state WHERE key='active'").fetchone()[0] == "first"


def test_health_failure_preserves_private_history_without_publishing(database, tmp_path, monkeypatch):
    class Bridge:
        def __init__(self):
            self.packed, self.metadata = pipeline.make_checkpoint(database, tmp_path / "seed")
            self.calls = []

        def json(self, method, path, body=None):
            self.calls.append((method, path, body))
            return self.metadata | {"key": "canonical/seed/123.db.gz"} if path == "/canonical" and method == "GET" else {}

        def download(self, _key, path):
            path.write_bytes(self.packed.read_bytes())

        def request(self, method, path, **kwargs):
            self.calls.append((method, path, None))

    bridge = Bridge()
    target = tmp_path / "cloud.db"
    job = pipeline.Pipeline("run-1", bridge=bridge, database=target)
    monkeypatch.setattr(pipeline, "configure_pi", lambda: None)
    commands = []

    def command(stage, args, budget):
        commands.append(stage)
        job.log.touch()
        job.checkpoint()
        return 1 if stage == "health" else 0

    monkeypatch.setattr(job, "command", command)
    job.run()
    assert commands == ["crawl", "entities", "health"]
    assert job.status["status"] == "failed"
    assert "previous catalogue retained" in job.status["error"]
    assert not any("/publish/" in path for _, path, _ in bridge.calls)
    assert any(method == "PUT" and path == "/canonical" for method, path, _ in bridge.calls)
    assert any(path == "/run-status" for _, path, _ in bridge.calls)
    with sqlite3.connect(target) as cloud, sqlite3.connect(database) as local:
        assert cloud.execute("SELECT count(*) FROM properties").fetchone() == local.execute("SELECT count(*) FROM properties").fetchone()

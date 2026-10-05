"""Staging isolation and development-cache recovery with disposable cloud snapshots."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from qayem.cloud_development import deployment_binding, projection_fingerprint, pull_snapshot
from qayem.cloud_pipeline import make_checkpoint
from test_cloudflare import clients, database


@pytest.fixture()
def config(tmp_path):
    (tmp_path / "cloudflare").mkdir()
    path = tmp_path / "cloudflare/wrangler.jsonc"
    data = {"d1_databases": [{"binding": "DB", "database_id": "production", "database_name": "qayem-public"}],
        "env": {"staging": {"routes": [], "triggers": {"crons": []},
            "d1_databases": [{"binding": "DB", "database_id": "staging", "database_name": "qayem-staging"}]}}}
    path.write_text(json.dumps(data))
    (tmp_path / "cloudflare/schema.sql").write_text("schema")
    return tmp_path, path, data


@pytest.mark.parametrize("mistake", ["shared-db", "domain", "cron", "inherited-db"])
def test_staging_refuses_production_bindings_or_scheduled_work(config, mistake):
    root, path, data = config
    assert deployment_binding(root, "staging")["database_id"] == "staging"
    stage = data["env"]["staging"]
    if mistake == "shared-db":
        stage["d1_databases"][0]["database_id"] = "production"
    elif mistake == "domain":
        stage["routes"] = [{"pattern": "qayem.ai", "custom_domain": True}]
    elif mistake == "cron":
        stage["triggers"]["crons"] = ["0 0 * * *"]
    else:
        del stage["d1_databases"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        deployment_binding(root, "staging")


@pytest.fixture()
def cloud(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE properties(id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO properties VALUES (1)")
    packed, metadata = make_checkpoint(source, tmp_path / "cloud")
    pointer = metadata | {"run_id": "nightly-2026-10-05", "key": "canonical/nightly-2026-10-05/0.db.gz"}
    requests = []

    def fetch(root, *args):
        assert args[:3] == ("r2", "object", "get") and "--remote" in args
        key, destination = args[3], Path(args[args.index("--file") + 1])
        requests.append(key)
        if key == "qayem-history/canonical/current.json":
            destination.write_text(json.dumps(pointer))
        else:
            assert key == "qayem-history/" + pointer["key"]
            destination.write_bytes(packed.read_bytes())
    return tmp_path, packed, pointer, requests, fetch


def test_repeated_pull_skips_download_and_repairs_local_damage_from_cached_checkpoint(cloud):
    root, _, _, requests, fetch = cloud
    first = pull_snapshot(root, run=fetch)
    database = Path(first["database"])
    before = database.stat().st_mtime_ns
    assert not first["cached"] and database.stat().st_mode & 0o777 == 0o600
    assert pull_snapshot(root, run=fetch)["cached"]
    assert database.stat().st_mtime_ns == before
    database.write_bytes(b"local database damaged")
    assert not pull_snapshot(root, run=fetch)["cached"]
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT id FROM properties").fetchone() == (1,)
    assert requests.count("qayem-history/canonical/nightly-2026-10-05/0.db.gz") == 1


def test_invalid_new_cloud_checkpoint_preserves_previous_development_copy(cloud):
    root, packed, pointer, _, fetch = cloud
    database = Path(pull_snapshot(root, run=fetch)["database"])
    original = database.read_bytes()
    pointer["sha256"] = "0" * 64
    packed.write_bytes(b"damaged cloud checkpoint")
    with pytest.raises(RuntimeError, match="checksum"):
        pull_snapshot(root, run=fetch)
    assert database.read_bytes() == original


def test_projection_cache_expires_for_data_comparison_code_or_filter_changes(config, monkeypatch):
    root, _, _ = config
    monkeypatch.delenv("QAYEM_SOURCES", raising=False)
    monkeypatch.delenv("QAYEM_BENCHMARK_SOURCES", raising=False)
    source = root / "src/qayem"
    source.mkdir(parents=True)
    code = source / "valuation.py"
    code.write_text("original")
    (root / "cloudflare/schema.sql").write_text("schema")
    first = projection_fingerprint(root, "first")
    assert first == projection_fingerprint(root, "first")
    assert first != projection_fingerprint(root, "second")
    (source / "cloud_web.py").write_text("API-only change")
    assert first == projection_fingerprint(root, "first")
    code.write_text("updated")
    assert first != projection_fingerprint(root, "first")
    code.write_text("original")
    monkeypatch.setenv("QAYEM_SOURCES", "all")
    assert first != projection_fingerprint(root, "first")


def test_refresh_skips_writes_for_same_projection_but_republishes_if_remote_version_changed(cloud, config, monkeypatch):
    root, _, _, _, fetch = cloud
    script = Path(__file__).resolve().parents[1] / "scripts/cloud-dev.py"
    spec = importlib.util.spec_from_file_location("cloud_dev", script)
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)
    monkeypatch.setattr(dev, "ROOT", root)
    monkeypatch.setattr(dev, "ARTIFACTS", root / ".artifacts/development")
    monkeypatch.setattr(dev, "pull_snapshot", lambda location: pull_snapshot(location, run=fetch))
    version, publications = ["empty"], []

    def publish(command, **kwargs):
        assert command[command.index("--env") + 1] == "staging"
        assert Path(command[command.index("--database") + 1]) == root / ".artifacts/development/qayem.db"
        publications.append(command)
        version[0] = f"published-{len(publications)}"

    monkeypatch.setattr(dev.subprocess, "run", publish)
    monkeypatch.setattr(dev, "staging_dataset", lambda: {"version": version[0]})
    assert not dev.refresh()["publication_skipped"]
    assert dev.refresh()["publication_skipped"] and len(publications) == 1
    version[0] = "changed-by-another-publisher"
    assert not dev.refresh()["publication_skipped"] and len(publications) == 2


def test_staging_api_identifies_itself_and_discourages_indexing(clients):
    _, cloud, _, _ = clients
    assert "x-qayem-environment" not in cloud.get("/api/health").headers

    async def staging(scope, receive, send):
        scope["env"] = SimpleNamespace(QAYEM_ENVIRONMENT="staging")
        await cloud.app(scope, receive, send)

    with TestClient(staging) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.headers["X-Qayem-Environment"] == "staging"
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert response.headers["Cache-Control"] == "no-store"

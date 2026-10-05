"""Isolated development copies of the cloud database, with no ingestion or AI calls."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import subprocess

from .cloud_pipeline import digest, restore_checkpoint


def deployment_binding(root: Path, environment: str) -> dict:
    config = json.loads((root / "cloudflare/wrangler.jsonc").read_text())
    production = next(db for db in config["d1_databases"] if db["binding"] == "DB")
    if environment == "production":
        return production
    if environment != "staging":
        raise ValueError("Unknown deployment environment")
    stage = config["env"]["staging"]
    databases = stage.get("d1_databases", [])
    if stage.get("routes") != [] or stage.get("triggers", {}).get("crons") != []:
        raise ValueError("Staging must have no production routes or scheduled updates")
    if len(databases) != 1 or databases[0].get("binding") != "DB":
        raise ValueError("Staging requires exactly one explicit D1 binding")
    database = databases[0]
    if database.get("database_name") != "qayem-staging" or not database.get("database_id") \
            or database["database_id"] == production["database_id"]:
        raise ValueError("Staging must use its own database")
    return database


def wrangler(root: Path, *arguments: str):
    executable = root / "cloudflare/updater/node_modules/.bin/wrangler"
    return subprocess.run([str(executable), *arguments], cwd=root / "cloudflare", check=True)


def pull_snapshot(root: Path, *, run=wrangler) -> dict:
    """Restore a verified development copy; identical checkpoints avoid another download."""
    directory = root / ".artifacts/development"
    directory.mkdir(parents=True, exist_ok=True)
    pointer = directory / "current.json"
    run(root, "r2", "object", "get", "qayem-history/canonical/current.json", "--remote", "--file", str(pointer))
    metadata = json.loads(pointer.read_text())
    run_id = metadata.get("run_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id) or \
            not re.fullmatch(rf"canonical/{re.escape(run_id)}/[01]\.db\.gz", metadata.get("key", "")):
        raise ValueError("Cloud checkpoint path is invalid")
    for name in ("sha256", "compressed_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", metadata.get(name, "")):
            raise ValueError("Cloud checkpoint checksum is invalid")
    for name in ("bytes", "compressed_bytes"):
        if type(metadata.get(name)) is not int or metadata[name] <= 0:
            raise ValueError("Cloud checkpoint size is invalid")
    database = directory / "qayem.db"
    cached = database.exists() and database.stat().st_size == metadata["bytes"] and digest(database) == metadata["sha256"]
    if not cached:
        packed = directory / "checkpoint.db.gz"
        if not packed.exists() or packed.stat().st_size != metadata["compressed_bytes"] \
                or digest(packed) != metadata["compressed_sha256"]:
            run(root, "r2", "object", "get", "qayem-history/" + metadata["key"], "--remote", "--file", str(packed))
        # Verify in a fresh location before replacing the preceding development copy.
        replacement = directory / "next.db"
        restore_checkpoint(packed, metadata, replacement)
        replacement.chmod(0o600)
        replacement.replace(database)
    return {"database": str(database), "run_id": run_id, "sha256": metadata["sha256"], "cached": cached}


def projection_fingerprint(root: Path, snapshot_sha256: str) -> str:
    """Reuse a projection until its data, comparison/export source or filters change.

    The comparison date comes from the snapshot's last-seen data, not today's wall clock.
    """
    checksum = hashlib.sha256()
    checksum.update(json.dumps({"snapshot": snapshot_sha256,
        "sources": os.environ.get("QAYEM_SOURCES", ""),
        "benchmarks": os.environ.get("QAYEM_BENCHMARK_SOURCES", "")}, sort_keys=True).encode())
    modules = {"cloud_export.py", "website_data.py", "valuation.py", "config.py"}
    files = sorted(path for path in (root / "src/qayem").glob("*.py") if path.name in modules)
    files.append(root / "cloudflare/schema.sql")
    for path in files:
        checksum.update(str(path.relative_to(root)).encode())
        checksum.update(path.read_bytes())
    return checksum.hexdigest()

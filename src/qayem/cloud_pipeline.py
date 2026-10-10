"""Container-only ingestion. Private R2 checkpoints; verified D1 publication via a Worker binding.

The bridge is an outbound-only virtual hostname, not a public administration API.
No Cloudflare account token or unrelated Pi credentials enter the container image.
"""
from __future__ import annotations

from contextlib import closing
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

from .cloud_export import export_sql
from .config import crawled_sources, db_path

RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
MAX_BATCH_BYTES = 300_000


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def make_checkpoint(database: Path, directory: Path, *, previous: dict | None = None) -> tuple[Path, dict]:
    """Backup API includes committed WAL rows without interrupting the crawler."""
    directory.mkdir(parents=True, exist_ok=True)
    backup = directory / "checkpoint.db"
    pending = directory / "checkpoint.pending.db"
    packed = directory / "checkpoint.db.gz"
    # A fresh destination keeps SQLite's backup header stable. Reusing an existing
    # destination changes its transaction counter even when the source is identical.
    pending.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True, timeout=30)) as source:
            with closing(sqlite3.connect(pending)) as target:
                source.backup(target, pages=256, sleep=0.1)
                if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("Database checkpoint failed its integrity check")
        pending.replace(backup)
    finally:
        pending.unlink(missing_ok=True)
    checksum = digest(backup)
    size = backup.stat().st_size
    if previous and checksum == previous["sha256"] and size == previous["bytes"] and packed.exists() \
            and packed.stat().st_size == previous["compressed_bytes"]:
        return packed, previous
    with backup.open("rb") as source, gzip.open(packed, "wb", compresslevel=1) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    return packed, {"sha256": checksum, "compressed_sha256": digest(packed),
                    "bytes": size, "compressed_bytes": packed.stat().st_size,
                    "saved_at": datetime.now(timezone.utc).isoformat()}


def restore_checkpoint(packed: Path, metadata: dict, database: Path) -> None:
    if digest(packed) != metadata["compressed_sha256"]:
        raise RuntimeError("Cloud checkpoint checksum mismatch")
    restored = database.with_suffix(".restoring")
    try:
        with gzip.open(packed, "rb") as source, restored.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        if restored.stat().st_size != metadata["bytes"] or digest(restored) != metadata["sha256"]:
            raise RuntimeError("Restored database checksum mismatch")
        with sqlite3.connect(f"file:{restored.resolve()}?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("Restored database failed its integrity check")
            connection.execute("SELECT id FROM properties LIMIT 1").fetchall()
        restored.replace(database)
    finally:
        restored.unlink(missing_ok=True)


def stage_batches(sql: Path, version: str):
    """Send bounded, replayable inserts. Activation belongs to the coordinator."""
    if not RUN_ID.fullmatch(version):
        raise ValueError("Invalid publication version")
    statements, size = [], 0
    with sql.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith("INSERT OR REPLACE INTO "):
                continue
            encoded_size = len(json.dumps(line, ensure_ascii=False).encode())
            if encoded_size > MAX_BATCH_BYTES:
                raise ValueError("Publication statement exceeds the batch budget")
            if statements and (size + encoded_size > MAX_BATCH_BYTES or len(statements) >= 40):
                yield statements
                statements, size = [], 0
            statements.append(line.strip())
            size += encoded_size + 1
    if statements:
        yield statements


class Bridge:
    def __init__(self, base: str | None = None):
        self.base = base or os.environ.get("QAYEM_CLOUD_BRIDGE", "http://qayem.internal")

    def request(self, method: str, path: str, *, json_body=None, file: Path | None = None):
        # Only retry safe/idempotent operations. Replay inserts never activates a partial dataset.
        for attempt in range(4):
            try:
                with httpx.Client(timeout=180) as client:
                    if file:
                        with file.open("rb") as source:
                            response = client.request(method, self.base + path, content=source,
                                headers={"Content-Length": str(file.stat().st_size),
                                         "X-Content-SHA256": digest(file)})
                    else:
                        response = client.request(method, self.base + path, json=json_body)
                    if response.status_code < 500 and response.status_code != 429:
                        response.raise_for_status()
                        return response
            except httpx.TransportError:
                pass
            if attempt < 3:
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Cloud bridge operation failed: {method} {path.split('?')[0]}")

    def json(self, method: str, path: str, body=None):
        return self.request(method, path, json_body=body).json()

    def download(self, key: str, path: Path):
        # Stream the compressed database instead of holding its contents in memory.
        with httpx.Client(timeout=180) as client, client.stream("GET", self.base + "/objects/" + key) as response:
            response.raise_for_status()
            with path.open("wb") as target:
                for chunk in response.iter_bytes(1024 * 1024):
                    target.write(chunk)


class Pipeline:
    def __init__(self, run_id: str, *, bridge=None, database=None):
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run ID")
        self.run_id = run_id
        self.bridge = bridge or Bridge()
        self.database = database or db_path()
        self.directory = self.database.parent / "runs" / run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log = self.directory / "pipeline.log"
        self.status = {"run_id": run_id, "status": "running", "stage": "restore",
                       "started_at": datetime.now(timezone.utc).isoformat()}
        self.checkpoint_lock = threading.Lock()
        self.stop_checkpoints = threading.Event()
        self.checkpoint_errors = 0
        self.checkpoint_slot = 0
        self.checkpoint_metadata = None
        self.checkpoint_log_hash = None

    def checkpoint(self):
        with self.checkpoint_lock:
            packed, metadata = make_checkpoint(self.database, self.directory, previous=self.checkpoint_metadata)
            # Alternate slots so the current pointer always names a complete object.
            # Two checkpoints per run bound storage growth, even during long crawls.
            if not self.checkpoint_metadata or metadata["sha256"] != self.checkpoint_metadata["sha256"]:
                key = f"canonical/{self.run_id}/{self.checkpoint_slot}.db.gz"
                self.bridge.request("PUT", "/objects/" + key, file=packed)
                self.bridge.json("PUT", "/canonical", metadata | {"key": key, "run_id": self.run_id})
                self.checkpoint_metadata = metadata
                self.checkpoint_slot = 1 - self.checkpoint_slot
            frozen_log = self.directory / "checkpoint.log"
            shutil.copyfile(self.log, frozen_log)
            log_hash = digest(frozen_log)
            if log_hash != self.checkpoint_log_hash:
                self.bridge.request("PUT", f"/objects/runs/{self.run_id}/pipeline.log", file=frozen_log)
                self.checkpoint_log_hash = log_hash
            self.status["checkpoint_at"] = self.checkpoint_metadata["saved_at"]
            self.checkpoint_errors = 0

    def checkpoint_loop(self):
        while not self.stop_checkpoints.wait(300):
            try:
                self.checkpoint()
            except Exception:
                self.checkpoint_errors += 1
                self.status["checkpoint_warning"] = "Cloud checkpoint failed; will retry"

    def command(self, stage: str, arguments: list[str], budget_seconds: int):
        self.status["stage"] = stage
        with self.log.open("a", encoding="utf-8") as output:
            output.write(f"\n== {stage} {datetime.now(timezone.utc).isoformat()}\n")
            output.flush()
            process = subprocess.Popen([sys.executable, "-m", "qayem.cli", *arguments],
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=budget_seconds)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise RuntimeError(f"{stage} exceeded its time budget") from None
        self.checkpoint()
        return code

    def run(self):
        thread = None
        try:
            metadata = self.bridge.json("GET", "/canonical")
            if metadata.get("run_id") == self.run_id:
                self.checkpoint_slot = 1 - int(Path(metadata["key"]).name.split(".")[0])
            packed = self.directory / "restore.db.gz"
            self.bridge.download(metadata["key"], packed)
            restore_checkpoint(packed, metadata, self.database)
            packed.unlink()
            self.log.touch()
            configure_pi()
            thread = threading.Thread(target=self.checkpoint_loop, daemon=True)
            thread.start()
            if self.command("crawl", ["crawl"], 4 * 3600):
                raise RuntimeError("Crawler failed")
            self.command("entities", ["resolve-entities", "--workers", "4", "--max-minutes", "30"], 45 * 60)
            if self.command("health", ["health", "--write", str(self.directory / "health.json")], 120):
                raise RuntimeError("Source health needs attention; previous catalogue retained")
            self.status["stage"] = "publish"
            # Freeze the canonical state in R2 before making any public version active.
            self.stop_checkpoints.set()
            if thread:
                thread.join(timeout=240)
                if thread.is_alive():
                    raise RuntimeError("Checkpoint did not finish before publication")
            self.checkpoint()
            sql = self.directory / "catalog.sql"
            manifest = export_sql(self.directory / "checkpoint.db", sql,
                                  sources=crawled_sources(), version=self.run_id)
            if not manifest["units"]:
                raise RuntimeError("Empty catalogue cannot be published")
            for index, batch in enumerate(stage_batches(sql, self.run_id)):
                self.bridge.json("POST", "/publish/batch", {"version": self.run_id, "index": index,
                                                            "statements": batch})
                self.status["publication_batch"] = index
            result = self.bridge.json("POST", "/publish/activate", manifest)
            if result.get("version") != self.run_id or result.get("ready") != 1:
                raise RuntimeError("D1 did not verify the complete catalogue")
            self.status.update(status="complete", stage="complete", publication=result)
        except Exception as exc:
            # Public status never contains raw request/provider errors or secret values.
            self.status.update(status="failed", error=str(exc) if isinstance(exc, RuntimeError)
                               else f"Pipeline failed ({type(exc).__name__}); inspect the private run log")
            if self.database.exists() and self.log.exists():
                try:
                    self.checkpoint()
                except Exception:
                    self.status["checkpoint_warning"] = "Final checkpoint failed; preceding cloud checkpoint retained"
        finally:
            self.stop_checkpoints.set()
            if thread:
                thread.join(timeout=240)
            self.status["finished_at"] = datetime.now(timezone.utc).isoformat()
            try:
                self.bridge.json("PUT", "/run-status", self.status)
            except Exception:
                self.status["status_warning"] = "Failed to persist run status"


def configure_pi():
    key = os.environ.get("GLM_API_KEY")
    if not key:
        raise RuntimeError("Cloud entity-resolution credential is missing")
    directory = Path.home() / ".pi" / "agent"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile("/app/pi-models.json", directory / "models.json")
    auth = directory / "auth.json"
    auth.write_text(json.dumps({"zai-coding-cn": {"type": "api_key", "key": key}}))
    auth.chmod(0o600)


def serve():
    pipeline = None
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                return self.respond(200, {"status": "ok"})
            if self.path == "/status":
                return self.respond(200, pipeline.status.copy() if pipeline else {"status": "idle"})
            self.respond(404, {"error": "not found"})

        def do_POST(self):
            nonlocal pipeline
            if self.path != "/run":
                return self.respond(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 4096:
                return self.respond(400, {"error": "invalid request"})
            try:
                run_id = json.loads(self.rfile.read(length))["run_id"]
                if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                return self.respond(400, {"error": "invalid run ID"})
            with lock:
                if pipeline:
                    return self.respond(200 if pipeline.run_id == run_id else 409, pipeline.status)
                pipeline = Pipeline(run_id)
                threading.Thread(target=pipeline.run, daemon=True).start()
                self.respond(202, pipeline.status)

    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    serve()

#!/usr/bin/env python3
"""Pull cloud data for local development, refresh staging, or verify its deployment."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from qayem.cloud_development import deployment_binding, projection_fingerprint, pull_snapshot
from qayem.config import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts/development"
URL = "https://qayem-staging.qayem-ai.workers.dev"


def staging_dataset():
    binding = deployment_binding(ROOT, "staging")
    result = subprocess.run([str(ROOT / "cloudflare/updater/node_modules/.bin/wrangler"),
        "d1", "execute", binding["database_name"], "--env", "staging", "--remote", "--json", "--command",
        "SELECT d.version,d.ready,d.unit_count,d.launch_count,d.entity_count,"
        "(SELECT count(*) FROM units WHERE version=d.version) AS actual_units,"
        "(SELECT count(*) FROM launches WHERE version=d.version) AS actual_launches,"
        "(SELECT count(*) FROM documents WHERE version=d.version)"
        "+(SELECT count(*) FROM entities WHERE version=d.version) AS actual_entities "
        "FROM datasets d JOIN state s ON s.value=d.version WHERE s.key='active'"],
        cwd=ROOT / "cloudflare", text=True, capture_output=True, check=True)
    rows = json.loads(result.stdout)[0]["results"]
    if len(rows) != 1 or rows[0]["ready"] != 1:
        raise RuntimeError("Staging has no complete active dataset; run cloud-dev.py refresh")
    dataset = rows[0]
    for declared, actual in [("unit_count", "actual_units"), ("launch_count", "actual_launches"),
                             ("entity_count", "actual_entities")]:
        if dataset[declared] != dataset[actual]:
            raise RuntimeError("Staging dataset counts do not match")
    return dataset


def verify():
    dataset = staging_dataset()
    manifest = json.loads((ROOT / ".artifacts/cloudflare/staging/catalog.manifest.json").read_text())
    if dataset["version"] != manifest["version"] or dataset["unit_count"] != manifest["units"] \
            or dataset["launch_count"] != manifest["launches"] \
            or dataset["entity_count"] != manifest["document_parts"] + manifest["entities"]:
        raise RuntimeError("Staging is not using the expected exported dataset")
    for path in ("/", "/api/health", "/api/units?resale=all&page_size=1"):
        request = urllib.request.Request(URL + path, headers={"User-Agent": USER_AGENT})
        # A newly registered workers.dev route can return 404 briefly after deployment.
        for attempt in range(6):
            try:
                response = urllib.request.urlopen(request, timeout=60)
                break
            except urllib.error.HTTPError as error:
                if attempt == 5 or (error.code not in (404, 429) and error.code < 500):
                    raise
                time.sleep(2)
        with response:
            if response.headers.get("X-Qayem-Environment") != "staging" \
                    or "noindex" not in response.headers.get("X-Robots-Tag", ""):
                raise RuntimeError("Staging identity or noindex header is missing")
            body = response.read().decode()
        if path == "/":
            if "<title>[Staging] " not in body or 'name="robots" content="noindex,nofollow"' not in body:
                raise RuntimeError("Staging HTML identity is missing")
        elif path == "/api/health":
            if json.loads(body).get("status") != "ok":
                raise RuntimeError("Staging health check failed")
        elif json.loads(body).get("total") != dataset["unit_count"] or not json.loads(body).get("items"):
            raise RuntimeError("Staging API does not match its full catalogue")
    proof = {"verified_at": datetime.now(timezone.utc).isoformat(), "url": URL,
             "dataset": dataset, "public_api": "verified", "noindex": True}
    (ARTIFACTS / "staging-verified.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


def refresh():
    deployment_binding(ROOT, "staging")  # Validate isolation before pulling or publishing anything.
    snapshot = pull_snapshot(ROOT)
    fingerprint = projection_fingerprint(ROOT, snapshot["sha256"])
    record = ARTIFACTS / "staging-refresh.json"
    if record.exists():
        previous = json.loads(record.read_text())
        if previous.get("fingerprint") == fingerprint:
            dataset = staging_dataset()
            if dataset["version"] == previous.get("version"):
                return snapshot | {"staging_version": dataset["version"], "publication_skipped": True}
    subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/cloudflare-sync.py"),
        "--env", "staging", "--database", snapshot["database"]], cwd=ROOT, check=True)
    dataset = staging_dataset()
    record.write_text(json.dumps({"fingerprint": fingerprint, "version": dataset["version"],
        "source_run": snapshot["run_id"]}, indent=2) + "\n")
    return snapshot | {"staging_version": dataset["version"], "publication_skipped": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pull", "refresh", "verify"])
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    lock_directory = ROOT / ".qayem-locks"
    lock_directory.mkdir(parents=True, exist_ok=True)
    with (lock_directory / "development.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another development data operation is running")
        operation = {"pull": lambda: pull_snapshot(ROOT), "refresh": refresh, "verify": verify}[args.action]
        print(json.dumps(operation(), indent=2))


if __name__ == "__main__":
    main()

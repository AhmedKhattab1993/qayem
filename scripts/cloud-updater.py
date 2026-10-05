#!/usr/bin/env python3
"""Operate the isolated Qayem cloud updater without printing credentials."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.request

from qayem.cloud_pipeline import make_checkpoint
from qayem.config import db_path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "cloudflare" / "updater"
ARTIFACTS = ROOT / ".artifacts" / "cloud-updater"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
TOKEN = ARTIFACTS / "admin-token"
URL = "https://qayem-updater.qayem-ai.workers.dev"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def wrangler(*args, input=None):
    return subprocess.run([str(UPDATER / "node_modules/.bin/wrangler"), *args], cwd=UPDATER,
                          input=input, text=True, check=True)


def request(path, method="GET"):
    req = urllib.request.Request(URL + path, data=b"{}" if method == "POST" else None, method=method,
        headers={"Authorization": "Bearer " + TOKEN.read_text().strip(), "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def verify_publication():
    """Check independent cloud state before retiring the local scheduler."""
    status = request("/status")
    if not status or status.get("status") != "complete" or not status.get("publication"):
        raise SystemExit("Local schedule retained: no complete verified cloud update is recorded")
    publication = status["publication"]
    result = subprocess.run([str(UPDATER / "node_modules/.bin/wrangler"), "d1", "execute",
        "qayem-public", "--remote", "--json", "--command",
        "SELECT d.version,d.ready,d.unit_count,d.launch_count,d.entity_count,"
        "(SELECT count(*) FROM units WHERE version=d.version) AS actual_units,"
        "(SELECT count(*) FROM launches WHERE version=d.version) AS actual_launches,"
        "(SELECT count(*) FROM documents WHERE version=d.version)"
        "+(SELECT count(*) FROM entities WHERE version=d.version) AS actual_entities "
        "FROM datasets d JOIN state s ON s.value=d.version WHERE s.key='active'"],
        cwd=UPDATER, text=True, capture_output=True, check=True)
    rows = json.loads(result.stdout)[0]["results"]
    if len(rows) != 1:
        raise SystemExit("Local schedule retained: public dataset is missing")
    dataset = rows[0]
    if dataset["version"] != status["run_id"] or dataset["version"] != publication["version"] or dataset["ready"] != 1:
        raise SystemExit("Local schedule retained: the cloud publication is not active")
    for declared, actual in [("unit_count", "actual_units"), ("launch_count", "actual_launches"),
                             ("entity_count", "actual_entities")]:
        if dataset[declared] != dataset[actual]:
            raise SystemExit("Local schedule retained: cloud publication counts do not match")
    pointer_path = ARTIFACTS / "verified-current.json"
    wrangler("r2", "object", "get", "qayem-history/canonical/current.json", "--remote", "--file", str(pointer_path))
    pointer = json.loads(pointer_path.read_text())
    if pointer.get("run_id") != status["run_id"]:
        raise SystemExit("Local schedule retained: cloud database checkpoint does not match the publication")
    def public(path):
        req = urllib.request.Request("https://qayem.ai" + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    health = public("/api/health")
    units = public("/api/units?resale=all&page_size=1")
    if health.get("status") != "ok" or units.get("total") != dataset["unit_count"] or not units.get("items"):
        raise SystemExit("Local schedule retained: the public API did not verify the complete cloud catalogue")
    proof = {"verified_at": datetime.now(timezone.utc).isoformat(), "run_id": status["run_id"],
             "dataset": dataset, "checkpoint": pointer, "public_api": "verified"}
    (ARTIFACTS / "publication-verified.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("action", choices=["seed", "secrets", "run", "status", "stop", "verify", "disable-local"])
args = parser.parse_args()

if args.action == "seed":
    packed, metadata = make_checkpoint(db_path(), ARTIFACTS)
    key = "canonical/seed/0.db.gz"
    pointer = metadata | {"key": key, "run_id": "seed"}
    manifest = ARTIFACTS / "current.json"
    manifest.write_text(json.dumps(pointer) + "\n")
    wrangler("r2", "object", "put", "qayem-history/" + key, "--file", str(packed), "--remote")
    wrangler("r2", "object", "put", "qayem-history/canonical/current.json", "--file", str(manifest), "--remote")
    print(json.dumps({"seeded": True, "database_bytes": metadata["bytes"], "compressed_bytes": metadata["compressed_bytes"],
                      "sha256": metadata["sha256"]}))
elif args.action == "secrets":
    if not TOKEN.exists():
        TOKEN.write_text(secrets.token_hex(32) + "\n")
    TOKEN.chmod(0o600)
    auth = json.loads((Path.home() / ".pi/agent/auth.json").read_text())
    provider = auth.get("zai-coding-cn", {})
    if provider.get("type") != "api_key" or not provider.get("key"):
        raise SystemExit("Qayem's GLM provider credential is unavailable")
    wrangler("secret", "put", "ADMIN_TOKEN", input=TOKEN.read_text().strip() + "\n")
    wrangler("secret", "put", "GLM_API_KEY", input=provider["key"] + "\n")
    print("Stored the Qayem administration and GLM credentials as Cloudflare Worker secrets.")
elif args.action in {"run", "status", "stop"}:
    result = request("/" + args.action, "POST" if args.action in {"run", "stop"} else "GET")
    path = ARTIFACTS / (args.action + "-latest.json")
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
elif args.action == "verify":
    print(json.dumps(verify_publication(), indent=2))
elif args.action == "disable-local":
    verify_publication()
    plist = Path.home() / "Library/LaunchAgents/com.qayem.crawl.nightly.plist"
    if plist.exists():
        backup = ARTIFACTS / "com.qayem.crawl.nightly.plist"
        backup.write_bytes(plist.read_bytes())
        result = subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.qayem.crawl.nightly"], capture_output=True)
        if result.returncode not in (0, 3):
            raise SystemExit("Could not unload the local scheduler; its configuration is retained")
        plist.rename(plist.with_suffix(".plist.disabled"))
        print("Disabled the local nightly crawl after verified cloud publication. Its configuration is saved for rollback.")
    else:
        print("No local nightly LaunchAgent is installed.")

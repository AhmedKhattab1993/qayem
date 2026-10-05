#!/usr/bin/env python3
"""Export a consistent SQLite backup, import it into D1, and verify activation."""
import argparse
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from qayem.cloud_export import export_sql, retention_sql
from qayem.config import crawled_sources, db_path
from qayem.cloud_development import deployment_binding

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--local", action="store_true", help="Publish to the local Wrangler D1 emulator")
parser.add_argument("--export-only", action="store_true", help="Create the SQL and manifest without importing")
parser.add_argument("--database", type=Path, default=db_path())
parser.add_argument("--env", choices=["production", "staging"], default="production")
parser.add_argument("--keep-versions", type=int, default=3, help="Retain this many recent D1 versions plus the active version")
args = parser.parse_args()
if args.keep_versions < 2:
    parser.error("--keep-versions must be at least 2")
binding = deployment_binding(root, args.env)
destination = root / ".artifacts" / "cloudflare"
if args.env == "staging":
    destination = destination / "staging"
destination.mkdir(parents=True, exist_ok=True)
lock_directory = root / ".qayem-locks"
lock_directory.mkdir(parents=True, exist_ok=True)
publication_lock = (lock_directory / f"cloudflare-publication-{args.env}.lock").open("a")
try:
    fcntl.flock(publication_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("A Qayem Cloudflare publication is already running; the active catalogue is unchanged.")
backup = destination / "source.db"
with sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True) as source:
    with sqlite3.connect(backup) as target:
        source.backup(target)
manifest = export_sql(backup, destination / "catalog.sql", sources=crawled_sources())
print(json.dumps(manifest, indent=2))
if args.export_only:
    sys.exit(0)
command = ["npm", "exec", "--yes", "--package=wrangler@4.147.0", "--", "wrangler", "d1", "execute",
           binding["database_name"], "--local" if args.local else "--remote", "--yes"]
if args.env == "staging":
    command.extend(["--env", "staging"])
for sql in [root / "cloudflare" / "schema.sql", destination / "catalog.sql"]:
    log = destination / (sql.stem + ("-local" if args.local else "-remote") + ".log")
    print("Importing", sql.name, "(log:", log, ")", flush=True)
    with log.open("w") as stream:
        subprocess.run([*command, "--file", str(sql)], cwd=root / "cloudflare", check=True,
                       stdout=stream, stderr=subprocess.STDOUT)
result = subprocess.run([*command, "--json", "--command",
    "SELECT d.version,d.ready,d.unit_count,d.launch_count FROM datasets d JOIN state s ON s.value=d.version "
    "WHERE s.key='active'"], cwd=root / "cloudflare", check=True, capture_output=True, text=True)
rows = json.loads(result.stdout)[0]["results"]
if len(rows) != 1 or rows[0]["version"] != manifest["version"] or rows[0]["ready"] != 1:
    raise SystemExit("D1 did not activate the complete exported catalogue. Previous version retained.")
print("Verified D1 publication:", rows[0]["version"], "units:", rows[0]["unit_count"])
retention = destination / "retention.sql"
retention.write_text(retention_sql(args.keep_versions))
with (destination / "retention.log").open("w") as stream:
    subprocess.run([*command, "--file", str(retention)], cwd=root / "cloudflare", check=True,
                   stdout=stream, stderr=subprocess.STDOUT)
print("Retained", args.keep_versions, "recent D1 versions and the active catalogue")

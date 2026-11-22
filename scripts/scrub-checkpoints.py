"""Remove personal data from the older database checkpoints kept in the private R2 history bucket.

    .venv/bin/python scripts/scrub-checkpoints.py            # report which checkpoints still hold phone numbers
    .venv/bin/python scripts/scrub-checkpoints.py --apply    # scrub them in place (same key, same history otherwise)

Each checkpoint is downloaded, checked for stored phone numbers, scrubbed with `qayem scrub-personal --vacuum`
(the same code the nightly run uses), checked again and uploaded over itself. The checkpoint the current
pointer names is never touched: the nightly run keeps it clean. docs/STRATEGY.md 5.5 and 11.
"""
from __future__ import annotations

from contextlib import closing
import gzip
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "8157d695115b808345ee82fce21007f3"
BUCKET = "qayem-history"
WRANGLER = ["npx", "wrangler@4.147.0"]


def token() -> str:
    out = subprocess.run([*WRANGLER, "auth", "token"], cwd=ROOT / "cloudflare", capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()[-1]


def keys() -> list[str]:
    headers = {"Authorization": f"Bearer {token()}"}
    found, cursor = [], None
    while True:
        params = {"prefix": "canonical/", "per_page": 1000, **({"cursor": cursor} if cursor else {})}
        response = httpx.get(f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/{BUCKET}/objects",
                             headers=headers, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        found += [item["key"] for item in data["result"]]
        cursor = (data.get("result_info") or {}).get("cursor")
        if not cursor or not (data.get("result_info") or {}).get("is_truncated"):
            break
    return [key for key in found if key.endswith(".db.gz")]


def r2(action: str, key: str, path: Path) -> None:
    flag = "--file" if action == "put" else "--file"
    subprocess.run([*WRANGLER, "r2", "object", action, f"{BUCKET}/{key}", flag, str(path), "--remote"],
                   cwd=ROOT / "cloudflare", capture_output=True, check=True)


def phones(database: Path) -> int:
    """Listings still holding a phone number: the phone column, or an Egyptian mobile number in the payload or text."""
    sys.path.insert(0, str(ROOT / "src"))
    from qayem.privacy import PERSONAL_KEY, PHONE
    with closing(sqlite3.connect(database)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(properties)")}
        phone = "phone" if "phone" in columns else "NULL"
        count = 0
        for number, raw, description, title in connection.execute(
                f"SELECT {phone}, raw, description, title FROM properties"):
            # numbers inside payloads are prices and file names; personal payload fields are found by key
            if number or any(PHONE.search(text or "") for text in (description, title)):
                count += 1
            elif raw and raw.startswith("{"):
                try:
                    keys = json.dumps(list(_keys(json.loads(raw))))
                except ValueError:
                    continue
                count += bool(PERSONAL_KEY.search(keys))
    return count


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def main() -> None:
    apply = "--apply" in sys.argv
    with tempfile.TemporaryDirectory(prefix="qayem-scrub-") as folder:
        folder = Path(folder)
        pointer = folder / "current.json"
        r2("get", "canonical/current.json", pointer)
        current = json.loads(pointer.read_text())["key"]
        report = []
        for key in keys():
            if key == current:
                continue
            work = folder / key.replace("/", "_")  # a fresh folder: no -wal/-shm from another checkpoint
            work.mkdir()
            packed, database = work / "c.db.gz", work / "c.db"
            r2("get", key, packed)
            with gzip.open(packed, "rb") as source, database.open("wb") as target:
                shutil.copyfileobj(source, target)
            before = phones(database)
            after = before
            if before and apply:
                env = {**os.environ, "QAYEM_DB": str(database)}
                subprocess.run([str(ROOT / ".venv/bin/qayem"), "scrub-personal", "--vacuum"], env=env, check=True,
                               capture_output=True)
                after = phones(database)
                with closing(sqlite3.connect(database, isolation_level=None)) as connection:
                    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError(f"{key}: integrity check failed after scrubbing")
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    connection.execute("PRAGMA journal_mode=DELETE")
                if after == 0:
                    with database.open("rb") as source, gzip.open(packed, "wb", compresslevel=6) as target:
                        shutil.copyfileobj(source, target)
                    r2("put", key, packed)
            report.append({"key": key, "before": before, "after": after})
            print(json.dumps(report[-1]), flush=True)
            shutil.rmtree(work)
        print(json.dumps({"checkpoints": len(report), "with_personal_data": sum(1 for r in report if r["after"])}))


if __name__ == "__main__":
    main()

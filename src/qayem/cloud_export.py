"""Publish a consistent, sanitized website snapshot as an atomic D1 read model."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .valuation import slug
from .website_data import Catalog, detail, opportunity_key, public_unit, url_key


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def retention_sql(keep: int = 3) -> str:
    """Retain recent versions plus the active version, even after an older-version rollback."""
    if keep < 2:
        raise ValueError("Keep at least two versions for rollback")
    obsolete = ("SELECT version FROM datasets WHERE version NOT IN "
                f"(SELECT version FROM datasets ORDER BY generated_at DESC,version DESC LIMIT {int(keep)}) "
                "AND version != (SELECT value FROM state WHERE key='active')")
    return "\n".join(f"DELETE FROM {table} WHERE version IN ({obsolete});"
                     for table in ("documents", "units", "launches", "entities", "datasets")) + "\n"


def export_sql(database: Path, output: Path, *, sources=None, version: str | None = None) -> dict:
    """Stage a new immutable version; activate only after every expected row is present.

    Callers supply a SQLite backup so descriptions and the computed catalogue share
    a transactionally consistent source. Existing D1 versions remain available for rollback.
    """
    version = version or uuid4().hex
    catalog = Catalog(database, refresh_seconds=0, sources=sources)
    snapshot = catalog.snapshot()
    generated = datetime.now(timezone.utc).isoformat()
    documents = [("overview", "", snapshot.overview), ("catalog", "", snapshot.catalog)]
    for kind, entries in [("compound", snapshot.compounds), ("developer", snapshot.developers),
                          ("district", snapshot.districts)]:
        documents.extend((kind, key, value) for key, value in entries.items())
    launch_count = sum(len(pool) for pool in snapshot.launches.values())
    parts = [(kind, key, part, position, text[start:start + 8000])
             for position, (kind, key, data) in enumerate(documents)
             for text in [encoded(data)] for part, start in enumerate(range(0, len(text), 8000))]
    manifest = {"version": version, "generated_at": generated, "today": snapshot.today.isoformat(),
                "units": len(snapshot.records), "launches": launch_count, "documents": len(documents),
                "document_parts": len(parts)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        def insert(table, values):
            statement = f"INSERT OR REPLACE INTO {table} VALUES ({','.join(literal(v) for v in values)});\n"
            if len(statement.encode()) > 95_000:
                raise ValueError(f"{table} row exceeds the D1 statement budget")
            stream.write(statement)

        insert("datasets", [version, generated, manifest["today"], manifest["units"], launch_count,
                            len(parts), 0])
        for kind, key, part, position, text in parts:
            insert("documents", [version, kind, key, part, position, text])
        part_count = len(parts)
        entity_count = 0
        for position, (kind, key, entity) in enumerate(documents):
            if kind not in {"compound", "developer"}:
                continue
            if kind == "compound":
                developer = entity["developer"]
                names = [entity["name"], entity["name_ar"], entity["district"],
                         developer and developer["name"], developer and developer["name_ar"]]
                district, developer = entity["district_key"], developer["key"] if developer else ""
            else:
                names = [entity["name"], entity["name_ar"], *(c["name"] for c in entity["compounds"]),
                         *(c["name_ar"] for c in entity["compounds"])]
                district, developer = "", ""
            launch = entity["launch"]
            insert("entities", [version, kind, key, position, entity["name"].casefold(),
                (entity["name_ar"] or "").casefold(), " ".join(v or "" for v in names).casefold(),
                district, developer, entity["units"], entity["good_count"],
                launch["median_gap"] if launch else None, launch["compared"] if launch else 0])
            entity_count += 1
        rank = {r["id"]: i for i, r in enumerate(sorted(snapshot.records.values(), key=opportunity_key))}
        default = {r["id"] for r in snapshot.default}
        # One connection for every sanitized description; no N+1 connections during export.
        with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
            from .website_data import clean_text
            descriptions = {i: clean_text(text, 10_000) for i, text in connection.execute(
                "SELECT id,description FROM properties") if i in snapshot.records}
        for record in snapshot.records.values():
            compound, developer = record["compound"], record["developer"]
            search = " ".join(str(v or "") for v in [record["title"], record["district"], record["compound_name"],
                record["developer_name"], compound and compound["name"], compound and compound["name_ar"],
                developer and developer["name"], developer and developer["name_ar"]]).casefold()
            launch, peers = record.get("launch"), record.get("peers")
            cash = record["payment"]["cash_equivalent"]
            insert("units", [version, record["id"], int(record["id"] in default), slug(record["district"]),
                record["compound_key"] or "", record["developer_key"] or "", record["property_type"],
                record["opportunity"]["level"], record["payment"]["terms"], record["source"], search,
                record["price"], record["area_m2"], rank[record["id"]], launch["gap"] if launch else None,
                int(bool(launch and launch["same_finishing"])), peers["gap"] if peers else None,
                cash / record["area_m2"] if cash else None, url_key(record["source_url"]),
                encoded(public_unit(record)), encoded(record)])
            unit_detail = detail(snapshot, record, descriptions.get(record["id"]))
            # Store comparable IDs, rather than duplicating their photos and public fields
            # across thousands of detail rows. The API joins the same immutable version.
            unit_detail["comparables"] = [{"id": item["id"], "cash_ppm": item["cash_ppm"]}
                                          for item in unit_detail["comparables"]]
            text = encoded(unit_detail)
            for part, start in enumerate(range(0, len(text), 8000)):
                insert("documents", [version, "unit_detail", str(record["id"]), part, record["id"], text[start:start + 8000]])
                part_count += 1
        for compound, pool in snapshot.launches.items():
            for record in pool:
                insert("launches", [version, compound, record["id"], encoded(record)])
        v = literal(version)
        stream.write(f"UPDATE datasets SET entity_count={part_count + entity_count} WHERE version={v};\n")
        stream.write(f"UPDATE datasets SET ready=1 WHERE version={v} "
                     f"AND unit_count=(SELECT count(*) FROM units WHERE version={v}) "
                     f"AND launch_count=(SELECT count(*) FROM launches WHERE version={v}) "
                     f"AND entity_count=(SELECT count(*) FROM documents WHERE version={v})"
                     f"+(SELECT count(*) FROM entities WHERE version={v});\n")
        stream.write(f"INSERT INTO state(key,value) SELECT 'active',{v} FROM datasets WHERE version={v} AND ready=1 "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value;\n")
    manifest["document_parts"] = part_count
    manifest["entities"] = entity_count
    output.with_suffix(".manifest.json").write_text(encoded(manifest) + "\n", encoding="utf-8")
    return manifest

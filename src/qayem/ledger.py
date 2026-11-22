"""What the price guide keeps from day to day, in the canonical database.

- `index_editions`: one Qayem Index per month. The current month's edition is rewritten every night
  and frozen once the month is over, so an archived edition never changes on its dated URL.
- `segment_history`: each district and compound figure per day, to see what moved (article triggers).
- `market_rates`: the Central Bank of Egypt's exchange rates, policy rates and inflation per day.

The website reads these tables read-only (website_data.Catalog); only `qayem record-index` and
`qayem fetch-rates` write them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS index_editions (
  month TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL, frozen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS segment_history (
  day TEXT NOT NULL, key TEXT NOT NULL, count INTEGER NOT NULL, median_ppm REAL, median_cash_ppm REAL,
  confidence TEXT, PRIMARY KEY(day, key)
);
CREATE TABLE IF NOT EXISTS market_rates (
  day TEXT NOT NULL, name TEXT NOT NULL, value REAL NOT NULL, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
  PRIMARY KEY(day, name)
);
"""
MOVE_DAYS = 30
MOVE_THRESHOLD = 0.05  # a segment "moved" at ±5% over 30 days ...
MOVE_MIN_COUNT = 10  # ... with at least 10 listings on both days


def ensure(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_index(connection: sqlite3.Connection, snapshot) -> dict:
    """Write this month's edition and today's segment figures; freeze editions of past months."""
    ensure(connection)
    edition, today = snapshot.index, snapshot.today
    month = edition["month"]
    with connection:
        connection.execute("UPDATE index_editions SET frozen=1 WHERE month<? AND frozen=0", (month,))
        frozen = connection.execute("SELECT frozen FROM index_editions WHERE month=?", (month,)).fetchone()
        if not (frozen and frozen[0]):
            connection.execute(
                "INSERT INTO index_editions(month,data,updated_at,frozen) VALUES (?,?,?,0) "
                "ON CONFLICT(month) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (month, json.dumps(edition, ensure_ascii=False, separators=(",", ":")), _now()))
        rows = [(today.isoformat(), s["key"], s["count"], s["median_ppm"], s["median_cash_ppm"], s["confidence"])
                for s in snapshot.guide.get("segments", []) if s["size"] == "*" and s["delivery"] == "*"]
        connection.execute("DELETE FROM segment_history WHERE day=?", (today.isoformat(),))
        connection.executemany("INSERT INTO segment_history VALUES (?,?,?,?,?,?)", rows)
    return {"month": month, "segments": len(rows), "day": today.isoformat()}


def record_rates(connection: sqlite3.Connection, figures: dict) -> int:
    ensure(connection)
    rows = [(figures["day"], f"fx_{name}", value, figures["source"], figures["fetched_at"])
            for name, value in figures["fx"].items()]
    rows += [(figures["day"], name, value, figures["source"], figures["fetched_at"])
             for name, value in figures["key"].items()]
    with connection:
        connection.executemany("INSERT INTO market_rates VALUES (?,?,?,?,?) ON CONFLICT(day,name) DO UPDATE SET "
                               "value=excluded.value, fetched_at=excluded.fetched_at", rows)
    return len(rows)


def _has(connection: sqlite3.Connection, table: str) -> bool:
    return bool(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def editions(connection: sqlite3.Connection) -> dict[str, dict]:
    if not _has(connection, "index_editions"):
        return {}
    out = {}
    for month, data, frozen in connection.execute("SELECT month,data,frozen FROM index_editions ORDER BY month"):
        edition = json.loads(data)
        edition["provisional"] = not frozen
        out[month] = edition
    return out


def rates(connection: sqlite3.Connection) -> dict | None:
    """The latest exchange rates and key figures, each with its own date, and the previous policy rate."""
    if not _has(connection, "market_rates"):
        return None
    latest = {}
    for name, day, value in connection.execute(
            "SELECT name, day, value FROM market_rates m WHERE day=(SELECT max(day) FROM market_rates WHERE name=m.name)"):
        latest[name] = {"day": day, "value": value}
    if "fx_usd" not in latest:
        return None
    previous = connection.execute(
        "SELECT day, value FROM market_rates WHERE name='overnight_deposit' AND value != "
        "(SELECT value FROM market_rates WHERE name='overnight_deposit' ORDER BY day DESC LIMIT 1) "
        "ORDER BY day DESC LIMIT 1").fetchone()
    return {
        "day": latest["fx_usd"]["day"], "source": "Central Bank of Egypt",
        "egp_per": {name[3:]: item["value"] for name, item in latest.items() if name.startswith("fx_")},
        "key": {name: item for name, item in latest.items() if not name.startswith("fx_")},
        "previous_overnight_deposit": {"day": previous[0], "value": previous[1]} if previous else None,
    }


def moves(connection: sqlite3.Connection, today: date) -> list[dict]:
    """District and compound figures that moved ±5% over about 30 days, with enough listings both times."""
    if not _has(connection, "segment_history"):
        return []
    days = [row[0] for row in connection.execute("SELECT DISTINCT day FROM segment_history ORDER BY day")]
    current = max((d for d in days if d <= today.isoformat()), default=None)
    target = (today - timedelta(days=MOVE_DAYS)).isoformat()
    earlier = max((d for d in days if d <= target), default=None)
    if not current or not earlier:
        return []
    before = {key: (count, ppm) for key, count, ppm in connection.execute(
        "SELECT key, count, median_ppm FROM segment_history WHERE day=?", (earlier,))}
    out = []
    for key, count, ppm, confidence in connection.execute(
            "SELECT key, count, median_ppm, confidence FROM segment_history WHERE day=?", (current,)):
        old = before.get(key)
        if not old or not ppm or not old[1] or count < MOVE_MIN_COUNT or old[0] < MOVE_MIN_COUNT or confidence == "indicative":
            continue
        change = ppm / old[1] - 1
        if abs(change) >= MOVE_THRESHOLD:
            out.append({"key": key, "from_day": earlier, "to_day": current, "from": old[1], "to": ppm,
                        "change": round(change, 4), "count": count, "previous_count": old[0]})
    return sorted(out, key=lambda m: -abs(m["change"]))

"""Statutory buying costs in Egypt: the yearly registration and transfer fee schedules (docs/STRATEGY.md 5.2 B).

CAPMAS's indicators and NUCA's notices moved to `signals` (read from CAPMAS's JSON API and by Claude).
"""
from __future__ import annotations

import json
from pathlib import Path

FEE_SCHEDULES = Path(__file__).resolve().parent / "data" / "fee_schedules.json"


def fee_schedules() -> dict:
    """Yearly registry, transfer and buying-cost schedules (Law 9/2022 & market norms)."""
    try:
        return json.loads(FEE_SCHEDULES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"year": 2026, "items": []}

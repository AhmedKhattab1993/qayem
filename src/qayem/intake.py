"""WhatsApp intake: broker inventory sheets and developers' offers, read into price rows for review.

The Worker stores each incoming WhatsApp Business message (editorial.py, phone numbers withheld).
`qayem extract-inbox` reads the new ones through the admin API, asks the configured GLM model (Pi)
for one row per unit offered, and posts the rows back; a person accepts or rejects them on
/admin/review, and only accepted rows become observations.
"""
from __future__ import annotations

from pathlib import Path

from .articles import Site

ROWS = {
    "type": "object", "required": ["rows"], "additionalProperties": False,
    "properties": {"rows": {"type": "array", "maxItems": 200, "items": {
        "type": "object", "required": ["compound", "property_type", "area_m2", "price"], "additionalProperties": False,
        "properties": {"compound": {"type": ["string", "null"]}, "district": {"type": ["string", "null"]},
                       "property_type": {"type": ["string", "null"]}, "area_m2": {"type": ["number", "null"]},
                       "price": {"type": ["number", "null"], "description": "total asking price in EGP"},
                       "over": {"type": ["number", "null"], "description": "the premium over the paid amount, EGP"},
                       "down_payment": {"type": ["number", "null"]}, "delivery": {"type": ["string", "null"]}}}}}}
INSTRUCTIONS = """You read a message an Egyptian property broker or a developer's sales agent sent: an inventory sheet
or an offer, in Arabic, English or both. Return one row per unit with the compound, district, unit type, area in m²,
total asking price in EGP, the over (أوفر, the premium above what the owner paid) and the down payment when stated.
"مليون" means million; "ألف" thousand. Copy numbers as stated and convert them to plain EGP. Leave out anything not
stated. Return no rows for a message that offers no unit."""


def run(site: Site, folder: Path, *, extract=None, limit: int = 30) -> list[dict]:
    if extract is None:
        from .ai import run_pi
        folder.mkdir(parents=True, exist_ok=True)
        instructions = folder / "intake-instructions.md"
        instructions.write_text(INSTRUCTIONS, encoding="utf-8")
        extract = lambda text: run_pi(text[:20_000], ROWS, instructions)  # noqa: E731
    out = []
    for message in site.get("/api/admin/inbox?status=new", admin=True)["items"][:limit]:
        if not message.get("text"):
            continue  # a document or image: read on the review page by a person
        try:
            rows = [r for r in extract(message["text"])["rows"] if r.get("area_m2") and r.get("price")]
        except RuntimeError as exc:
            out.append({"id": message["id"], "status": "failed", "error": str(exc)})
            continue
        site.post(f"/api/admin/inbox/{message['id']}", {"action": "extracted", "rows": rows})
        out.append({"id": message["id"], "status": "extracted", "rows": len(rows)})
    return out

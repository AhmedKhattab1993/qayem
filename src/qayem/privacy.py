"""No personal data from sources: Qayem keeps the facts of a listing, never who posted it.

Phone numbers, e-mail addresses, member names and contact handles are dropped from parsed
listings and their stored payloads before anything is written, and `qayem scrub-personal`
removes what earlier crawls stored (rows and their history). See docs/STRATEGY.md, 5.5.
"""

from __future__ import annotations

import re
from typing import Any

WITHHELD = "[contact withheld]"
PHONE = re.compile(r"(?<!\d)(?:\+?20[\s().-]*)?0?1[0125](?:[\s().-]*\d){8}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Payload keys that name or reach a person (OpenSooq's member fields, phone reveal keys, a seller's name).
PERSONAL_KEY = re.compile(
    r"phone|whatsapp|e_?mail|^member_|user_?name|display_?name|avatar|^(tel|telephone|mobile|contact|chat|seller)$"
    r"|(seller|agent|owner|broker|shop)_?name",
    re.I,
)
# Payload keys holding free text, where a contact can be written into the sentence.
TEXT_KEYS = {"title", "description", "masked_description", "subtitle", "overpayment_note", "text", "body"}
# Version history columns (old snapshots) that held a contact.
PERSONAL_COLUMNS = ("phone",)


def scrub_text(value: Any) -> Any:
    """Text with any phone number or e-mail address replaced; anything else unchanged."""
    if not isinstance(value, str):
        return value
    return EMAIL.sub(WITHHELD, PHONE.sub(WITHHELD, value))


def scrub_raw(value: Any) -> Any:
    """A stored payload without personal keys, its free text scrubbed."""
    if isinstance(value, dict):
        return {key: scrub_text(item) if key in TEXT_KEYS else scrub_raw(item)
                for key, item in value.items() if not PERSONAL_KEY.search(str(key))}
    if isinstance(value, list):
        return [scrub_raw(item) for item in value]
    return value


def scrub_listing(listing) -> None:
    """Make a parsed listing safe to store (in place)."""
    listing.title = scrub_text(listing.title)
    listing.description = scrub_text(listing.description)
    listing.raw = scrub_raw(listing.raw or {})


def scrub_snapshot(payload: dict | None) -> dict | None:
    """A version-history snapshot or field diff without contacts."""
    if not isinstance(payload, dict):
        return payload
    out = {}
    for key, item in payload.items():
        if key in PERSONAL_COLUMNS:
            continue
        if key in ("title", "description"):
            item = ({k: scrub_text(v) for k, v in item.items()} if isinstance(item, dict) else scrub_text(item))
        elif key == "raw":
            item = scrub_raw(item)
        out[key] = item
    return out

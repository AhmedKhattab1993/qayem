"""Small shared request helpers for the local and Cloudflare APIs."""
from typing import Literal

from .valuation import DISTRICT_ALIASES

RANK_MIN_COMPOUND, RANK_MIN_DEVELOPER = 5, 20
SEARCH_DISTRICTS = DISTRICT_ALIASES | {
    "مدينة ٦ أكتوبر": "6th of October City", "مدينة 6 أكتوبر": "6th of October City", "مدينتي": "Madinaty",
    "التوسعات الشمالية": "Northern Expansion", "المعادي": "Maadi", "برج العرب": "Borg el arab",
}


def search_query(query: str) -> str:
    return SEARCH_DISTRICTS.get(" ".join(query.split()).casefold(), query).casefold()


def matches(query: str, *values: str | None) -> bool:
    text = " ".join(value or "" for value in values).casefold()
    return all(term in text for term in search_query(query).split())


def sort_entities(items: list[dict], sort: str, min_units: int) -> list[dict]:
    if sort == "name":
        return sorted(items, key=lambda e: e["name"].casefold())
    if sort == "opportunities":
        return sorted(items, key=lambda e: (-e["good_count"], -e["units"], e["key"]))
    if sort.startswith("gap"):
        ranked = [e for e in items if e["launch"] and e["launch"]["median_gap"] is not None
                  and e["launch"]["compared"] >= min_units]
        return sorted(ranked, key=lambda e: e["launch"]["median_gap"], reverse=sort == "gap_desc")
    return items


def page_of(items: list, page: int, page_size: int) -> dict:
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page,
            "page_size": page_size, "pages": (len(items) + page_size - 1) // page_size}


Sort = Literal["opportunity", "launch_gap", "peer_gap", "price_asc", "price_desc", "area_desc", "cash_ppm_asc", "newest"]
# "ready", or a year: ready by the end of it (a unit already delivered counts)
DELIVERY_PATTERN = r"^(|ready|\d{4})$"


def signing(record: dict) -> float | None:
    """What leaves the buyer's account at signing: the headline less the balance still owed."""
    remaining = record["payment"]["remaining"]
    return None if remaining is None else record["price"] - remaining


def within(record: dict, *, price_max=None, cash_max=None, signing_max=None, area_min=None, area_max=None,
           bedrooms_min=None, delivery="", newer_than=None) -> bool:
    """A buyer's budget and needs. A figure the listing does not publish never matches a limit on it.
    The Cloudflare API applies the same rules in SQL (`cloud_web.budget_clauses`)."""
    cash, paid = record["payment"]["cash_equivalent"], signing(record)
    when = record.get("delivery") or {}
    return ((price_max is None or record["price"] <= price_max)
            and (cash_max is None or (cash is not None and cash <= cash_max))
            and (signing_max is None or (paid is not None and paid <= signing_max))
            and (area_min is None or record["area_m2"] >= area_min)
            and (area_max is None or record["area_m2"] <= area_max)
            and (bedrooms_min is None or (record["bedrooms"] is not None and record["bedrooms"] >= bedrooms_min))
            and (not delivery or when.get("bucket") == "ready"
                 or (delivery != "ready" and bool(when.get("date")) and when["date"][:4] <= delivery))
            and (newer_than is None or record["id"] > newer_than))

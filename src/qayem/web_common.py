"""Small shared request helpers for the local and Cloudflare APIs."""
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

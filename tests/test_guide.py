"""The price guide: market districts, cross-source dedupe, segments, the index, the ledger and CBE rates."""
from datetime import date
import json
import sqlite3
from types import SimpleNamespace

from qayem import guide, ledger, market, rates


def item(i, source="nawy", district="New Cairo", compound="badya", cls="apartment", area=100.0, price=5_000_000.0,
         seen="2026-11-20T00:00:00Z", **extra):
    return {"id": i, "source": source, "district": district, "compound_key": compound, "class": cls,
            "property_type": cls, "area_m2": area, "price": price, "price_per_m2": round(price / area),
            "payment": {"terms": "cash", "cash_equivalent": price}, "last_seen_at": seen, "source_url": None,
            "delivery": {"bucket": "ready"}, **extra}


def test_market_districts_from_every_source_spelling():
    assert market.resolve("التجمع الخامس").key == "new-cairo"
    assert market.resolve("New Cairo - 5th Settlement").key == "new-cairo"
    assert market.resolve("6 أكتوبر").key == "6th-of-october-city"
    assert market.resolve("حدائق أكتوبر").key == "october-gardens"  # the longer name wins
    assert market.resolve("New Zayed").key == "new-zayed"
    assert market.resolve("North Coast-Sahel").key == "north-coast"
    # an Aqarmap street: the link's path names the place, most specific last
    url = "https://aqarmap.com.eg/en/listing/1-for-sale-cairo-new-cairo-madinaty-first-zone-13th-st./"
    assert market.resolve("13th St.", None, city="cairo", url=url).key == "madinaty"
    # an Alexandria page lists Alexandria: «6 October St.» there is a street, not the city
    assert market.resolve("6 October St.", None, city="alexandria").key == "alexandria"
    assert market.resolve("Somewhere unknown") is None
    assert all(d.key == __import__("qayem.valuation", fromlist=["slug"]).slug(d.name) for d in market.DISTRICTS)


def test_the_same_unit_on_two_sites_counts_once():
    items = [item(1, "nawy", price=5_000_000), item(2, "aqarmap", area=101, price=5_100_000),  # a copy
             item(3, "nawy", price=5_000_000),  # an identical unit on the same site: a second unit
             item(4, "aqarmap", price=5_400_000),  # 8% dearer: another unit
             item(5, "aqarmap", price=5_000_000, seen="2026-09-01T00:00:00Z")]  # seen months apart
    kept, dropped = guide.dedupe(items)
    assert dropped == 1 and {r["id"] for r in kept} == {1, 3, 4, 5}
    assert items[1]["duplicate_of"] == 1 and items[0]["copies"] == [{"source": "aqarmap", "id": 2}]


def test_a_segment_needs_enough_listings_and_sources():
    one = [item(i, "nawy") for i in range(9)]
    assert guide.confidence(one) is None  # 9 from one source
    assert guide.confidence(one + [item(9, "nawy")]) == "indicative"  # 10: single source
    assert guide.confidence([item(i, "nawy") for i in range(3)] + [item(9, "aqarmap"), item(10, "aqarmap")]) == "medium"
    mixed = [item(i, "nawy") for i in range(12)] + [item(100 + i, "aqarexit") for i in range(8)]
    assert guide.confidence(mixed) == "high"
    lopsided = [item(i, "nawy") for i in range(19)] + [item(99, "aqarexit")]
    assert guide.confidence(lopsided) == "medium"  # one source holds 95%


def test_segments_index_and_csv():
    today = date(2026, 11, 22)
    resale = [item(i, "nawy", area=100 + i, price=(5_000_000 + i * 10_000)) for i in range(12)]
    market_items = [item(100 + i, "aqarmap", compound=None, area=140 + i, price=7_000_000 + i * 50_000,
                         compound_name=None) for i in range(10)]
    market_items.append(item(200, "aqarmap", compound=None, area=100, price=200_000))  # a down payment as the price
    developer = [item(300 + i, "nawy_primary", area=100 + i, price=7_000_000) for i in range(4)]
    compounds = {"badya": {"key": "badya", "name": "Badya", "name_ar": "باديا"}}
    built = guide.build(resale, market_items, developer, compounds, {"badya": developer}, today)
    keys = {s["key"]: s for s in built["segments"]}
    district = keys["new-cairo/*/apartment/*/*"]
    assert district["count"] == 22 and district["confidence"] == "high" and not district["single_source"]
    assert built["counts"]["suspect"] == 1
    assert keys["new-cairo/badya/apartment/*/*"]["confidence"] == "indicative"  # 12 from Nawy alone
    assert keys["new-cairo/badya/apartment/*/*"]["developer"]["count"] == 4
    assert keys["new-cairo/badya/apartment/*/*"]["resale_vs_new"] < 0
    assert "new-cairo/outside/apartment/*/*" in keys  # 10 classifieds outside compounds
    edition = guide.index(built, today)
    assert edition["month"] == "2026-11" and edition["districts"][0]["key"] == "new-cairo"
    rows = guide.csv_rows(edition)
    assert rows[0][0] == "month" and rows[1][:3] == ["2026-11", "district", "new-cairo"]


def test_the_ledger_freezes_past_editions_and_finds_moves():
    connection = sqlite3.connect(":memory:")

    def snapshot(day, month, ppm):
        segment = {"key": "new-cairo/*/apartment/*/*", "size": "*", "delivery": "*", "count": 40, "median_ppm": ppm,
                   "median_cash_ppm": None, "confidence": "high"}
        return SimpleNamespace(today=date.fromisoformat(day), index={"month": month, "v": ppm},
                               guide={"segments": [segment]})
    ledger.record_index(connection, snapshot("2026-10-20", "2026-10", 60_000))
    ledger.record_index(connection, snapshot("2026-11-21", "2026-11", 66_000))
    ledger.record_index(connection, snapshot("2026-10-30", "2026-10", 1))  # a late rerun cannot rewrite October
    editions = ledger.editions(connection)
    assert editions["2026-10"]["v"] == 60_000 and not editions["2026-10"]["provisional"]
    assert editions["2026-11"]["provisional"]
    moves = ledger.moves(connection, date(2026, 11, 21))
    assert moves and moves[0]["change"] == 0.1 and moves[0]["key"] == "new-cairo/*/apartment/*/*"


def test_cbe_rates_are_read_from_the_published_pages():
    day, fx = rates.parse_fx("<p>Rates for Date: 22/11/2026</p><table><tr><td>US Dollar</td><td>54.3634</td>"
                             "<td>54.5026</td></tr><tr><td>Saudi Riyal</td><td>14.4892</td><td>14.5278</td></tr></table>")
    assert day == "2026-11-22" and fx == {"usd": 54.433, "sar": 14.5085}
    key = rates.parse_key_figures("<div>Overnight Deposit Rate</div><b>20.00%</b> HEADLINE INFLATION RATE 12.700%")
    assert key == {"overnight_deposit": 20.0, "headline_inflation": 12.7}
    connection = sqlite3.connect(":memory:")
    ledger.record_rates(connection, {"day": "2026-11-01", "fx": {"usd": 50.0}, "key": {"overnight_deposit": 21.0},
                                     "source": "CBE", "fetched_at": "x"})
    ledger.record_rates(connection, {"day": "2026-11-22", "fx": {"usd": 54.4}, "key": {"overnight_deposit": 20.0},
                                     "source": "CBE", "fetched_at": "x"})
    latest = ledger.rates(connection)
    assert latest["egp_per"]["usd"] == 54.4 and latest["previous_overnight_deposit"] == {"day": "2026-11-01", "value": 21.0}


def test_heads_answer_first_with_structured_data():
    import asyncio
    from qayem import seo
    segment = {"class": "apartment", "count": 3117, "median_ppm": 66_800, "p25_ppm": 52_400, "p75_ppm": 85_700,
               "resale_vs_new": -0.12, "confidence": "high", "compound": "*", "size": "*", "delivery": "*"}
    answer = seo.answer_ar(segment, "القاهرة الجديدة", "2026-11-22")
    assert answer.startswith("متوسط سعر المتر المطلوب في الشقق في القاهرة الجديدة حوالي 66.8 ألف جنيه (نوفمبر 2026)")
    assert "أرخص 12%" in answer and "لا تنشر أسعار البيع" in answer
    edition = guide.index({"segments": [{**segment, "key": "new-cairo/*/apartment/*/*", "district": "new-cairo",
                                         "district_name": "New Cairo", "district_name_ar": "القاهرة الجديدة",
                                         "region": "greater_cairo", "compound_name": None, "compound_name_ar": None,
                                         "single_source": False, "median_cash_ppm": None, "median_price": 9e6,
                                         "list_price_gap": None, "developer": None,
                                         "sources": [{"id": "nawy"}]}],
                           "period": {"start": "2026-10-23", "end": "2026-11-22"}, "counts": {"kept": 3117}},
                          date(2026, 11, 22))

    async def load(kind, key):
        return {"index": edition, "article": {"slug": "x-y-z", "lang": "en", "title": "T", "summary": "S",
                "published_at": "2026-11-22T00:00:00", "blocks": [{"type": "p", "text": "<b>body</b>"}]}}.get(kind)
    index = asyncio.run(seo.page_meta("/index/2026-11", {}, load))
    assert index.path == "/index/2026-11" and any(j["@type"] == "Dataset" for j in index.jsonld)
    assert "qayem-index-2026-11.csv" in json.dumps(index.jsonld)
    article = asyncio.run(seo.page_meta("/articles/x-y-z", {}, load))
    assert article.jsonld[0]["@type"] == "Article" and "&lt;b&gt;body" in article.body
    assert seo.csv_month("qayem-index-2026-11.csv") == "2026-11" and seo.csv_month("../etc") is None

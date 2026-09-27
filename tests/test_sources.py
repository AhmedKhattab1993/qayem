"""Per-source parser tests against real captured fixtures (tests/fixtures/)."""

import json
from pathlib import Path

from qayem.http_client import FetchError, HTTPStatusError
from qayem.sources.aqarexit import AqarExitSource, parse_detail as aqx_parse_detail
from qayem.sources.aqarmap import AqarmapSource
from qayem.sources.coldwellbanker import ColdwellBankerSource, parse_detail as cb_parse_detail
from qayem.sources.gpm import GpmSource, parse_detail as gpm_parse_detail
from qayem.sources.nawy import NawyPrimarySource, NawySource, parse_unit
from qayem.sources.opensooq import OpenSooqSource
from qayem.sources.semsar import SemsarSource, parse_detail_jsonld

FIXTURES = Path(__file__).parent / "fixtures"
EMPTY_PAGE = "<html><body></body></html>"


class FakeFetcher:
    """Returns canned responses; records requested URLs."""

    def __init__(self, responses: dict[str, str], fallback=None):
        self.responses = responses
        self.fallback = fallback  # callable(url) -> str
        self.requests: list[str] = []

    def get_text(self, url: str, encoding: str | None = None) -> str:
        self.requests.append(url)
        if url in self.responses:
            return self.responses[url]
        if self.fallback is not None:
            return self.fallback(url)
        raise FetchError(url, "no canned response")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def next_data_html(props: dict) -> str:
    payload = {"props": props, "buildId": "test"}
    return (
        '<html><head><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></head><body></body></html>"
    )


# --- Nawy --------------------------------------------------------------------


def test_nawy_parse_unit_fields():
    payload = json.loads((FIXTURES / "nawy_next_data.json").read_text())
    units = payload["props"]["pageProps"]["loadedSearchResultsSSR"]["results"]
    unit = parse_unit(units[0])
    assert unit.source_listing_id == "125234"
    assert unit.price == 10_128_000
    assert unit.currency == "EGP"
    assert unit.compound == "June"
    assert unit.developer == "SODIC"
    assert unit.bedrooms == 2
    assert unit.area_m2 == 110
    assert unit.is_resale is True
    assert "resale" in unit.resale_evidence
    assert unit.url.startswith("https://www.nawy.com/compound/")
    assert unit.delivery_date == "2026-08-20"


def test_nawy_primary_queries_developer_sale_and_is_never_resale():
    payload = json.loads((FIXTURES / "nawy_next_data.json").read_text())
    ssr = payload["props"]["pageProps"]["loadedSearchResultsSSR"]
    for unit in ssr["results"]:
        unit["saleType"] = "developer_sale"
    html = next_data_html(payload["props"])
    fetcher = FakeFetcher(
        {"https://www.nawy.com/search?sale_type=developer_sale&page_number=1&category=property": html})
    listings = list(NawyPrimarySource(fetcher, max_pages=1).fetch())
    assert len(listings) == 12
    assert all(item.is_resale is False for item in listings)
    assert listings[0].resale_evidence.startswith("developer launch")
    assert listings[0].delivery_date == "2026-08-20"


def test_nawy_skips_a_failing_page_and_keeps_crawling():
    payload = json.loads((FIXTURES / "nawy_next_data.json").read_text())
    payload["props"]["pageProps"]["loadedSearchResultsSSR"].update(total=36, pageSize=12)
    html = next_data_html(payload["props"])
    url = "https://www.nawy.com/search?sale_type=resale&page_number={}&category=property"
    fetcher = FakeFetcher({url.format(1): html, url.format(3): html})  # page 2 times out
    src = NawySource(fetcher)
    assert len(list(src.fetch())) == 24
    assert src.complete is True and len(src.errors) == 1  # recorded partial: no removals


def test_nawy_source_pagination_and_truncation():
    payload = json.loads((FIXTURES / "nawy_next_data.json").read_text())
    html = next_data_html(payload["props"])
    fetcher = FakeFetcher({"https://www.nawy.com/search?sale_type=resale&page_number=1&category=property": html})
    src = NawySource(fetcher, max_pages=1)
    listings = list(src.fetch())
    assert len(listings) == 12
    assert src.complete is False  # truncated by max_pages
    assert src.errors == []


def test_nawy_depth_cap_404_is_natural_end():
    """Nawy 404s past its crawl-depth cap. A 404 that repeats on every check
    means the reachable inventory ended — the run must complete, not fail."""
    payload = json.loads((FIXTURES / "nawy_next_data.json").read_text())
    html = next_data_html(payload["props"])

    class DepthCappedFetcher(FakeFetcher):
        def get_text(self, url: str, encoding: str | None = None) -> str:
            if "page_number=85" in url:
                raise HTTPStatusError(url, 404)
            return super().get_text(url, encoding)

    responses = {
        f"https://www.nawy.com/search?sale_type=resale&page_number={p}&category=property": html
        for p in range(1, 85)
    }
    src = NawySource(DepthCappedFetcher(responses))
    listings = list(src.fetch())
    assert len(listings) == 84 * 12
    assert src.complete is True
    assert src.scopes_completed == {"all"}
    assert src.errors == []


def test_nawy_transient_404_does_not_end_crawl():
    """A single 404 must be re-checked: if the page serves on retry, the
    crawl continues (a transient edge hiccup is not the end of inventory)."""
    payload = json.loads((FIXTURES / "nawy_next_data.json").read_text())
    html = next_data_html(payload["props"])

    class FlakyFetcher(FakeFetcher):
        def __init__(self, responses):
            super().__init__(responses)
            self.p85_hits = 0

        def get_text(self, url: str, encoding: str | None = None) -> str:
            if "page_number=85" in url:
                self.p85_hits += 1
                if self.p85_hits == 1:
                    raise HTTPStatusError(url, 404)
            if "page_number=87" in url:
                raise HTTPStatusError(url, 404)  # permanent: the real end
            return super().get_text(url, encoding)

    responses = {
        f"https://www.nawy.com/search?sale_type=resale&page_number={p}&category=property": html
        for p in range(1, 87)
    }
    src = NawySource(FlakyFetcher(responses))
    listings = list(src.fetch())
    assert len(listings) == 86 * 12  # crawled THROUGH the transient 404
    assert src.complete is True
    assert src.errors == []


# --- OpenSooq ----------------------------------------------------------------


def _opensooq_props(meta: dict) -> dict:
    props = json.loads((FIXTURES / "opensooq_page_props.json").read_text())
    props["serpApiResponse"]["listings"]["meta"] = meta
    return props


def _opensooq_page(current: int, pages: int) -> str:
    props = _opensooq_props(
        {"count": 2000, "per_page": 30, "pages": pages, "current_page": current}
    )
    return next_data_html({"pageProps": props})


def test_opensooq_parse_item_fields():
    props = json.loads((FIXTURES / "opensooq_page_props.json").read_text())
    items = props["serpApiResponse"]["listings"]["items"]
    from qayem.sources.opensooq import parse_item
    from datetime import datetime, timezone

    parsed = parse_item(items[0], datetime.now(timezone.utc))
    assert parsed.source_listing_id == "287480432"
    assert parsed.price == 4_800_000
    assert parsed.currency == "EGP"
    assert parsed.city == "cairo"
    assert parsed.district == "New Administrative Capital"
    assert parsed.bedrooms == 2
    assert parsed.bathrooms == 2
    assert parsed.area_m2 == 130
    assert parsed.url and parsed.url.startswith("https://eg.opensooq.com/en/")


def test_opensooq_natural_end_single_page():
    props = _opensooq_props({"count": 30, "per_page": 30, "pages": 1, "current_page": 1})
    url = "https://eg.opensooq.com/en/cairo/property/apartments-for-sale"
    fetcher = FakeFetcher({url: next_data_html({"pageProps": props})})
    src = OpenSooqSource(fetcher)
    listings = list(src.fetch())
    assert len(listings) == 30
    assert src.complete is True
    assert fetcher.requests == [url]


def test_opensooq_hard_cap_marks_truncated():
    base = "https://eg.opensooq.com/en/cairo/property/apartments-for-sale"
    responses = {base: _opensooq_page(1, 67)}
    for p in range(2, 51):
        responses[f"{base}?page={p}"] = _opensooq_page(p, 67)
    fetcher = FakeFetcher(responses)
    src = OpenSooqSource(fetcher)
    list(src.fetch())
    assert src.complete is False  # hit the 50-page SERP cap
    assert len(fetcher.requests) == 50


# --- Aqarmap -----------------------------------------------------------------


def test_aqarmap_cards_and_completion():
    page1 = (FIXTURES / "aqarmap_list.html").read_text()
    url1 = "https://aqarmap.com.eg/en/for-sale/property-type/cairo/"
    url2 = url1 + "?page=2"
    fetcher = FakeFetcher({url1: page1, url2: EMPTY_PAGE})
    src = AqarmapSource(fetcher)
    listings = list(src.fetch())
    assert len(listings) == 22
    assert src.complete is True
    assert src.errors == []

    first = next(l for l in listings if l.source_listing_id == "7255321")
    assert first.price == 43_000_000
    assert first.area_m2 == 600
    assert first.bedrooms == 5
    assert first.bathrooms == 5
    assert first.city == "cairo"
    assert first.district == "El Sheikh Zayed"
    assert first.compound == "Beverly Hills Compound - Sodic"
    assert first.property_type == "villa"
    assert first.finishing == "extra_super_lux"
    assert first.url == "https://aqarmap.com.eg/en/listing/7255321-for-sale-cairo-el-sheikh-zayed-city-compounds-beverly-hills/"
    # RSC flag association captured at least some listings
    flagged = [l for l in listings if l.raw.get("isResaleInstallment") is not None]
    assert flagged, "no listing got an isResaleInstallment flag"


# --- Semsar ------------------------------------------------------------------


def _semsar_fixture() -> str:
    return (FIXTURES / "semsar_list.html").read_bytes().decode("windows-1256", errors="replace")


def test_semsar_cards_microdata():
    page = _semsar_fixture()
    base = "https://www.semsarmasr.com/3akarat?r=70&g=0&a=0"
    fetcher = FakeFetcher({
        f"{base}&cid=765&p=1": page,
        f"{base}&cid=765&p=2": EMPTY_PAGE,
    })
    src = SemsarSource(fetcher, category="apartments")
    listings = list(src.fetch())
    assert src.complete is True
    assert len(listings) >= 8

    first = next(l for l in listings if l.source_listing_id == "2997698")
    assert first.price == 4_900_000
    assert first.down_payment == 4_000_000
    assert first.is_installment is True
    assert first.purpose == "sale"
    assert first.bedrooms == 3
    assert first.area_m2 == 155
    assert first.governorate == "cairo"
    assert first.is_resale is True  # «تمليك» in description
    assert first.seller_type == "broker"  # «بواسطة سمسار»
    assert first.finishing == "semi_finished"  # «نصف تشطيب» in the generated description

    # a rental card exists and is classified via businessFunction
    rentals = [l for l in listings if l.purpose == "rent"]
    assert rentals, "expected at least one LeaseOut card"


def test_semsar_stops_when_paging_repeats_the_same_page():
    page = _semsar_fixture()
    fetcher = FakeFetcher({}, fallback=lambda url: page)  # every page number returns page 1
    src = SemsarSource(fetcher, category="apartments")
    listings = list(src.fetch())
    assert src.pages_fetched == 2 and "repeats page 1" in src.errors[0]
    assert src.complete is False and not src.scopes_completed  # never a basis for removals
    assert len({item.source_listing_id for item in listings}) == len(listings)  # no duplicates yielded


def test_semsar_detail_jsonld_phone():
    detail = (FIXTURES / "semsar_detail.html").read_bytes().decode("windows-1256", errors="replace")
    data = parse_detail_jsonld(detail)
    assert data is not None
    provider = data["provider"]
    assert provider["telephone"].startswith("+20")


# --- GPM ---------------------------------------------------------------------


def test_gpm_list_card_and_detail_enrichment():
    page = (FIXTURES / "gpm_list.html").read_text()
    detail = (FIXTURES / "gpm_detail.html").read_text()
    listing_url = "https://gpmegypt.com/en/resale-real-estate/chalet-for-sale-in-dose-north-coast-y33pW"
    fetcher = FakeFetcher({
        "https://gpmegypt.com/en/resale": page,
        listing_url: detail,
        "https://gpmegypt.com/en/resale?page=2": EMPTY_PAGE,
    })
    src = GpmSource(fetcher, details=True, max_details=None)
    listings = list(src.fetch())
    assert src.complete is True
    assert len(listings) == 12

    first = next(l for l in listings if l.source_listing_id == "y33pW")
    assert first.is_resale is True
    assert first.price == 7_500_000
    assert first.title == "Sea View Chalet for sale in Dose North Coast"
    assert first.district == "North Coast"
    assert first.phone == "+201070399500"
    assert first.property_type == "chalets"

    gpm_parse_detail(first, detail)
    assert first.area_m2 == 70
    assert first.bedrooms == 1
    assert first.bathrooms == 2
    assert first.down_payment == 3_700_000
    assert first.is_installment is True
    assert first.finishing == "finished"
    assert first.delivery_status == "2027"


# --- AqarExit ----------------------------------------------------------------


AQX = "https://aqarexit.com/buy/opportunity/"
UNIT_A = "314a64f7-8ca5-4496-8ca6-f35c813845bf"


def aqx_sitemap(entries: dict[str, str]) -> str:
    filler = "".join(f"<url><loc>{AQX}00000000-0000-4000-8000-{i:012d}</loc><lastmod>2026-09-01T00:00:00Z</lastmod></url>"
                     for i in range(120))
    units = "".join(f"<url><loc>{AQX}{uid}</loc><lastmod>{mod}</lastmod></url>" for uid, mod in entries.items())
    return f"<urlset><url><loc>https://aqarexit.com/</loc></url>{units}{filler}</urlset>"


def test_aqarexit_detail_carries_the_full_payment_position():
    unit = aqx_parse_detail((FIXTURES / "aqarexit_detail.html").read_text(), UNIT_A, "2026-09-20T00:00:00Z")
    assert unit.compound == "Malaz بيت الوطن" and unit.developer == "Malaz" and unit.district == "التجمع الخامس"
    assert unit.property_type == "apartment" and unit.area_m2 == 177 and unit.bedrooms == 3 and unit.bathrooms == 3
    assert unit.finishing == "semi_finished" and unit.delivery_status == "under_construction"
    assert unit.delivery_date == "2030-06-30"
    # total = cash the buyer pays now + balance still owed to the developer
    assert unit.down_payment == 940_000 and unit.price == 940_000 + 3_760_000
    assert unit.is_installment is True and unit.installment_months == 60
    assert unit.is_resale is True and "verified by AqarExit" in unit.resale_evidence
    assert unit.raw["unit_code"] == "U-18340" and unit.raw["floor"] == "3"
    assert unit.raw["installment_every_months"] == 3 and unit.raw["lastmod"] == "2026-09-20T00:00:00Z"
    assert "أوفر" in unit.raw["overpayment_note"]
    other = aqx_parse_detail((FIXTURES / "aqarexit_detail_note.html").read_text(), "x" * 36)
    assert other.property_type == "chalet" and other.finishing == "finished" and other.raw["floor"] is None


def test_aqarexit_fetches_only_new_or_changed_units_and_confirms_the_rest():
    detail = (FIXTURES / "aqarexit_detail.html").read_text()
    changed, same, new = "c" * 8 + UNIT_A[8:], "d" * 8 + UNIT_A[8:], UNIT_A
    sitemap = aqx_sitemap({changed: "2026-09-25T00:00:00Z", same: "2026-09-01T00:00:00Z", new: "2026-09-26T00:00:00Z"})
    fetcher = FakeFetcher({"https://aqarexit.com/sitemap.xml": sitemap, AQX + changed: detail, AQX + new: detail})
    known = {changed: "2026-09-02T00:00:00Z", same: "2026-09-01T00:00:00Z"}
    src = AqarExitSource(fetcher, known=known, max_details=10)
    ids = [item.source_listing_id for item in src.fetch()]
    assert set(ids) == {new, changed} and ids[0] == new  # new units first
    assert AQX + same not in fetcher.requests
    assert same in src.present_ids and len(src.present_ids) == 123
    assert src.complete and src.scopes_completed == {"all"}


def test_aqarexit_refuses_a_truncated_sitemap():
    fetcher = FakeFetcher({"https://aqarexit.com/sitemap.xml": "<urlset></urlset>"})
    src = AqarExitSource(fetcher)
    assert list(src.fetch()) == [] and not src.complete and src.present_ids == set()


# --- Coldwell Banker ---------------------------------------------------------


def test_cb_detail_fields():
    html = (FIXTURES / "cb_detail.html").read_text()
    url = "https://coldwellbanker-eg.com/en/properties/apartment-647036"
    parsed = cb_parse_detail(html, url)
    assert parsed.source_listing_id == "647036"
    assert parsed.price == 38_000_000
    assert parsed.area_m2 == 440.0
    assert parsed.bedrooms == 4
    assert parsed.bathrooms == 4
    assert parsed.is_resale is True
    assert parsed.resale_evidence == "Sale Type field: Resale"
    assert parsed.finishing == "core_shell"  # site's 'Unfinshed'


def test_cb_source_truncation_and_completion():
    sitemap = (FIXTURES / "cb_sitemap.xml").read_text()
    hub = (FIXTURES / "cb_hub.html").read_text()
    detail = (FIXTURES / "cb_detail.html").read_text()

    def fallback(url: str) -> str:
        if "properties.xml" in url:
            raise FetchError(url, "unexpected")
        return detail

    responses = {
        "https://ecms.coldwellbanker-eg.com/properties.xml": sitemap,
        "https://coldwellbanker-eg.com/en/residential-resale-properties-egypt": hub,
    }
    fetcher = FakeFetcher(responses, fallback=fallback)

    src = ColdwellBankerSource(fetcher, max_details=3)
    listings = list(src.fetch())
    assert len(listings) == 3
    assert src.complete is False  # detail budget exhausted sitemap only partially

    # full run: every sitemap URL fetched → complete
    src2 = ColdwellBankerSource(FakeFetcher(responses, fallback=fallback), max_details=None)
    listings2 = list(src2.fetch())
    assert src2.complete is True
    assert len(listings2) == 60
    # every listing carries the Sale Type field from the fixture detail
    assert all(l.is_resale is True for l in listings2)


def test_semsar_description_template():
    from qayem.sources.semsar import parse_description
    text = ("شقة للبيع (تمليك) في المنصورة الجديدة الدقهلية مصر، 3 غرف، 183 م² ،جديدة أول ساكن، "
            "بالتقسيط بدون وسيط من المالك مباشرة متشطب إكسترا سوبر لوكس . مقدم دفعة أولى 1,934,164 جنيه. "
            "والباقي أٌقساط على 84 شهر")
    assert parse_description(text) == {
        "bedrooms": 3, "finishing": "extra_super_lux", "down_payment": 1_934_164.0,
        "installment_months": 84, "is_installment": True,
    }
    assert parse_description("محل أو تجاري للبيع (تمليك) في بنها القليوبية مصر، 200 م² بدون تشطيب . "
                             "السعر 250,000 جنيه قابل للتفاوض") == {
        "finishing": "core_shell", "price_negotiable": True,
    }
    assert parse_description("شقة للبيع في القاهرة مصر، 2 غرفة (غرفتين) 100 م² متشطب لوكس")["bedrooms"] == 2

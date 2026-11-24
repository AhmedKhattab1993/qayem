"""Page heads, sitemap, first-party events, lead capture, search alerts and their nightly dispatch."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from qayem import seo
from qayem.alerts import dispatch
from qayem.cloud_export import export_sql
from qayem.cloud_web import Store, create_cloud_app
from qayem.growth import LocalDatabase, Settings, phone, search_query
from qayem.web import create_app
from test_cloudflare import SCHEMA, SQLite
from test_web import database  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "web" / "index.html").read_text()
LEADS_SCHEMA = ROOT / "cloudflare" / "leads-schema.sql"


class FakeHttp:
    def __init__(self, responses=None):
        self.calls, self.responses = [], responses or {}

    async def post(self, url, body, headers=None):
        self.calls.append((url, body, headers))
        return next((answer for prefix, answer in self.responses.items() if url.startswith(prefix)), (200, "{}"))


@pytest.fixture()
def apps(database, tmp_path):  # noqa: F811
    export = tmp_path / "export.sql"
    export_sql(database, export, version="first")
    published = tmp_path / "public.db"
    with sqlite3.connect(published) as db:
        db.executescript(SCHEMA.read_text())
        db.executescript(export.read_text())
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(TEMPLATE)
    leads = LocalDatabase(tmp_path / "leads.db", LEADS_SCHEMA)
    http = FakeHttp()
    settings = Settings(telegram_token="t0k", telegram_chat="42", admin_token="a" * 40, resend_key="re_x",
                        hash_salt="salt")
    local = create_app(database, dist, sources=None, leads_db=None)
    cloud = create_cloud_app(SQLite(published), leads=leads, http=http, settings=settings, template=TEMPLATE)
    with TestClient(local) as local_client, TestClient(cloud) as cloud_client:
        yield local_client, cloud_client, leads, http, SQLite(published)


@pytest.mark.parametrize("path", [
    "/", "/evaluate", "/evaluate?compound=Garden&property_type=apartment&area=120&price=4200000", "/evaluate?mode=sell",
    "/units", "/units?price_dropped=true", "/units/17", "/units/18", "/units/999999", "/units/abc",
    "/compounds", "/compounds/garden", "/compounds/nowhere", "/developers/nile", "/districts", "/districts/new-cairo",
    "/methodology", "/privacy", "/compare", "/watchlist", "/sheet/17", "/nothing-here",
])
def test_every_page_head_matches_between_local_and_cloud(apps, path):
    local, cloud, *_ = apps
    old, new = local.get(path), cloud.get(path)
    assert (old.status_code, old.text) == (new.status_code, new.text)
    assert new.headers["content-type"].startswith("text/html")


def test_a_compound_page_carries_its_own_head_summary_and_faq(apps):
    _, cloud, *_ = apps
    html = cloud.get("/compounds/garden").text
    assert html.count("<title>") == 1 and "Garden" in html.split("<title>")[1].split("</title>")[0]
    assert '<link rel="canonical" href="https://qayem.ai/compounds/garden" />' in html
    assert 'property="og:image" content="https://qayem.ai/og-default.png"' in html
    assert '"@type":"FAQPage"' in html and '"@type":"BreadcrumbList"' in html
    assert '<div id="root"><div class="seo-summary"><h1>' in html  # crawlers read it; React replaces it
    assert html.count('name="description"') == 1
    unit = cloud.get("/units/17").text
    assert "أرخص" in unit.split("<title>")[1] and "RealEstateListing" in unit
    assert 'content="noindex,follow"' in cloud.get("/compare").text
    missing = cloud.get("/compounds/nowhere")
    assert missing.status_code == 404 and 'content="noindex,follow"' in missing.text


def test_rendering_cannot_be_broken_by_published_text():
    meta = seo.Meta('A "quoted" </script><b>name</b>', "x</title>", "/units/1",
                    jsonld=[{"name": "</script><script>alert(1)</script>"}], body="<p>ok</p>")
    html = seo.render(TEMPLATE, meta)
    assert "</script><script>alert(1)" not in html and "<\\/script>" in html
    assert "&lt;b&gt;name&lt;/b&gt;" in html and 'content="x&lt;/title&gt;"' in html


def test_sitemap_robots_and_canonical_host(apps):
    local, cloud, *_ = apps
    assert local.get("/sitemap.xml").text == cloud.get("/sitemap.xml").text
    sitemap = cloud.get("/sitemap.xml").text
    for path in ("/</loc>", "/map<", "/index<", "/compounds/garden<", "/districts/new-cairo<", "/developers/nile<"):
        assert f"https://qayem.ai{path}" in sitemap
    assert "/units/17<" not in sitemap and "/units/22<" not in sitemap  # unit pages fade out of search
    assert 'content="noindex,follow"' in cloud.get("/units/17").text
    robots = cloud.get("/robots.txt").text
    assert "Sitemap: https://qayem.ai/sitemap.xml" in robots and "Disallow: /api" not in robots
    for bot in ("OAI-SearchBot", "GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {bot}" in robots
    llms = cloud.get("/llms.txt")
    assert llms.status_code == 200 and llms.text.startswith("# Qayem") and "https://qayem.ai/methodology" in llms.text
    assert local.get("/llms.txt").text == llms.text
    moved = cloud.get("http://www.qayem.ai/units/17?utm_source=x", follow_redirects=False)
    assert moved.status_code == 301 and moved.headers["location"] == "https://qayem.ai/units/17?utm_source=x"
    assert cloud.get("http://www.qayem.ai/api/health", follow_redirects=False).status_code == 301
    assert cloud.get("/api/overview").headers["x-robots-tag"] == "noindex"


def test_events_are_kept_without_raw_addresses_and_never_fail(apps):
    _, cloud, leads, *_ = apps
    human = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Mobile Safari", "cf-connecting-ip": "203.0.113.7",
             "cf-ipcountry": "EG"}
    body = {"type": "outbound_click", "path": "/units/17", "unit_id": 17, "visitor": "v-1234567890",
            "referrer": "https://m.facebook.com/groups/x", "utm_source": "facebook", "meta": {"cta": "source", "x": [1]}}
    assert cloud.post("/api/events", json=body, headers=human).status_code == 204
    assert cloud.post("/api/events", json={**body, "type": "pageview"}, headers={"user-agent": "Googlebot/2.1"}).status_code == 204
    assert cloud.post("/api/events", json={"type": "drop table"}, headers=human).status_code == 204
    assert cloud.post("/api/events", content=b"not json", headers=human).status_code == 204
    rows = asyncio.run(leads.all("SELECT * FROM events ORDER BY id"))
    assert [(r["event_type"], r["is_bot"], r["device"]) for r in rows] == [("outbound_click", 0, "mobile"), ("pageview", 1, "desktop")]
    assert rows[0]["referrer"] == "m.facebook.com" and rows[0]["country"] == "EG" and rows[0]["meta"] == '{"cta":"source"}'
    assert "203.0.113.7" not in json.dumps(rows)


def test_a_lead_is_stored_and_the_founder_gets_a_whatsapp_link(apps):
    _, cloud, leads, http, _ = apps
    body = {"kind": "developer_price", "role": "buyer", "name": "Mona", "whatsapp": "٠١٠١٢٣٤٥٦٧٨", "unit_id": 17,
            "intent": {"budget": 5000000, "timeline": "3 months"}, "path": "/units/17", "lang": "ar"}
    assert cloud.post("/api/leads", json=body).json() == {"ok": True}
    row = asyncio.run(leads.all("SELECT * FROM leads"))[0]
    assert row["whatsapp"] == "+201012345678" and row["kind"] == "developer_price" and json.loads(row["intent"])["budget"] == 5000000
    url, message, _ = http.calls[-1]
    assert url == "https://api.telegram.org/bott0k/sendMessage" and message["chat_id"] == "42"
    assert "https://wa.me/201012345678?text=" in message["text"] and "/units/17" in message["text"]
    # When Telegram is omitted and FOUNDER_EMAIL + RESEND_API_KEY are set, founder pings fall back to Resend email.
    from qayem.growth import Growth, telegram
    email_http = FakeHttp()
    fallback = Growth(leads=None, public=None, http=email_http,
                      settings=Settings(resend_key="re_x", founder_email="founder@example.com"))
    assert asyncio.run(telegram(fallback, "<b>New lead</b>\nhttps://qayem.ai/units/17")) is True
    assert email_http.calls[-1][0] == "https://api.resend.com/emails"
    assert email_http.calls[-1][1]["to"] == ["founder@example.com"]
    assert "Qayem: New lead" in email_http.calls[-1][1]["subject"]
    assert cloud.post("/api/leads", json={**body, "whatsapp": "12", "email": "nope"}).json()["detail"] == "invalid_contact"
    assert cloud.post("/api/leads", json={**body, "kind": "spam"}).status_code == 422
    assert cloud.post("/api/leads", json={**body, "website": "http://spam"}).json() == {"ok": True}  # honeypot
    assert len(asyncio.run(leads.all("SELECT id FROM leads"))) == 1
    for _ in range(10):
        last = cloud.post("/api/leads", json={**body, "email": "a@b.co"})
    assert last.status_code == 429


def test_turnstile_is_required_once_configured(database, tmp_path):  # noqa: F811
    leads = LocalDatabase(tmp_path / "leads.db", LEADS_SCHEMA)
    http = FakeHttp({"https://challenges.cloudflare.com": (200, '{"success": false}')})
    app = create_app(database, tmp_path / "none", sources=None, leads_db=tmp_path / "leads.db", http=http,
                     settings=Settings(turnstile_secret="secret", turnstile_site_key="site"))
    with TestClient(app) as client:
        assert client.get("/api/config").json() == {"leads": True, "turnstile_site_key": "site", "email_alerts": False}
        body = {"kind": "seller", "whatsapp": "+971501234567", "turnstile": "token"}
        assert client.post("/api/leads", json=body).json()["detail"] == "verification_failed"
        http.responses = {"https://challenges.cloudflare.com": (200, '{"success": true}')}
        assert client.post("/api/leads", json=body).json() == {"ok": True}
    assert asyncio.run(leads.all("SELECT whatsapp FROM leads")) == [{"whatsapp": "+971501234567"}]
    without = create_app(database, tmp_path / "none", sources=None, leads_db=None)
    with TestClient(without) as client:
        assert client.post("/api/leads", json=body).status_code == 503
        assert client.post("/api/events", json={"type": "pageview"}).status_code == 204


def test_alerts_subscribe_once_and_unsubscribe(apps):
    _, cloud, leads, http, _ = apps
    body = {"channel": "email", "destination": "Buyer@Example.com", "query": "delivery=ready&compound=garden&price_max=6000000",
            "label": "Garden · ready", "lang": "en", "path": "/units"}
    assert cloud.post("/api/alerts", json=body).json() == {"ok": True}
    assert cloud.post("/api/alerts", json=body).json() == {"ok": True, "existing": True}
    alert = asyncio.run(leads.all("SELECT * FROM alerts"))[0]
    assert alert["destination"] == "buyer@example.com"
    assert alert["query"] == "compound=garden&price_max=6000000&delivery=ready"  # the website's own order
    assert alert["last_seen_unit"] == 30  # only units listed after signing up are new
    assert "New alert" in http.calls[-1][1]["text"]
    assert cloud.post("/api/alerts", json={**body, "query": "level=everything"}).status_code == 422
    page = cloud.get(f"/api/alerts/unsubscribe?token={alert['token']}")
    assert page.status_code == 200 and "This alert is off" in page.text
    assert asyncio.run(leads.all("SELECT active FROM alerts")) == [{"active": 0}]
    assert "not valid" in cloud.get("/api/alerts/unsubscribe?token=" + "x" * 30).text


def test_the_funnel_is_private_and_counts_humans(apps):
    _, cloud, *_ = apps
    browser = {"user-agent": "Mozilla/5.0 (Linux; Android 15) Mobile"}
    for visitor in ("v-aaaaaaaaaa", "v-bbbbbbbbbb", "v-aaaaaaaaaa"):
        cloud.post("/api/events", json={"type": "pageview", "path": "/", "visitor": visitor,
                                        "referrer": "https://chatgpt.com/c/123" if visitor == "v-bbbbbbbbbb" else ""},
                   headers=browser)
    cloud.post("/api/events", json={"type": "pageview", "path": "/"}, headers={"user-agent": "curl/8"})
    cloud.post("/api/leads", json={"kind": "general", "email": "x@y.co"})
    assert cloud.get("/api/admin/funnel").status_code == 401
    assert cloud.get("/api/admin/funnel", headers={"Authorization": "Bearer wrong"}).status_code == 401
    report = cloud.get("/api/admin/funnel", headers={"Authorization": "Bearer " + "a" * 40}).json()
    assert report["totals"]["visitors"] == 2 and report["totals"]["pageviews"] == 3 and report["totals"]["leads"] == 1
    assert report["totals"]["capture_rate"] == 0.5 and report["pages"] == [{"path": "/", "n": 3}]
    assert report["ai_referrals"] == [{"source": "chatgpt.com", "visitors": 1, "pageviews": 1}]


def test_dispatch_sends_new_matches_once_per_publication(apps):
    _, cloud, leads, http, public = apps
    for body in [{"channel": "email", "destination": "a@b.co", "query": "compound=garden", "label": "Garden"},
                 {"channel": "whatsapp", "destination": "+201000000001", "query": "compound=lake", "label": "Lake"},
                 {"channel": "email", "destination": "c@d.co", "query": "compound=nowhere", "label": "None"}]:
        assert cloud.post("/api/alerts", json=body).json()["ok"]
    asyncio.run(leads.run("UPDATE alerts SET last_seen_unit=10"))  # as if they signed up before units 11+
    http.calls.clear()
    store = asyncio.run(Store(public).open())
    settings = Settings(telegram_token="t", telegram_chat="1", resend_key="re_x")
    summary = asyncio.run(dispatch(store, leads, http, settings))
    assert summary | {"alerts": 3} == {"status": "sent", "version": "first", "alerts": 3, "matched": 2, "emailed": 1,
                                       "email_failed": 0, "whatsapp": 1}
    email = next(body for url, body, _ in http.calls if url == "https://api.resend.com/emails")
    assert email["to"] == ["a@b.co"] and "/units/17?utm_source=alert" in email["html"]
    assert email["headers"]["List-Unsubscribe"].startswith("<https://qayem.ai/api/alerts/unsubscribe?token=")
    digest = next(body for url, body, _ in http.calls if "telegram" in url)["text"]
    assert "https://wa.me/201000000001?text=" in digest
    assert asyncio.run(dispatch(store, leads, http, settings))["status"] == "already_sent"
    assert {r["last_seen_unit"] for r in asyncio.run(leads.all("SELECT last_seen_unit FROM alerts"))} == {30}


def test_a_failed_email_is_retried_with_the_next_publication(apps):
    _, cloud, leads, _, public = apps
    cloud.post("/api/alerts", json={"channel": "email", "destination": "a@b.co", "query": "compound=garden", "label": "G"})
    asyncio.run(leads.run("UPDATE alerts SET last_seen_unit=10"))
    store = asyncio.run(Store(public).open())
    failing = FakeHttp({"https://api.resend.com": (500, "down")})
    summary = asyncio.run(dispatch(store, leads, failing, Settings(resend_key="re_x")))
    assert summary["email_failed"] == 1
    assert asyncio.run(leads.all("SELECT last_seen_unit FROM alerts")) == [{"last_seen_unit": 10}]


def test_contact_and_search_validation():
    assert phone("+20 100 123 4567") == "+201001234567" and phone("00966501234567") == "+966501234567"
    assert phone("+2001001234567") == "+201001234567" and phone("12345") is None and phone("+0123456789") is None
    assert search_query("price_max=5e6&q=<script>&level=good&unknown=1") == "q=script&price_max=5000000&level=good"
    assert search_query("bedrooms_min=99") is None and search_query("") == ""
    assert search_query("price_dropped=true&compound=badya") == "compound=badya&price_dropped=true"


def test_history_reports_delistings_price_cuts_and_developer_moves(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from qayem.db import init_db
    from qayem.models import Property, PropertyVersion
    from qayem.website_data import Catalog

    today = datetime(2026, 11, 20, tzinfo=timezone.utc)
    start = today - timedelta(days=60)
    path = tmp_path / "history.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    base = {"source": "aqarexit", "purpose": "sale", "currency": "EGP", "property_type": "apartment",
            "district": "New Cairo", "compound": "Garden", "developer": "Nile", "is_resale": True, "status": "active",
            "finishing": "finished", "first_seen_at": start, "last_seen_at": today}
    with Session(engine) as session:
        for i in range(1, 9):  # 1-8 active; 3 and 4 were cut in price; 5 rose
            session.add(Property(id=i, source_listing_id=str(i), area_m2=100 + i, price=5_000_000 + i, **base))
        for i in range(9, 13):  # 9-12 listed after the opening crawls and gone within days
            session.add(Property(id=i, source_listing_id=str(i), area_m2=110, price=5_000_000, **base | {
                "status": "removed", "first_seen_at": today - timedelta(days=20), "removed_at": today - timedelta(days=12 + i % 3)}))
        for i in range(13, 16):  # the developer's own units, observed all along; one raised 10%
            session.add(Property(id=i, source_listing_id=str(i), area_m2=105, price=8_000_000, **base | {
                "source": "nawy_primary", "is_resale": False, "is_installment": True, "down_payment": 800_000,
                "installment_months": 96}))
        session.flush()
        edits = [(3, 5_500_000, 5_000_003), (4, 5_200_000, 5_000_004), (5, 4_000_000, 5_000_005),
                 (13, 7_272_727, 8_000_000), (6, 1_000, 5_000_006)]  # the last is a data correction (bounds)
        for property_id, old, new in edits:
            session.add(PropertyVersion(property_id=property_id, captured_at=today - timedelta(days=9), change_type="updated",
                                        changed_fields={"price": {"old": old, "new": new}}))
        session.add(PropertyVersion(property_id=7, captured_at=today - timedelta(days=9), change_type="updated",
                                    changed_fields={"price": {"old": 6_000_000, "new": 5_000_007},
                                                    "url": {"old": "https://a/list", "new": "https://a/7"}}))  # parser upgrade
        session.commit()
    snapshot = Catalog(path, 0, None).snapshot()
    assert snapshot.records[3]["price_change"]["change"] == pytest.approx(-0.0909, abs=1e-4)
    assert snapshot.records[7]["price_change"] is None and snapshot.records[6]["price_change"] is None
    history = snapshot.compounds["garden"]["history"]
    assert history["delisted_30d"] == 4 and history["turnover_30d"] == pytest.approx(4 / 12, abs=1e-4)
    assert history["median_days_listed"] == 8 and history["tracked_delisted"] == 4
    assert (history["price_cuts_60d"], history["price_rises_60d"]) == (2, 1)
    assert history["developer_change_60d"] == pytest.approx(0.1 / 3, abs=1e-3) and history["developer_rising"] == 1
    assert snapshot.overview["history"]["delisted_30d"] == 4
    with TestClient(create_app(path, tmp_path / "none", sources=None, leads_db=None)) as client:
        dropped = client.get("/api/units", params={"price_dropped": "true"}).json()
        assert {u["id"] for u in dropped["items"]} == {3, 4}
        assert client.get("/api/units/3").json()["unit"]["price_change"]["from"] == 5_500_000


def test_the_weekly_content_brief_writes_posts_cards_and_tracked_links(database, tmp_path):  # noqa: F811
    from datetime import date
    from qayem.content import build, write
    from qayem.website_data import Catalog

    snapshot = Catalog(database, 0, None).snapshot()
    stories = build(snapshot, today=date(2026, 11, 23))
    result = write(stories, tmp_path / "brief", date(2026, 11, 23))
    assert result["stories"] == len(stories) >= 2 and result["campaign"] == "brief-2026-w48"
    brief = (tmp_path / "brief" / "brief.md").read_text()
    assert "utm_campaign=brief-2026-w48-1" in brief and "#قيّم" in brief
    cards = sorted((tmp_path / "brief" / "cards").glob("*.svg"))
    assert len(cards) == len(stories) and all(card.read_text().startswith("<svg") for card in cards)
    assert json.loads((tmp_path / "brief" / "brief.json").read_text())[0]["link"].startswith("https://qayem.ai/units")

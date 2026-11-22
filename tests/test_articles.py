"""The article agent's fact check, gates and triggers, and the editorial API (articles, observations, WhatsApp)."""
from datetime import date
import hashlib
import hmac
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from qayem import articles
from qayem.editorial import editorial_router
from qayem.growth import Growth, LocalDatabase, Settings

TOKEN = "t" * 40


def pack() -> articles.Pack:
    figures = [articles.Figure("place", "place", "New Cairo", "text"),
               articles.Figure("headline.median_ppm", "median", 66_800, "egp_per_m2", "x", 3117),
               articles.Figure("headline.p25_ppm", "p25", 52_400, "egp_per_m2"),
               articles.Figure("headline.count", "count", 3117, "count"),
               articles.Figure("headline.median_price", "price", 9_720_000, "egp"),
               articles.Figure("headline.confidence", "confidence", "high", "text"),
               articles.Figure("compound_vs_district", "gap", -0.1234, "share", new=True)]
    trigger = articles.Trigger("guide", "guide:district:new-cairo:2026-11", 4, {})
    return articles.Pack(trigger, "x", "/districts/new-cairo", {"start": "2026-10-23", "end": "2026-11-22"}, figures, [], {})


def draft(text_ar: str, text_en: str) -> dict:
    filler_ar = " الأرقام متوسطات الإعلانات المرصودة خلال الفترة بعد حذف المكرر." * 14
    filler_en = " Figures are medians of the listings observed in the period, with duplicates removed." * 12
    return {"ar": {"title": "سعر المتر في القاهرة الجديدة", "summary": "حوالي 66.8 ألف جنيه",
                   "blocks": [{"type": "p", "text": text_ar}, {"type": "h2", "text": "كم السعر؟"},
                              {"type": "p", "text": filler_ar}]},
            "en": {"title": "New Cairo prices", "summary": "About 66,800 pounds per m²",
                   "blocks": [{"type": "p", "text": text_en}, {"type": "h2", "text": "How much?"},
                              {"type": "p", "text": filler_en}]}}


def test_numbers_are_read_in_both_scripts():
    assert articles.numbers_in("٦٦٫٨ ألف و3,117 إعلان في 2026") == [66.8, 3117, 2026]
    assert articles.numbers_in("66,800 pounds, 12%") == [66800, 12]


def test_every_number_must_come_from_the_pack():
    p = pack()
    ok = draft("سعر المتر حوالي ٦٦٫٨ ألف جنيه (نوفمبر 2026) من 3,117 إعلان، أرخص 12% من المنطقة، والوحدة 9.72 مليون.",
               "About 66,800 pounds per m² in November 2026 from 3,117 listings, 12% below the district; 9.7 million.")
    assert articles.fact_check(ok["ar"], p) == [] and articles.fact_check(ok["en"], p) == []
    assert articles.gates(ok, p) == []
    wrong = draft("سعر المتر حوالي 71 ألف جنيه.", "About 71,000 pounds per m², up 15% by 2028.")
    reasons = articles.gates(wrong, p)
    assert any("numbers not in the data pack: 71" in r for r in reasons)
    assert any("2028" in r for r in reasons)


def test_gates_reject_advice_loaded_words_links_and_nothing_new():
    p = pack()
    base = "سعر المتر حوالي 66.8 ألف جنيه، أرخص 12% من المنطقة."
    assert any("advice" in r for r in articles.gates(draft(base + " اشتر الآن.", "66,800 pounds, 12% below."), p))
    assert any("loaded" in r for r in articles.gates(draft(base, "66,800 pounds, 12% below; the developer is a scam."), p))
    assert any("link" in r for r in articles.gates(draft(base, "66,800 pounds, 12% below. See www.example.com."), p))
    assert any("adds no figure" in r for r in articles.gates(draft("سعر المتر 66.8 ألف جنيه.", "66,800 pounds."), p))
    english = draft(base, "66,800 pounds, 12% below.")
    english["ar"] = english["en"]
    assert any("ar: written in the wrong language" in r for r in articles.gates(english, p))


def test_triggers_skip_what_was_published_and_rotate_the_calendar():
    head = {"count": 400, "confidence": "high"}
    data = {"index": {"month": "2026-11"}, "overview": {}, "guide": {"moves": []}, "developers": [],
            "compounds": [{"key": "badya", "guide": {"headline": head}}, {"key": "tiny", "guide": {"headline": {
                "count": 5, "confidence": "high"}}}],
            "districts": [{"key": "new-cairo", "headline": head}]}
    keys = [t.key for t in articles.triggers(data, [], date(2026, 11, 22))]
    assert keys[0] == "index:2026-11" and "guide:compound:tiny:2026-11" not in keys
    recent = [{"trigger_key": "index:2026-11", "published_at": "2026-11-20T00:00:00"},
              {"trigger_key": "guide:compound:badya:2026-10", "published_at": "2026-10-30T00:00:00"}]
    keys = [t.key for t in articles.triggers(data, recent, date(2026, 11, 22))]
    assert keys == ["guide:district:new-cairo:2026-11"]  # Badya was reported 23 days ago


def app_with(tmp_path: Path) -> tuple[TestClient, LocalDatabase]:
    leads = LocalDatabase(tmp_path / "leads.db")
    settings = Settings(admin_token=TOKEN, whatsapp_verify_token="verify", whatsapp_app_secret="secret")

    async def resolve(request: Request):
        return Growth(leads, None, settings, None, ip="1.2.3.4", user_agent="Mozilla/5.0 (iPhone)")
    app = FastAPI()
    app.include_router(editorial_router(resolve))
    return TestClient(app), leads


def test_articles_publish_list_and_unpublish(tmp_path: Path):
    client, _ = app_with(tmp_path)
    body = {"slug": "guide-district-new-cairo-2026-11", "lang": "ar", "kind": "guide", "title": "سعر المتر",
            "summary": "حوالي 66.8 ألف", "trigger_key": "guide:district:new-cairo:2026-11",
            "blocks": [{"type": "p", "text": "<script>x</script> نص"}, {"type": "table", "columns": ["a"], "rows": [[1]]}],
            "meta": {"district": {"key": "new-cairo", "name": "New Cairo"}}}
    assert client.post("/api/admin/articles", json=body).status_code == 401
    published = client.post("/api/admin/articles", json=body, headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert published["ok"] and "token=" in published["unpublish"]
    listed = client.get("/api/articles?lang=ar").json()
    assert listed["total"] == 1 and listed["items"][0]["district"]["key"] == "new-cairo"
    article = client.get(f"/api/articles/{body['slug']}").json()
    assert "<" not in article["blocks"][0]["text"] and article["byline"] == "Qayem data desk"
    link = published["unpublish"].removeprefix("https://qayem.ai")
    assert "button" in client.get(link).text  # a link preview cannot unpublish
    assert client.get(f"/api/articles/{body['slug']}").status_code == 200
    assert client.post(link.replace("token=", "token=x")).status_code == 404
    assert "Unpublished" in client.post(link).text
    assert client.get(f"/api/articles/{body['slug']}").status_code == 404


def test_observations_and_the_whatsapp_webhook(tmp_path: Path):
    client, leads = app_with(tmp_path)
    assert client.post("/api/observations", json={"kind": "quoted_over", "compound": "badya", "area_m2": 150,
                                                   "price": 9_000_000, "over": 1_500_000}).json()["stored"]
    assert client.post("/api/observations", json={"kind": "quoted_over"}).status_code == 422
    assert client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify&hub.challenge=42").text == "42"
    assert client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=no&hub.challenge=42").status_code == 403
    message = {"id": "wamid.1", "from": "201012345678", "type": "text",
               "text": {"body": "باديا شقة 150م 9 مليون أوفر 1.5 مليون للتواصل 01012345678"}}
    payload = json.dumps({"entry": [{"changes": [{"value": {"messages": [message]}}]}]}).encode()
    signature = "sha256=" + hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    assert client.post("/api/whatsapp/webhook", content=payload, headers={"x-hub-signature-256": "sha256=bad"}).status_code == 403
    assert client.post("/api/whatsapp/webhook", content=payload, headers={"x-hub-signature-256": signature}).json()["stored"] == 1
    inbox = client.get("/api/admin/inbox", headers={"Authorization": f"Bearer {TOKEN}"}).json()["items"]
    assert "01012345678" not in inbox[0]["text"] and "[number withheld]" in inbox[0]["text"]
    auth = {"Authorization": f"Bearer {TOKEN}"}
    rows = [{"compound": "badya", "property_type": "apartment", "area_m2": 150, "price": 9_000_000, "over": 1_500_000}]
    client.post(f"/api/admin/inbox/{inbox[0]['id']}", json={"action": "extracted", "rows": rows}, headers=auth)
    assert client.post(f"/api/admin/inbox/{inbox[0]['id']}", json={"action": "accept"}, headers=auth).json()["accepted"] == 1
    totals = client.get("/api/admin/observations", headers=auth).json()
    assert totals["all_time"] == 2

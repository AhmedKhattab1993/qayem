"""Economic and market signals: Claude CLI extraction, source checks, storage, publication and article triggers."""
from datetime import date
import io
import json
from pathlib import Path
import sqlite3

import httpx
import pytest

from qayem import articles, claude_cli, signals

TODAY = date(2026, 11, 25)


# --- the Claude CLI step -------------------------------------------------------------------------

SCHEMA = {"type": "object", "required": ["k21"], "additionalProperties": False,
          "properties": {"k21": {"type": "number"}}}


def result(output, model="claude-opus-5-5", **overrides) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "structured_output": output,
                       "modelUsage": {model: {"outputTokens": 10}}, **overrides})


def test_the_cli_runs_opus_at_medium_effort_with_no_tools(monkeypatch):
    monkeypatch.setattr(claude_cli.shutil, "which", lambda name: "/usr/bin/claude")
    command = claude_cli.command(SCHEMA, "Read the gold page.")
    assert command[:2] == ["/usr/bin/claude", "-p"]
    pairs = dict(zip(command, command[1:]))
    assert pairs["--model"] == "claude-opus-5-5" and pairs["--effort"] == "medium"
    assert pairs["--tools"] == "" and pairs["--setting-sources"] == "" and pairs["--output-format"] == "json"
    assert "--strict-mcp-config" in command and "--no-session-persistence" in command
    assert json.loads(pairs["--json-schema"]) == SCHEMA


def test_the_answer_must_be_opus_and_match_the_schema():
    assert claude_cli.answer(result({"k21": 5535}), SCHEMA) == {"k21": 5535}
    with pytest.raises(RuntimeError, match="unexpected model"):
        claude_cli.answer(result({"k21": 1}, model="claude-haiku-5-5"), SCHEMA)
    with pytest.raises(RuntimeError, match="schema"):
        claude_cli.answer(result({"k21": "a lot"}), SCHEMA)
    with pytest.raises(RuntimeError, match="did not finish"):
        claude_cli.answer(result(None, is_error=True, subtype="error_max_budget_usd"), SCHEMA)
    with pytest.raises(claude_cli.ClaudeUnavailable, match="not signed in"):
        claude_cli.answer(result(None, is_error=True, result="Not logged in · Please run /login"), SCHEMA)
    with pytest.raises(RuntimeError, match="no JSON"):
        claude_cli.answer("Not logged in", SCHEMA)


def test_a_missing_cli_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(claude_cli.shutil, "which", lambda name: None)
    with pytest.raises(claude_cli.ClaudeUnavailable):
        claude_cli.extract("text", SCHEMA, "x")


def test_figures_are_kept_only_when_written_in_the_source():
    text = "عيار 21 ٥٥١٠ 5,560 +0.2% and remittances of 12,361.5 in the quarter"
    assert claude_cli.numbers(text) == [21, 5510, 5560, 0.2, 12361.5]
    assert claude_cli.number_in(5560, text) and claude_cli.number_in(12361.5, text) and not claude_cli.number_in(5561, text)
    assert claude_cli.quoted("remittances of 12,361.5", text) and not claude_cli.quoted("remittances of 13,000", text)
    assert claude_cli.checked({"value": 12361.5, "quote": "remittances of 12,361.5"}, text)
    assert not claude_cli.checked({"value": 12000, "quote": "remittances of 12,361.5"}, text)  # number not in quote
    assert claude_cli.page_text("<p>Hi <script>x()</script><b>there</b></p>") == "Hi there"


def test_capmas_periods():
    assert signals.capmas_period("اكتوبر 2026") == "2026-10"
    assert signals.capmas_period("الربع الثانى 2026") == "2026-Q2"
    assert signals.capmas_period("2025") == "2025"
    assert signals.month_period("2026-6") == "2026-06" and signals.month_period("June 2026") is None
    assert signals.quarter_of("2026-06") == "2026-Q2"


# --- every source, end to end, with a fake network and a fake Claude -----------------------------

def workbook() -> bytes:
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "2025-2026"
    sheet.append(["Balance of Payments"])
    sheet.append([None, None, "July/Sep 2025*", "Oct./Dec. 2025*", "Jan/March 2026*", "April/June 2026*"])
    sheet.append(["منها: تحويلات العاملين", "of which: Workers' remittances", 10807.5, 11319, 12779.3, 12361.5])
    sheet.append(["الاستثمار المباشر", "Direct Investment In Egypt (net)", 2405.9, 6865.9, 3765.8, 4961.4])
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


RENT_TEXT = ("The median rent in Giza was LE 8,000 per month during the third quarter of 2026, while the monthly rent "
             "was LE 60 LE/Sq M. Monthly rents ranged from 44 LE/Sq M. in Poulaq Al-Dakrour neighbourhood to 179 LE/Sq M. "
             "in Dokki neighbourhood.")
FRA_TEXT = "Mortgage finance reached EGP 7.3 billion in January and February 2026, granted to 2,154 clients."
OFFER_TEXT = "NUCA offers a residential plot in New Cairo at EGP 5,480 per square metre for developers."
NEWS_TITLE = "Top 10 developers' sales reach EGP 1.065trn in 9M 2026, up 2%"


def routes(request: httpx.Request) -> httpx.Response:
    url, host = str(request.url), request.url.host
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if host == "www.capmas.gov.eg" and "SelectedIndicator" in url:
        return httpx.Response(200, json={"data": [
            {"title": "معدل التضخم السنوى", "unit": "%", "studyPeriod": "اكتوبر 2026", "value": 12.0,
             "selectedIndicatorTranslations": [{"title": "Annually inflation rate %", "locale": "en"}]},
            {"title": "الواردات", "unit": "مليون دولار", "studyPeriod": "أغسطس 2026", "value": 11071.01,
             "selectedIndicatorTranslations": [{"title": "Foreign Trade - Imports", "locale": "en"}]}]})
    if host == "www.capmas.gov.eg" and "GetHomeCalendar" in url:
        return httpx.Response(200, json={"data": [{"date": "2026-11-29T00:00:00", "publication": {
            "id": 7, "name": "x", "publicationTranslations": [{"name": "Social Services Statistics"}]}}]})
    if host == "p2p.binance.com":
        side = json.loads(request.content)["tradeType"]
        base = 55.5 if side == "BUY" else 55.1
        return httpx.Response(200, json={"data": [{"adv": {"price": f"{base + i / 100:.2f}"}} for i in range(5)]})
    if host == "api.worldbank.org":
        return httpx.Response(200, json=[{"page": 1}, [{"date": "2025", "value": None}, {"date": "2024", "value": 28.3}]])
    if host == "api.db.nomics.world":
        return httpx.Response(200, json={"series": {"docs": [{"period": ["2025-04", "2025-05"], "value": [24.0, "NA"]}]}})
    if host == "www.isagha.com":
        return httpx.Response(200, text="<p>العيار شراء بيع عيار 21 5510 5560 +0.2% عيار 24 6297.25 6354.25</p>")
    if host == "www.newcities.gov.eg":
        return httpx.Response(200, text='<a href="/news/9">طرح أراضي سكنية بمدينة بدر</a> نتيجة القرعة العلنية')
    if host == "www.cbe.org.eg" and "downloadlist" in url:
        return httpx.Response(200, text='<a href="/-/media/bop/bop_quarter-2024--2025-.xlsx">a</a>'
                                        '<a href="/-/media/bop/bop_quarter-2025-2026_.xlsx">b</a>'
                                        '<a href="/-/media/bop/bop-annual___.xlsx">c</a>')
    if host == "www.cbe.org.eg" and url.endswith("2025-2026_.xlsx"):
        return httpx.Response(200, content=workbook())
    if host == "marsadomran.info":
        return httpx.Response(200, json=[{"id": 1, "date": "2026-11-23T10:00:00", "link": "https://marsadomran.info/giza",
                                          "title": {"rendered": "Giza Rent Price Index"},
                                          "content": {"rendered": f"<p>{RENT_TEXT}</p>"}}])
    if host == "fra.gov.eg":
        return httpx.Response(200, json=[{"id": 2, "link": "https://fra.gov.eg/en/mortgage", "title": {"rendered": "FRA stats"},
                                          "content": {"rendered": f"<p>{FRA_TEXT}</p>"}},
                                         {"id": 3, "link": "https://fra.gov.eg/en/licences", "title": {"rendered": "Licences"},
                                          "content": {"rendered": "<p>FRA licensed 6 companies.</p>"}}])
    if host == "blogs.realestate.gov.eg":
        return httpx.Response(200, json=[{"id": 5, "link": "https://blogs.realestate.gov.eg/news/new-cairo-land/",
                                          "title": {"rendered": "NUCA land in New Cairo"},
                                          "content": {"rendered": f"<p>{OFFER_TEXT}</p>"}, "date": "2026-11-20T10:00:00"}])
    if host == "www.dailynewsegypt.com":
        return httpx.Response(200, text=f"""<rss><channel><item><title>{NEWS_TITLE}</title>
            <link>https://www.dailynewsegypt.com/2026/11/24/sales/</link><pubDate>Tue, 24 Nov 2026 10:00:00 +0000</pubDate>
            <description>Contracted sales of 73,920 units.</description></item>
            <item><title>Old story</title><link>https://www.dailynewsegypt.com/old/</link>
            <pubDate>Tue, 03 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>""")
    return httpx.Response(403)  # every other feed refuses: it is skipped, never retried another way


class FakeClaude:
    """Answers each source's instructions as Claude would, including one figure it invented."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text: str, schema: dict, instructions: str) -> dict:
        self.calls.append(next(k for k in ("gold dealer", "(هيئة", "balance of payments", "rent price index",
                                           "Financial Regulatory", "real-estate platform", "screen news") if k in instructions))
        if "gold dealer" in instructions:
            return {"prices": [{"item": "21k", "buy": 5510, "sell": 5560, "quote": "عيار 21 5510 5560"},
                               {"item": "18k", "buy": 4700, "sell": 4750, "quote": "عيار 18 4700 4750"}]}  # not on the page
        if "New Urban Communities Authority (هيئة" in instructions:
            return {"notices": [{"title": "طرح أراضي سكنية بمدينة بدر", "kind": "land_offer",
                                 "link": "http://www.newcities.gov.eg/news/9", "quote": "طرح أراضي سكنية بمدينة بدر"}]}
        if "balance of payments" in instructions:
            return {"quarter_end_month": "2026-06", "figures": [
                {"name": "workers_remittances", "value": 12361.5,
                 "quote": "منها: تحويلات العاملين | of which: Workers' remittances | 10807.5 | 11319 | 12779.3 | 12361.5"},
                {"name": "current_account", "value": -7883.8, "quote": "Current Account Balance | -7883.8"}]}
        if "rent price index" in instructions:
            return {"city": "Giza", "quarter_end_month": "2026-09", "figures": [
                {"name": "median_rent_month", "area": "city", "value": 8000, "quote": "The median rent in Giza was LE 8,000 per month"},
                {"name": "rent_per_m2_month", "area": "city", "value": 60, "quote": "the monthly rent was LE 60 LE/Sq M"},
                {"name": "rent_per_m2_month", "area": "Dokki", "value": 179, "quote": "179 LE/Sq M. in Dokki"}]}
        if "Financial Regulatory Authority" in instructions:
            return {"posts": [{"post": 1, "period_end_month": "2026-02", "figures": [
                {"name": "mortgage_finance", "unit": "egp_bn", "value": 7.3, "basis": "year_to_date",
                 "quote": "Mortgage finance reached EGP 7.3 billion"},
                {"name": "mortgage_clients", "unit": "count", "value": 2154, "basis": "year_to_date",
                 "quote": "granted to 2,154 clients"}]}]}
        if "official real-estate platform" in instructions:
            return {"offers": [{"post": 1, "kind": "land_offer", "city": "New Cairo", "use": "residential", "figures": [
                {"name": "price_per_m2", "value": 5480, "quote": "at EGP 5,480 per square metre"}]}]}
        if "screen news items" in instructions:
            return {"events": [{"item": 1, "title_en": NEWS_TITLE, "summary_en": "Top-10 developers' sales rose 2%.",
                                "topic": "sales", "figures": [
                                    {"name": "sales", "label": "top-10 developers' contracted sales", "unit": "egp_trn",
                                     "value": 1.065, "quote": "EGP 1.065trn"},
                                    {"name": "growth", "label": "change on a year earlier", "unit": "percent", "value": 2,
                                     "quote": "up 2%"},
                                    {"name": "units", "label": "units sold", "unit": "count", "value": 73920,
                                     "quote": "73,920 units"}]}]}
        raise AssertionError(instructions)


def run(connection, claude, only=None):
    with httpx.Client(transport=httpx.MockTransport(routes)) as client:
        return {o["source"]: o for o in signals.run(connection, only=only, client=client, extract=claude, today=TODAY)}


def test_every_source_is_read_checked_and_stored(tmp_path: Path):
    claude = FakeClaude()
    with sqlite3.connect(tmp_path / "q.db") as connection:
        outcomes = run(connection, claude)
        assert all(o["status"] == "ok" for o in outcomes.values()), outcomes
        stored = {(n, p): v for n, p, v in connection.execute("SELECT name, period, value FROM market_signals")}
        assert stored[("capmas_inflation_annual", "2026-10")] == 12.0
        assert stored[("capmas_imports", "2026-08")] == 11071.01
        assert stored[("usdt_egp_p2p_buy", "2026-11-25")] == 55.52 and stored[("usdt_egp_p2p_sell", "2026-11-25")] == 55.12
        assert stored[("usdt_egp_p2p", "2026-11-25")] == 55.32
        assert stored[("wb_inflation", "2024")] == 28.3 and stored[("imf_policy_rate", "2025-04")] == 24.0
        assert stored[("gold_21k", "2026-11-25")] == 5535 and not any(n == "gold_18k" for n, _ in stored)  # invented: dropped
        assert stored[("cbe_bop_workers_remittances", "2026-Q2")] == 12361.5
        assert not any(n == "cbe_bop_current_account" for n, _ in stored)  # its quote is not a row of the sheet
        assert stored[("rent_median_rent_month:giza:giza", "2026-Q3")] == 8000
        assert stored[("rent_rent_per_m2_month:giza:dokki", "2026-Q3")] == 179
        assert stored[("fra_mortgage_finance_year_to_date", "2026-02")] == 7300
        assert stored[("fra_mortgage_clients_year_to_date", "2026-02")] == 2154
        assert stored[("nuca_land_ppm:new-cairo:residential", "2026-11")] == 5480
        events = {k: kind for k, kind in connection.execute("SELECT key, kind FROM market_events")}
        assert sorted(set(events.values())) == ["capmas_release", "fra_statistics", "land_offer", "news", "nuca_notice",
                                                "rent_index"]
        assert outcomes["news"]["events"] == 1 and "Enterprise: Blocked" in outcomes["news"]["note"]
        first = len(claude.calls)
        again = run(connection, claude)
        # Unchanged documents are not sent again: only the gold page (prices change daily) is re-read.
        assert claude.calls[first:] == ["gold dealer"] and again["nuca"]["note"] == "unchanged"


def test_without_claude_the_structured_sources_still_run(tmp_path: Path):
    def missing(*_):
        raise claude_cli.ClaudeUnavailable("the Claude CLI is not installed")
    with sqlite3.connect(tmp_path / "q.db") as connection:
        outcomes = run(connection, missing)
        assert outcomes["capmas"]["status"] == outcomes["binance"]["status"] == "ok"
        assert all(outcomes[name]["status"] == "skipped" for name in signals.READ_BY_CLAUDE)


def test_published_signals_and_their_articles(tmp_path: Path):
    with sqlite3.connect(tmp_path / "q.db") as connection:
        run(connection, FakeClaude())
        published = signals.published(connection, TODAY)
    assert published["latest"]["usdt_egp_p2p"]["value"] == 55.32
    assert published["calendar"] == [{"day": "2026-11-29", "title": "Social Services Statistics", "source": "CAPMAS"}]
    kinds = {e["kind"] for e in published["events"]}
    assert "capmas_release" not in kinds and {"rent_index", "news"} <= kinds
    data = {"overview": {"signals": published}, "districts": [
        {"key": "mohandessin-dokki", "name": "Mohandessin & Dokki", "name_ar": "المهندسين والدقي",
         "headline": {"class": "apartment", "median_ppm": 71_600, "count": 140, "confidence": "high"}}]}
    found = {t.kind: t for t in articles.triggers(data, [], TODAY)}
    assert {"rent_index", "market_news"} <= set(found)
    rent = articles.rent_pack(found["rent_index"], data, None)
    gross = next(f for f in rent.figures if f.id == "yield.mohandessin-dokki.Dokki")
    assert gross.value == round(179 * 12 / 71_600, 4) and gross.new and rent.path == "/districts/mohandessin-dokki"
    assert rent.tables[0]["rows"] == [["Dokki", "Mohandessin & Dokki", "المهندسين والدقي", 179, 71_600, gross.value]]
    news = articles.news_pack(found["market_news"], data, None)
    assert any(f.value == 1.065 for f in news.figures) and news.context["source"] == "reported by Daily News Egypt"
    draft = {"title": "x", "summary": "y", "blocks": [{"type": "p", "text": "Sales reached EGP 1.065 trillion, up 2%, "
                                                                            "on 73,920 units in 2026."}]}
    assert articles.fact_check(draft, news) == []
    assert articles.fact_check({**draft, "blocks": [{"type": "p", "text": "Sales of 1.2 trillion."}]}, news) == ["1.2"]

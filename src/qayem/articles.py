"""The article agent: data stories written from Qayem's published figures, with no approval step.

    trigger → data pack → draft → fact check → quality gates → publish → distribute

It runs on the operator's machine (`qayem articles run`, scheduled daily), because the drafting model
is the local Antigravity CLI (`agy`, Gemini 4 Neon at medium effort; owner decision 2026-11-22).

- Triggers: the monthly index, a CBE rate decision, a new rent index edition (with the gross yield
  against Qayem's prices), a segment that moved ±5% in 30 days, a developer whose list prices moved,
  property news with figures (from `signals`), and otherwise the calendar: a compound or district
  report, rotated by size.
- The data pack is every figure the article may use, read from the live public API, with its period
  and listing count. Derived figures (gaps, ranks) are computed here, never by the model.
- The model writes Arabic and English from the pack. The fact check rejects any number in the text
  that is not in the pack; the gates reject advice, loaded words about developers, links to other
  sites, thin data and drafts that add nothing to the guide page. A rejected draft is logged with its
  reason and never published (docs/STRATEGY.md, 8).
- Volume is capped: at most one article pair a run and four a rolling week (8.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable

import httpx

AGY_MODEL = os.environ.get("QAYEM_ARTICLE_MODEL", "gemini-4-neon")
AGY_EFFORT = os.environ.get("QAYEM_ARTICLE_EFFORT", "medium")
WEEKLY_CAP = 4
MAX_DRAFTS = 3  # model calls a run, published or not
CALENDAR_REPEAT_DAYS = 60  # a compound or district report is not repeated within two months
MIN_HEADLINE_COUNT = 20
RENT_DAYS = 45  # a new rent index edition is written about within six weeks
NEWS_DAYS = 7  # a news item with figures, within a week
CLASS_EN = {"apartment": "apartments", "chalet": "chalets", "house": "villas and houses"}
CLASS_AR = {"apartment": "الشقق", "chalet": "الشاليهات", "house": "الفيلات والمنازل"}
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December")
MONTHS_AR = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
             "ديسمبر")


# --- reading the published figures ------------------------------------------------------

class Site:
    """The live public API, and the admin endpoints for publishing (Bearer admin token)."""

    def __init__(self, base: str, token: str = "", client: httpx.Client | None = None):
        self.base, self.token = base.rstrip("/"), token
        self.client = client or httpx.Client(timeout=60, headers={"User-Agent": "Qayem-article-agent/1.0"})

    def get(self, path: str, admin: bool = False) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if admin else {}
        response = self.client.get(self.base + path, headers=headers)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, body: dict) -> dict:
        response = self.client.post(self.base + path, json=body, headers={"Authorization": f"Bearer {self.token}"})
        response.raise_for_status()
        return response.json()


# --- triggers -------------------------------------------------------------------------------

@dataclass
class Trigger:
    kind: str  # index | rates | move | developer_prices | guide
    key: str  # deduplication key, e.g. "guide:compound:badya:2026-11"
    priority: int
    subject: dict = field(default_factory=dict)


def month_of(day: str) -> str:
    return day[:7]


def label_month(day: str, lang: str) -> str:
    names = MONTHS_AR if lang == "ar" else MONTHS_EN
    return f"{names[int(day[5:7]) - 1]} {day[:4]}"


def triggers(data: dict, recent: list[dict], today: date) -> list[Trigger]:
    """Candidates, best first; ones already published (same key) are dropped."""
    done = {item["trigger_key"] for item in recent}
    published_days = {item["trigger_key"]: item["published_at"][:10] for item in recent}
    out: list[Trigger] = []
    edition = data.get("index") or {}
    if edition.get("month"):
        out.append(Trigger("index", f"index:{edition['month']}", 0, {"month": edition["month"]}))
    rates = (data.get("overview") or {}).get("rates") or {}
    deposit, previous = (rates.get("key") or {}).get("overnight_deposit"), rates.get("previous_overnight_deposit")
    if deposit and previous and deposit["value"] != previous["value"]:
        changed = date.fromisoformat(deposit["day"]) if deposit.get("day") else today
        if (today - changed).days <= 14:
            out.append(Trigger("rates", f"rates:{deposit['day']}", 1, {"from": previous, "to": deposit}))
    seen_reports = set()
    for report in (data.get("overview") or {}).get("developer_reports") or []:
        names = {f["name"] for f in report["figures"]}
        key = f"report:{report['developer']}:{report.get('period')}"
        fetched = date.fromisoformat(report["fetched_at"][:10])
        if (report.get("period") and key not in seen_reports and (today - fetched).days <= 45
                and names & {"contracted_sales", "units_sold", "net_sales"}):
            seen_reports.add(key)
            out.append(Trigger("developer_report", key, 1, {"developer": report["developer"], "period": report["period"]}))
    signals = (data.get("overview") or {}).get("signals") or {}
    for event in signals.get("events") or []:
        age = (today - date.fromisoformat(event["day"])).days if event.get("day") else 999
        figures = [f for f in event.get("figures") or [] if f.get("checked")]
        if event["kind"] == "rent_index" and age <= RENT_DAYS and len(figures) >= 2:
            out.append(Trigger("rent_index", event["key"], 2, event))
        elif event["kind"] == "news" and age <= NEWS_DAYS and len(figures) >= 2:
            out.append(Trigger("market_news", event["key"], 3, {**event, "count": len(figures)}))
    for move in (data.get("guide") or {}).get("moves", [])[:5]:
        out.append(Trigger("move", f"move:{move['key']}:{move['to_day'][:7]}", 2, move))
    for developer in data.get("developers", []):
        history = developer.get("history") or {}
        change = history.get("developer_change_60d")
        if change is not None and abs(change) >= 0.03 and (history.get("developer_tracked") or 0) >= 20:
            out.append(Trigger("developer_prices", f"developer:{developer['key']}:{today:%Y-%m}", 3,
                               {"key": developer["key"]}))
    month = today.strftime("%Y-%m")
    for gap in data.get("search_gaps") or []:
        level, key = gap.get("level"), gap.get("key")
        query = (gap.get("query") or "").strip()
        if level in ("district", "compound") and key and query:
            out.append(Trigger("search_gap", f"search:{level}:{key}:{month}", 3,
                               {"level": level, "key": key, "query": query,
                                "count": int(gap.get("impressions") or 0)}))
    for compound in data.get("compounds", []):
        head = (compound.get("guide") or {}).get("headline")
        if head and head["count"] >= MIN_HEADLINE_COUNT and head["confidence"] != "indicative":
            out.append(Trigger("guide", f"guide:compound:{compound['key']}:{month}", 4,
                               {"level": "compound", "key": compound["key"], "count": head["count"]}))
    for district in data.get("districts", []):
        head = district.get("headline")
        if head and head["count"] >= MIN_HEADLINE_COUNT and head["confidence"] != "indicative":
            out.append(Trigger("guide", f"guide:district:{district['key']}:{month}", 4,
                               {"level": "district", "key": district["key"], "count": head["count"] * 2}))

    def repeated(trigger: Trigger) -> bool:
        if trigger.key in done:
            return True
        if trigger.kind == "guide":  # the same subject in another month, too recently
            stem = trigger.key.rsplit(":", 1)[0]
            return any(k.rsplit(":", 1)[0] == stem and (today - date.fromisoformat(d)).days < CALENDAR_REPEAT_DAYS
                       for k, d in published_days.items())
        return False
    fresh = [t for t in out if not repeated(t)]
    return sorted(fresh, key=lambda t: (t.priority, -t.subject.get("count", 0)))


# --- data packs -------------------------------------------------------------------------------

@dataclass
class Figure:
    id: str
    label: str
    value: float | int | str
    unit: str  # egp | egp_per_m2 | share | count | m2 | percent_points | text | date
    period: str = ""
    count: int | None = None
    new: bool = False  # not shown on the guide page as such: the article's own contribution

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", False) or k in ("value",)}


@dataclass
class Pack:
    trigger: Trigger
    title_hint: str
    path: str  # the guide page the article is tied to
    period: dict
    figures: list[Figure]
    tables: list[dict]
    context: dict
    district: dict | None = None
    compound: dict | None = None

    def as_dict(self) -> dict:
        return {"trigger": self.trigger.kind, "subject_page": self.path, "period": self.period,
                "figures": [f.as_dict() for f in self.figures], "tables": self.tables, "context": self.context}


def _seg_figures(prefix: str, label: str, segment: dict, period: str) -> list[Figure]:
    out = [Figure(f"{prefix}.median_ppm", f"{label}: median asking price per m²", segment["median_ppm"], "egp_per_m2",
                  period, segment["count"]),
           Figure(f"{prefix}.p25_ppm", f"{label}: lower quartile price per m²", segment["p25_ppm"], "egp_per_m2", period),
           Figure(f"{prefix}.p75_ppm", f"{label}: upper quartile price per m²", segment["p75_ppm"], "egp_per_m2", period),
           Figure(f"{prefix}.count", f"{label}: listings behind the figure", segment["count"], "count", period),
           Figure(f"{prefix}.confidence", f"{label}: confidence", segment["confidence"], "text")]
    if segment.get("median_price"):
        out.append(Figure(f"{prefix}.median_price", f"{label}: median asking price", segment["median_price"], "egp", period))
    if segment.get("median_area"):
        out.append(Figure(f"{prefix}.median_area", f"{label}: median size", segment["median_area"], "m2", period))
    if segment.get("median_cash_ppm"):
        out.append(Figure(f"{prefix}.median_cash_ppm", f"{label}: median price per m² in today's money (instalments "
                          "discounted)", segment["median_cash_ppm"], "egp_per_m2", period))
    if segment.get("resale_vs_new") is not None:
        out.append(Figure(f"{prefix}.resale_vs_new", f"{label}: resale against buying from the developer, in today's "
                          "money with both sides' instalments discounted (negative: resale cheaper)", segment["resale_vs_new"],
                          "share", period))
    if segment.get("list_price_gap") is not None:
        out.append(Figure(f"{prefix}.list_price_gap", f"{label}: resale asking price per m² against developers' list "
                          "price per m², before discounting instalments (negative: resale cheaper)", segment["list_price_gap"],
                          "share", period))
    if segment.get("developer"):
        out.append(Figure(f"{prefix}.developer_ppm", f"{label}: developers' median list price per m² today",
                          segment["developer"]["median_ppm"], "egp_per_m2", period, segment["developer"]["count"]))
    if segment.get("plan_share") is not None:
        out.append(Figure(f"{prefix}.plan_share", f"{label}: share listed with an instalment plan", segment["plan_share"],
                          "share", period))
    sources = segment.get("sources") or []
    out.append(Figure(f"{prefix}.sources", f"{label}: number of sources", len(sources), "count"))
    return out


def _size_table(segments: list[dict], lang_label: str) -> dict:
    rows = [[s["size"], s["median_ppm"], s["p25_ppm"], s["p75_ppm"], s["count"]] for s in segments
            if s["size"] != "*" and s["delivery"] == "*"]
    return {"id": f"sizes.{lang_label}", "columns": ["size_m2", "median_ppm", "p25_ppm", "p75_ppm", "listings"], "rows": rows}


def guide_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    level, key = trigger.subject["level"], trigger.subject["key"]
    if level == "compound":
        entry = site.get(f"/api/compounds/{key}")
        compound, district = entry["compound"], entry.get("district") or {}
        segments = (compound.get("guide") or {}).get("segments", [])
        name, name_ar = compound["name"], compound.get("name_ar") or compound["name"]
        path = f"/compounds/{key}"
    else:
        district = site.get(f"/api/districts/{key}")
        compound = None
        segments = [s for s in (district.get("guide") or {}).get("segments", []) if s["compound"] in ("*", "outside")]
        name, name_ar = district["name"], district.get("name_ar") or district["name"]
        path = f"/districts/{key}"
    period = ((compound or district).get("guide") or {}).get("period") or {}
    stamp = f"{period.get('start')}/{period.get('end')}"
    tops = [s for s in segments if s["size"] == "*" and s["delivery"] == "*" and s["compound"] != "outside"]
    if not tops:
        return None
    head = next((s for s in tops if s["class"] == "apartment"), max(tops, key=lambda s: s["count"]))
    figures = [Figure("place", "place", name, "text"), Figure("place_ar", "place in Arabic", name_ar, "text"),
               Figure("class", "unit class", head["class"], "text")]
    figures += _seg_figures("headline", f"{CLASS_EN[head['class']]} in {name}", head, stamp)
    for other in tops:
        if other is not head:
            figures += _seg_figures(other["class"], f"{CLASS_EN[other['class']]} in {name}", other, stamp)
    for s in segments:
        if s["class"] == head["class"] and s["delivery"] in ("ready", "under_2y", "later") and s["size"] == "*":
            figures.append(Figure(f"delivery.{s['delivery']}.median_ppm", f"{CLASS_EN[head['class']]} delivering "
                                  f"{s['delivery'].replace('_', ' ')}: median price per m²", s["median_ppm"], "egp_per_m2",
                                  stamp, s["count"]))
    context: dict = {}
    if level == "compound":
        district_head = ((district.get("guide") or {}).get("headline")) or {}
        if district_head.get("class") == head["class"] and district_head.get("median_ppm"):
            gap = head["median_ppm"] / district_head["median_ppm"] - 1
            figures += [Figure("district", "district", district.get("name") or "", "text"),
                        Figure("district_ar", "district in Arabic", district.get("name_ar") or "", "text"),
                        Figure("district.median_ppm", f"{CLASS_EN[head['class']]} across the district: median price per m²",
                               district_head["median_ppm"], "egp_per_m2", stamp, district_head["count"]),
                        Figure("compound_vs_district", "this compound against its district's median (negative: cheaper)",
                               round(gap, 4), "share", stamp, new=True)]
            peers = [s for s in (district.get("guide") or {}).get("segments", []) if s["class"] == head["class"]
                     and s["compound"] not in ("*", "outside") and s["size"] == "*" and s["count"] >= 10]
            if len(peers) >= 3:
                ranked = sorted(peers, key=lambda s: s["median_ppm"])
                rank = next((i + 1 for i, s in enumerate(ranked) if s["compound"] == key), None)
                if rank:
                    figures += [Figure("rank_in_district", "rank by median price per m² among the district's compounds "
                                       "with 10+ listings (1 = cheapest)", rank, "count", stamp, new=True),
                                Figure("compounds_ranked", "compounds ranked", len(ranked), "count", stamp, new=True)]
    else:
        inside = [s for s in (district.get("guide") or {}).get("segments", []) if s["class"] == head["class"]
                  and s["compound"] not in ("*", "outside") and s["size"] == "*" and s["count"] >= 10]
        if len(inside) >= 3:
            ranked = sorted(inside, key=lambda s: s["median_ppm"])
            for tag, segment in (("cheapest", ranked[0]), ("dearest", ranked[-1])):
                figures += [Figure(f"{tag}_compound", f"{tag} compound by median price per m²",
                                   segment["compound_name"] or segment["compound"], "text", new=True),
                            Figure(f"{tag}_compound_ar", f"{tag} compound in Arabic",
                                   segment.get("compound_name_ar") or segment["compound_name"] or "", "text", new=True),
                            Figure(f"{tag}_compound.median_ppm", f"{tag} compound: median price per m²",
                                   segment["median_ppm"], "egp_per_m2", stamp, segment["count"], new=True)]
            spread = ranked[-1]["median_ppm"] / ranked[0]["median_ppm"] - 1
            figures.append(Figure("compound_spread", "dearest compound against the cheapest (median price per m²)",
                                  round(spread, 4), "share", stamp, new=True))
            figures.append(Figure("compounds_compared", "compounds compared", len(ranked), "count", stamp, new=True))
    rates = (data.get("overview") or {}).get("rates") or {}
    usd = (rates.get("egp_per") or {}).get("usd")
    if usd:
        figures += [Figure("egp_per_usd", "Central Bank of Egypt rate, EGP per US dollar", usd, "egp", rates.get("day", "")),
                    Figure("headline.median_ppm_usd", "headline median price per m² in US dollars",
                           round(head["median_ppm"] / usd), "usd_per_m2", stamp, new=True)]
    tables = [_size_table([s for s in segments if s["class"] == head["class"] and s["compound"] != "outside"], head["class"])]
    return Pack(trigger, f"{name}: what {CLASS_EN[head['class']]} cost", path, period, figures, tables, context,
                district={"key": district.get("key"), "name": district.get("name"), "name_ar": district.get("name_ar")}
                if district.get("key") else None,
                compound={"key": key, "name": name, "name_ar": name_ar} if level == "compound" else None)


def index_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    edition = data.get("index") or {}
    if not edition.get("districts"):
        return None
    stamp = f"{edition['period']['start']}/{edition['period']['end']}"
    figures = [Figure("month", "index month", edition["month"], "date"),
               Figure("districts", "districts with figures", len(edition["districts"]), "count", stamp),
               Figure("compounds", "compounds with figures", len(edition["compounds"]), "count", stamp),
               Figure("listings", "listings behind the index after removing duplicates", edition["counts"]["kept"], "count", stamp),
               Figure("duplicates", "duplicate listings removed across sources", edition["counts"]["duplicates"], "count",
                      stamp, new=True),
               Figure("segments_high", "segments published with high confidence", edition["counts"]["high"], "count", stamp)]
    rows = []
    for district in edition["districts"][:12]:
        row = next((c for c in district["classes"] if c["class"] == "apartment"), None)
        if row and row["confidence"] != "indicative":
            rows.append([district["name"], district.get("name_ar") or "", row["median_ppm"], row["p25_ppm"], row["p75_ppm"],
                         row["count"]])
            figures.append(Figure(f"apartments.{district['key']}.median_ppm", f"apartments in {district['name']}: median "
                                  "price per m²", row["median_ppm"], "egp_per_m2", stamp, row["count"]))
    if len(rows) < 3:
        return None
    ranked = sorted(rows, key=lambda r: r[2])
    figures += [Figure("cheapest_district", "cheapest of these districts for apartments", ranked[0][0], "text", new=True),
                Figure("dearest_district", "dearest of these districts for apartments", ranked[-1][0], "text", new=True),
                Figure("dearest_vs_cheapest", "dearest district against the cheapest", round(ranked[-1][2] / ranked[0][2] - 1, 4),
                       "share", stamp, new=True)]
    for change in edition.get("changes", [])[:5]:
        figures.append(Figure(f"change.{change['key']}.{change['class']}", f"{change['name']} {change['class']}: change "
                              "since the previous edition", change["change"], "share", stamp, change["count"], new=True))
    table = {"id": "districts", "columns": ["district", "district_ar", "median_ppm", "p25_ppm", "p75_ppm", "listings"],
             "rows": rows}
    return Pack(trigger, f"Qayem Index {edition['label']}", f"/index/{edition['month']}", edition["period"], figures,
                [table], {"provisional": edition.get("provisional", True)})


def move_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    move = trigger.subject
    district_key, compound, cls = move["key"].split("/")[:3]
    district = site.get(f"/api/districts/{district_key}")
    segment = next((s for s in (district.get("guide") or {}).get("segments", []) if s["key"] == move["key"]), None)
    if compound not in ("*", "outside"):
        entry = site.get(f"/api/compounds/{compound}")["compound"]
        segment = next((s for s in (entry.get("guide") or {}).get("segments", []) if s["key"] == move["key"]), segment)
    if segment is None:
        return None
    name = segment.get("compound_name") or segment["district_name"]
    name_ar = segment.get("compound_name_ar") or segment.get("district_name_ar") or name
    stamp = f"{move['from_day']}/{move['to_day']}"
    figures = [Figure("place", "place", name, "text"), Figure("place_ar", "place in Arabic", name_ar, "text"),
               Figure("class", "unit class", cls, "text"),
               Figure("from_ppm", f"median price per m² on {move['from_day']}", move["from"], "egp_per_m2", move["from_day"],
                      move["previous_count"], new=True),
               Figure("to_ppm", f"median price per m² on {move['to_day']}", move["to"], "egp_per_m2", move["to_day"],
                      move["count"]),
               Figure("change", "change over the period", move["change"], "share", stamp, new=True),
               Figure("from_day", "start date", move["from_day"], "date"), Figure("to_day", "end date", move["to_day"], "date")]
    figures += _seg_figures("now", f"{CLASS_EN.get(cls, cls)} in {name}", segment, stamp)
    path = f"/compounds/{compound}" if compound not in ("*", "outside") else f"/districts/{district_key}"
    return Pack(trigger, f"{name}: {CLASS_EN.get(cls, cls)} prices moved", path, {"start": move["from_day"],
                "end": move["to_day"]}, figures, [], {"note": "a move in asking prices, not in sale prices"},
                district={"key": district_key, "name": district.get("name"), "name_ar": district.get("name_ar")})


def developer_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    developer = site.get(f"/api/developers/{trigger.subject['key']}")
    history = developer.get("history") or {}
    launch = developer.get("launch") or {}
    if history.get("developer_change_60d") is None:
        return None
    stamp = "last 60 days"
    figures = [Figure("developer", "developer", developer["name"], "text"),
               Figure("developer_ar", "developer in Arabic", developer.get("name_ar") or developer["name"], "text"),
               Figure("change_60d", "average change in the developer's list prices for the same units over 60 days",
                      history["developer_change_60d"], "share", stamp, history.get("developer_tracked"), new=True),
               Figure("tracked", "developer units tracked", history.get("developer_tracked"), "count", stamp),
               Figure("rising", "units whose list price rose", history.get("developer_rising"), "count", stamp, new=True),
               Figure("falling", "units whose list price fell", history.get("developer_falling"), "count", stamp, new=True)]
    if launch.get("median_headline_ppm"):
        figures.append(Figure("developer_ppm", "developer's median list price per m² today", launch["median_headline_ppm"],
                              "egp_per_m2", "today", launch.get("units")))
    if launch.get("median_gap") is not None:
        figures.append(Figure("resale_gap", "the developer's resale units against its own prices today (negative: cheaper)",
                              launch["median_gap"], "share", "today", launch.get("compared")))
    rows = [[c["name"], c.get("name_ar") or "", c["units"]] for c in developer.get("compounds", [])[:8]]
    return Pack(trigger, f"{developer['name']} list prices", f"/developers/{developer['key']}", {"start": "", "end": ""},
                figures, [{"id": "compounds", "columns": ["compound", "compound_ar", "resale_units"], "rows": rows}],
                {"wording": "neutral: report the change, never judge the developer"})


def rates_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    before, after = trigger.subject["from"], trigger.subject["to"]
    overview = data.get("overview") or {}
    figures = [Figure("rate_before", "CBE overnight deposit rate before (percent)", before["value"], "percent_points",
                      before["day"]),
               Figure("rate_after", "CBE overnight deposit rate now (percent)", after["value"], "percent_points", after["day"]),
               Figure("rate_change", "change in percentage points", round(after["value"] - before["value"], 2),
                      "percent_points", after["day"], new=True),
               Figure("decision_day", "date the new rate was observed", after["day"], "date")]
    if overview.get("discount_rate") is not None:
        figures.append(Figure("qayem_discount_rate", "annual rate Qayem uses to express instalments in today's money",
                              overview["discount_rate"], "share"))
    if overview.get("plan_median_discount") is not None:
        figures.append(Figure("plan_discount", "median gap between an instalment plan's total and its value today",
                              overview["plan_median_discount"], "share", new=True))
    share = (overview.get("payment_terms") or {})
    known = sum(share.get(k, 0) for k in ("plan", "cash"))
    if known:
        figures.append(Figure("plan_share", "share of resale listings sold on instalments", round(share.get("plan", 0) / known, 4),
                              "share"))
    return Pack(trigger, "What the CBE's rate decision means for instalment buyers", "/methodology",
                {"start": before["day"], "end": after["day"]}, figures, [], {})


SIGNAL_UNITS = {"egp": ("egp", "EGP"), "egp_per_m2": ("egp_per_m2", "EGP per m²"), "egp_month": ("egp", "EGP a month"),
                "egp_per_m2_month": ("egp", "EGP per m² a month"), "percent": ("percent_points", "percent"),
                "egp_mn": ("number", "million EGP"), "egp_bn": ("number", "billion EGP"), "egp_trn": ("number", "trillion EGP"),
                "usd": ("egp", "US dollars"), "usd_mn": ("number", "million US dollars"),
                "usd_bn": ("number", "billion US dollars"), "count": ("count", ""), "m2": ("count", "m²")}


def _event_figure(figure: dict, period: str, prefix: str) -> Figure:
    unit = figure.get("unit") or ("percent" if figure["name"].endswith("_pct") else
                                  "egp_per_m2_month" if figure["name"] == "rent_per_m2_month" else
                                  "egp_month" if figure["name"] == "median_rent_month" else "count")
    kind, words = SIGNAL_UNITS.get(unit, ("number", unit))
    what = figure.get("label") or figure["name"].replace("_", " ")
    where = f", {figure['area']}" if figure.get("area") else ""
    return Figure(f"{prefix}.{figure['name']}.{figure.get('area') or ''}".rstrip("."),
                  f"{what}{where}" + (f" ({words})" if words else "") + f", as stated: «{figure['quote'][:160]}»",
                  figure["value"], kind, period, new=True)


def rent_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    """A new rent index edition, set against Qayem's asking prices: the gross rental yield per district."""
    event = trigger.subject
    period = event["key"].rsplit(":", 1)[-1]
    checked = [f for f in event["figures"] if f.get("checked")]
    figures = [Figure("index_source", "rent index publisher", event["source"], "text"),
               Figure("index_period", "period the rent index covers", period, "text")]
    figures += [_event_figure(f, period, "rent") for f in checked]
    districts = {d["key"]: d for d in data.get("districts") or []}
    rows, path = [], "/index"
    for figure in checked:
        district = districts.get(figure.get("district") or "")
        head = (district or {}).get("headline") or {}
        if figure["name"] != "rent_per_m2_month" or head.get("class") != "apartment" or not head.get("median_ppm"):
            continue
        if head.get("confidence") == "indicative":
            continue
        gross = round(figure["value"] * 12 / head["median_ppm"], 4)
        key, area = district["key"], figure.get("area") or district["name"]
        figures += [Figure(f"sale.{key}.median_ppm", f"apartments in {district['name']} (the guide district {area} is in): "
                           "Qayem's median asking price per m²", head["median_ppm"], "egp_per_m2", "last 30 days", head["count"]),
                    Figure(f"yield.{key}.{area}", f"{area}: a year's asking rent per m² against {district['name']}'s asking "
                           "price per m² (gross rental yield, indicative)", gross, "share", period, new=True)]
        rows.append([area, district["name"], district.get("name_ar") or "", figure["value"], head["median_ppm"], gross])
        path = f"/districts/{key}"
    if len(checked) < 2:
        return None
    tables = [{"id": "rent_vs_price", "columns": ["neighbourhood", "district", "district_ar", "rent_per_m2_month",
                                                   "median_ppm", "gross_yield"], "rows": rows}] if rows else []
    return Pack(trigger, event["title"], path if len(rows) == 1 else "/index", {"start": "", "end": period}, figures,
                tables, {"source": f"{event['source']} rent price index (median asking rents of unfurnished apartments)",
                         "method": "Rents are the publisher's medians; prices are Qayem's medians of asking prices.",
                         "urls_not_to_cite": True})


def news_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    """A property-market fact the press reported, with the figures the report itself states."""
    event = trigger.subject
    checked = [f for f in event["figures"] if f.get("checked")]
    if len(checked) < 2:
        return None
    figures = [Figure("reported_by", "publication that reported it", event["source"], "text"),
               Figure("reported_on", "date reported", event["day"], "date")]
    figures += [_event_figure(f, event["day"][:7], "news") for f in checked]
    return Pack(trigger, event.get("title_en") or event["title"], "/index", {"start": event["day"], "end": event["day"]},
                figures, [], {"summary": event.get("summary"), "topic": event.get("topic"),
                              "source": f"reported by {event['source']}", "urls_not_to_cite": True,
                              "method": "Figures are as the publication reported them; Qayem did not compute them."})


UNIT_WORDS = {"egp_bn": "billion EGP", "egp_mn": "million EGP", "egp": "EGP", "units": "units", "m2": "m²",
              "egp_per_m2": "EGP per m²"}


def report_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    developer, period = trigger.subject["developer"], trigger.subject["period"]
    reports = [r for r in (data.get("overview") or {}).get("developer_reports") or []
               if r["developer"] == developer and r.get("period") == period]
    if not reports:
        return None
    figures = [Figure("developer_key", "developer", developer, "text"), Figure("period", "reporting period", period, "text")]
    seen = set()
    for report in reports:
        for item in report["figures"]:
            if not item.get("checked") or item["name"] in seen:
                continue
            seen.add(item["name"])
            figures.append(Figure(f"report.{item['name']}", f"{item['name'].replace('_', ' ')} ({UNIT_WORDS.get(item['unit'], item['unit'])}),"
                                  f" as stated in the report: «{item['quote'][:160]}»", item["value"],
                                  "egp" if item["unit"].startswith("egp") else "count", period, new=True))
    try:
        entry = site.get(f"/api/developers/{developer}")
        figures += [Figure("developer", "developer", entry["name"], "text"),
                    Figure("developer_ar", "developer in Arabic", entry.get("name_ar") or entry["name"], "text"),
                    Figure("resale_units", "the developer's resale units listed now", entry["units"], "count")]
        if (entry.get("launch") or {}).get("median_headline_ppm"):
            figures.append(Figure("developer_ppm", "the developer's median list price per m² today",
                                  entry["launch"]["median_headline_ppm"], "egp_per_m2", "today", entry["launch"].get("units")))
    except httpx.HTTPError:
        pass
    if len(seen) < 2:
        return None
    return Pack(trigger, f"{developer}'s results for {period}, in numbers", f"/developers/{developer}",
                {"start": "", "end": ""}, figures, [],
                {"source": "the developer's own published results", "urls_not_to_cite": True})


def search_gap_pack(trigger: Trigger, data: dict, site: Site) -> Pack | None:
    """Data pack for a Search Console query with impressions and no matching page (docs/STRATEGY.md 8.2)."""
    pack = guide_pack(trigger, data, site)
    if pack is None:
        return None
    query = trigger.subject.get("query") or ""
    if query:
        pack.title_hint = f"{query} — {pack.title_hint}"
        pack.context = {**pack.context, "search_query": query}
    return pack


PACKS: dict[str, Callable[[Trigger, dict, Site], Pack | None]] = {
    "developer_report": report_pack, "search_gap": search_gap_pack, "rent_index": rent_pack, "market_news": news_pack,
    "guide": guide_pack, "index": index_pack, "move": move_pack, "developer_prices": developer_pack, "rates": rates_pack}


# --- drafting with agy --------------------------------------------------------------------------

DRAFT_SCHEMA = {
    "type": "object", "required": ["ar", "en"], "properties": {
        lang: {"type": "object", "required": ["title", "summary", "blocks"], "properties": {
            "title": {"type": "string"}, "summary": {"type": "string"},
            "blocks": {"type": "array", "items": {"type": "object", "required": ["type"]}}}}
        for lang in ("ar", "en")}}

INSTRUCTIONS = """You write for Qayem (qayem.ai), Egypt's property price guide for regular buyers in Egypt and abroad.
Write one short data article in Arabic (Modern Standard Arabic that Egyptian readers find natural) and the same article
in English, from the DATA PACK below and nothing else.

Hard rules (a draft that breaks any of them is rejected automatically):
1. Every number you write must appear in the data pack, either exactly or rounded the obvious way: a price per m² may be
   written in full (66,800) or in thousands (66.8 thousand / 66.8 ألف); a total price in millions (9.7 million); a share
   (0.1707) as a whole percent (17%); a count exactly. Never compute a new number, never add a number from memory, no
   other years or dates than those in the pack. Write digits as 0-9 in both languages.
2. Open with the answer: the first sentence gives the main figure, the place and the month.
3. Call prices "asking prices" (أسعار مطلوبة); Egypt publishes no sale prices — say so once.
4. No advice: never tell readers to buy, sell, wait or invest; no "opportunity", "don't miss", "guaranteed".
5. Neutral wording about developers and compounds: report figures, never praise or criticise.
6. No links, no source websites' names other than those in the pack, no copied listing text.
7. Use at least one figure marked "new": true.
8. 250–450 words per language. Use blocks: {"type":"p","text"}, {"type":"h2","text"}, {"type":"list","items":[...]},
   {"type":"table","columns":[...],"rows":[[...]]} (only from the pack's tables, values unchanged or rounded as in rule 1),
   {"type":"figure","label","value","note"}. Headings are buyers' questions.
9. End with one sentence on method: figures are medians of listings observed in the period, with duplicates removed.

Return only JSON: {"ar": {"title": "...", "summary": "...", "blocks": [...]}, "en": {"title": "...", "summary": "...",
"blocks": [...]}}. Title under 90 characters; summary one sentence under 200 characters with the main figure."""


def prompt_for(pack: Pack) -> str:
    return (INSTRUCTIONS + "\n\nARTICLE: " + pack.title_hint + "\n\nDATA PACK:\n"
            + json.dumps(pack.as_dict(), ensure_ascii=False, indent=1))


def agy_draft(prompt: str, *, model: str = AGY_MODEL, effort: str = AGY_EFFORT, timeout: int = 900) -> dict:
    """One fresh, tool-less `agy` print run in an empty folder; the answer is parsed as JSON."""
    binary = shutil.which(os.environ.get("QAYEM_AGY", "agy"))
    if not binary:
        raise RuntimeError("agy (Antigravity CLI) is not installed")
    with tempfile.TemporaryDirectory(prefix="qayem-article-") as folder:
        try:
            result = subprocess.run([binary, "--print", prompt, "--output-format", "json", "--model", model,
                                     "--effort", effort, "--print-timeout", f"{timeout}s", "--disable-slash-commands"],
                                    cwd=folder, capture_output=True, text=True, timeout=timeout + 60, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("agy timed out") from exc
    try:
        envelope = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"agy returned no JSON (exit {result.returncode})") from exc
    if envelope.get("status") == "ERROR" or envelope.get("error"):
        raise RuntimeError(f"agy failed: {str(envelope.get('error'))[:200]}")
    return parse_json(envelope.get("response") or "")


def parse_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("the draft is not JSON")
    try:
        return json.loads(text[start:end + 1])
    except ValueError as exc:
        raise RuntimeError("the draft is not valid JSON") from exc


# --- fact check -----------------------------------------------------------------------------------

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
_NUMBER = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\d])")


def numbers_in(text: str) -> list[float]:
    """Every number written in the text (Arabic digits read as Western; 66,800 → 66800)."""
    text = text.translate(_DIGITS)
    out = []
    for match in _NUMBER.finditer(text):
        whole = match.group(1).replace(",", "")
        value = float(whole + ("." + match.group(2) if match.group(2) else ""))
        out.append(value)
    return out


def allowed_numbers(pack: Pack) -> set[float]:
    """Every rendering of every pack figure a careful writer may use."""
    allowed: set[float] = set(range(0, 11))  # one, two, top three …
    def add(value: float):
        allowed.add(round(value, 2))

    def money(value: float):
        add(value)
        for digits in (-2, -3, -4, -5):
            add(round(value, digits))
        for scale in (1_000, 1_000_000, 1_000_000_000):
            for digits in (0, 1, 2):
                add(round(value / scale, digits))

    def stamp(text: str):
        for part in re.findall(r"\d+", text or ""):
            add(float(part))
            if len(part) == 2:
                add(float(int(part)))

    values = [(f.value, f.unit) for f in pack.figures]
    for table in pack.tables:
        for row in table["rows"]:
            for cell in row:
                if isinstance(cell, (int, float)):
                    values.append((cell, "egp_per_m2" if cell > 1000 else "count"))
                else:
                    stamp(str(cell))  # size bands such as "100-150"
    for value, unit in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, str):
            if unit == "date":
                stamp(value)
            continue
        if unit in ("egp", "egp_per_m2", "usd_per_m2"):
            money(float(value))
        elif unit == "share":
            pct = abs(value) * 100
            for digits in (0, 1):
                add(round(pct, digits))
            add(math.floor(pct))
        elif unit == "percent_points":
            add(float(value))
            add(abs(float(value)))
            for digits in (0, 1, 2):
                add(round(abs(float(value)), digits))
        else:
            add(float(value))
    for key in ("start", "end"):
        stamp(pack.period.get(key) or "")
    for figure in pack.figures:
        if figure.period:
            stamp(figure.period)
    return allowed


def draft_text(draft: dict) -> str:
    parts = [draft.get("title", ""), draft.get("summary", "")]
    for block in draft.get("blocks", []):
        for key in ("text", "label", "value", "note"):
            if isinstance(block.get(key), (str, int, float)):
                parts.append(str(block[key]))
        parts.extend(str(item) for item in block.get("items", []) or [])
        parts.extend(str(col) for col in block.get("columns", []) or [])
        for row in block.get("rows", []) or []:
            parts.extend(str(cell) for cell in row)
    return "\n".join(parts)


def fact_check(draft: dict, pack: Pack) -> list[str]:
    """Numbers in the draft that are not in the pack (an empty list passes)."""
    allowed = allowed_numbers(pack)
    bad = []
    for value in numbers_in(draft_text(draft)):
        if not any(abs(value - ok) <= max(0.051, abs(ok) * 0.0005) for ok in allowed):
            bad.append(f"{value:g}")
    return sorted(set(bad), key=lambda v: float(v))


# --- quality gates ----------------------------------------------------------------------------

ADVICE = re.compile(r"\b(buy now|invest now|don'?t miss|must buy|guaranteed|you should (buy|sell|invest)|best time to buy|"
                    r"hurry|act now|once[- ]in[- ]a[- ]lifetime|opportunity)\b|اشتر[يِ]? ?الآن|اشتري الآن|لا تفوت|فرصة لا تعوض|"
                    r"مضمون|ننصح(ك)? ب|استثمر الآن|أفضل وقت للشراء|بادر|فرصة ذهبية|لقطة", re.I)
LOADED = re.compile(r"\b(scam|fraud|cheat|rip[- ]?off|worst|terrible|overpriced|greedy|liar|best developer|"
                    r"trustworthy|untrustworthy)\b|نصب|احتيال|أسوأ|اسوأ|مبالغ فيه|جشع|كذب|أفضل مطور|غير موثوق", re.I)
LINK = re.compile(r"https?://|www\.|\.com\b|\.eg\b", re.I)
ARABIC = re.compile(r"[؀-ۿ]")


def gates(drafts: dict, pack: Pack) -> list[str]:
    reasons = []
    head = next((f for f in pack.figures if f.id == "headline.count"), None)
    if head is not None and head.value < MIN_HEADLINE_COUNT:
        reasons.append("not enough listings behind the headline figure")
    confidence = next((f for f in pack.figures if f.id == "headline.confidence"), None)
    if confidence is not None and confidence.value == "indicative":
        reasons.append("the headline figure rests on a single source")
    new_values = [f for f in pack.figures if f.new]
    for lang in ("ar", "en"):
        draft = drafts.get(lang)
        if not isinstance(draft, dict):
            reasons.append(f"{lang}: missing")
            continue
        text = draft_text(draft)
        words = len(text.split())
        if not draft.get("title") or len(draft["title"]) > 110 or not draft.get("summary"):
            reasons.append(f"{lang}: title or summary missing or too long")
        if not 150 <= words <= 900:
            reasons.append(f"{lang}: {words} words, outside 150–900")
        if ADVICE.search(text):
            reasons.append(f"{lang}: advice wording «{ADVICE.search(text).group(0)}»")
        if LOADED.search(text):
            reasons.append(f"{lang}: loaded wording «{LOADED.search(text).group(0)}»")
        if LINK.search(text):
            reasons.append(f"{lang}: contains a link or a site address")
        arabic_share = len(ARABIC.findall(text)) / max(1, len(re.findall(r"\w", text)))
        if lang == "ar" and arabic_share < 0.6 or lang == "en" and arabic_share > 0.2:
            reasons.append(f"{lang}: written in the wrong language")
        if unchecked := fact_check(draft, pack):
            reasons.append(f"{lang}: numbers not in the data pack: {', '.join(unchecked[:8])}")
        if new_values and not _uses_new(text, new_values):
            reasons.append(f"{lang}: adds no figure beyond the guide page")
        blocks = draft.get("blocks") or []
        if not 3 <= len(blocks) <= 40 or any(b.get("type") not in ("p", "h2", "list", "table", "figure") for b in blocks):
            reasons.append(f"{lang}: invalid blocks")
    return reasons


def _uses_new(text: str, figures: list[Figure]) -> bool:
    written = numbers_in(text)
    lowered = text.casefold()
    for figure in figures:
        if isinstance(figure.value, str):
            if figure.value and figure.value.casefold() in lowered:
                return True
            continue
        if figure.unit == "share":
            target = abs(figure.value) * 100
            if any(abs(v - target) <= 1 for v in written):
                return True
        elif figure.unit in ("egp_per_m2", "egp", "usd_per_m2"):
            if any(abs(v - figure.value) <= abs(figure.value) * 0.01 or abs(v * 1000 - figure.value) <= abs(figure.value) * 0.01
                   for v in written):
                return True
        elif any(abs(v - figure.value) < 0.5 for v in written):
            return True
    return False


# --- publishing ------------------------------------------------------------------------------

def slug_for(pack: Pack, today: date) -> str:
    trigger = pack.trigger
    stem = re.sub(r"[^a-z0-9]+", "-", trigger.key.split(":", 1)[1].casefold()).strip("-")
    return f"{trigger.kind.replace('_', '-')}-{stem}"[:110].strip("-") or f"article-{today:%Y%m%d}"


def publish(site: Site, pack: Pack, drafts: dict, today: date) -> dict:
    base = slug_for(pack, today)
    slugs = {"ar": base, "en": f"{base}-en"}
    meta = {"period": pack.period, "district": pack.district, "compound": pack.compound, "page": pack.path,
            "sources": [{"name": "Qayem Index", "url": "https://qayem.ai/index"}],
            "figures": [f.as_dict() for f in pack.figures], "model": f"agy {AGY_MODEL} ({AGY_EFFORT})"}
    kind = "guide" if pack.trigger.kind == "guide" else pack.trigger.kind
    results = {}
    for lang in ("ar", "en"):
        draft = drafts[lang]
        results[lang] = site.post("/api/admin/articles", {
            "slug": slugs[lang], "lang": lang, "kind": kind, "title": draft["title"], "summary": draft["summary"],
            "blocks": draft["blocks"], "trigger_key": pack.trigger.key, "translation": slugs["en" if lang == "ar" else "ar"],
            "meta": meta})
    return results


Drafter = Callable[[str], dict]


def share_card(pack: Pack, drafts: dict, slug: str, today: date, folder: Path | None) -> dict | None:
    """Write one 1080×1350 Arabic chart card + tracked social link after publishing (docs/STRATEGY.md 8.4)."""
    from .content import COLORS, Story, card_svg, find_chrome, tracked

    ar = drafts.get("ar") or {}
    bars: list[tuple[str, float, str, str]] = []
    for table in pack.tables:
        for row in table.get("rows", [])[:5]:
            if len(row) >= 3 and isinstance(row[2], (int, float)) and row[2] > 0:
                label = str(row[1] or row[0])
                bars.append((label, float(row[2]), f"{round(row[2]):,} ج/م²", COLORS["nile"]))
    if not bars:
        for fig in pack.figures:
            if isinstance(fig.value, (int, float)) and fig.value > 0 and fig.unit in ("egp_per_m2", "egp"):
                shown = f"{round(fig.value):,} ج/م²" if fig.unit == "egp_per_m2" else f"{round(fig.value / 1_000_000, 1)} م"
                bars.append((fig.label[:24], float(fig.value), shown, COLORS["brass"] if fig.new else COLORS["nile"]))
            if len(bars) >= 4:
                break
    article_path = f"/articles/{slug}"
    social_url = tracked(article_path, f"article-{slug[:40]}")
    story = Story(slug=slug, title=ar.get("title") or pack.title_hint, hook=ar.get("summary") or ar.get("title") or "",
                  body=[], path=article_path, bars=bars, chart_title="قيّم — مؤشر أسعار العقارات في مصر")
    svg_text = card_svg(story, f"{today.isoformat()} · qayem.ai")
    if folder is None:
        return {"social_url": social_url, "svg_bytes": len(svg_text.encode("utf-8"))}
    cards = folder / today.isoformat() / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    svg = cards / f"{slug}.svg"
    svg.write_text(svg_text, encoding="utf-8")
    image = svg.name
    if chrome := find_chrome():
        png = svg.with_suffix(".png")
        try:
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1080,1350",
                            f"--screenshot={png}", svg.resolve().as_uri()], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            if png.exists():
                image = png.name
        except (OSError, subprocess.SubprocessError):
            pass
    return {"social_url": social_url, "card": str(cards / image)}


def run(site: Site, *, drafter: Drafter = agy_draft, today: date | None = None, log_dir: Path | None = None,
        dry_run: bool = False, limit: int = 1) -> list[dict]:
    """One pass: publish up to `limit` article pairs, within the weekly cap. Returns what happened."""
    today = today or datetime.now(timezone.utc).date()
    recent = site.get("/api/admin/articles?days=60", admin=True)["items"]
    this_week = {item["trigger_key"] for item in recent
                 if (today - date.fromisoformat(item["published_at"][:10])).days < 7 and item["status"] == "published"}
    if len(this_week) >= WEEKLY_CAP:
        return [{"status": "capped", "reason": f"{len(this_week)} articles in the last 7 days (cap {WEEKLY_CAP})"}]
    data = {"overview": site.get("/api/overview"), "guide": site.get("/api/guide"), "index": site.get("/api/index"),
            "compounds": site.get("/api/compounds?sort=units&page_size=40")["items"],
            "developers": site.get("/api/developers?sort=units&page_size=30")["items"]}
    data["districts"] = data["guide"].get("districts", [])
    gaps_file = (log_dir / "search-gaps.json") if log_dir else None
    if gaps_file and gaps_file.is_file():
        try:
            data["search_gaps"] = json.loads(gaps_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data["search_gaps"] = []
    outcomes = []
    budget = min(limit, WEEKLY_CAP - len(this_week))
    attempts = 0
    for trigger in triggers(data, recent, today):
        if budget <= 0 or attempts >= MAX_DRAFTS:
            break
        outcome: dict[str, Any] = {"trigger": trigger.key, "kind": trigger.kind}
        try:
            pack = PACKS[trigger.kind](trigger, data, site)
        except httpx.HTTPError as exc:
            outcome.update(status="skipped", reason=f"data unavailable: {exc}")
            outcomes.append(outcome)
            continue
        if pack is None:
            outcome.update(status="skipped", reason="not enough data for this article")
            outcomes.append(outcome)
            continue
        attempts += 1
        try:
            drafts = drafter(prompt_for(pack))
        except RuntimeError as exc:
            outcome.update(status="failed", reason=str(exc))
            outcomes.append(outcome)
            _log(log_dir, today, trigger, pack, None, outcome)
            break  # the model is unavailable: try again on the next run
        reasons = gates(drafts, pack)
        if reasons:
            outcome.update(status="rejected", reasons=reasons)
        elif dry_run:
            outcome.update(status="passed", title=drafts["ar"]["title"])
        else:
            published = publish(site, pack, drafts, today)
            card = share_card(pack, drafts, slug_for(pack, today), today, log_dir)
            outcome.update(status="published", result=published, title=drafts["ar"]["title"], share_card=card)
        outcomes.append(outcome)
        _log(log_dir, today, trigger, pack, drafts, outcome)
        if outcome["status"] in ("published", "passed"):
            budget -= 1
    return outcomes


def _log(folder: Path | None, today: date, trigger: Trigger, pack: Pack, drafts: dict | None, outcome: dict) -> None:
    if folder is None:
        return
    target = folder / today.isoformat()
    target.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "-", trigger.key.casefold()).strip("-")
    (target / f"{name}.json").write_text(json.dumps({"outcome": outcome, "pack": pack.as_dict(), "drafts": drafts},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")

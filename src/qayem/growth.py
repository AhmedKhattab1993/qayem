"""First-party visits, lead capture and search alerts, shared by the local and Cloudflare APIs.

Everything is written to a separate database (`qayem-leads` on Cloudflare, `QAYEM_LEADS_DB`
locally), never to the published catalogue. Browsing never depends on it: without that database
events are dropped silently and the forms answer that they are unavailable. Contact details are
kept only to answer the person who left them; nothing is shared with brokers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from html import escape
import json
import re
import secrets
from typing import Any, Awaitable, Callable, Protocol
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

SITE = "https://qayem.ai"
EVENT_TYPES = {"pageview", "outbound_click", "evaluate_run", "share_click", "cta_click", "lead_open",
               "alert_open", "sheet_view", "lookup"}
LEAD_KINDS = {"developer_price", "resale_check", "deal_sheet", "seller", "broker", "general"}
ROLES = {"", "buyer", "investor", "seller", "broker"}
CHANNELS = {"email", "whatsapp"}
# Limits per visitor (a salted, daily IP hash): generous for a person, useless for a script.
EVENTS_PER_DAY, LEADS_PER_DAY, ALERTS_PER_DAY, ALERTS_PER_DESTINATION = 600, 8, 12, 10
BOT = re.compile(r"bot|crawl|spider|slurp|preview|headless|lighthouse|python|curl|wget|httpclient|java/|"
                 r"go-http|axios|node-fetch|facebookexternalhit|whatsapp|telegram|monitor|uptime|scan", re.I)
VISITOR = re.compile(r"^[A-Za-z0-9-]{8,64}$")
EMAIL = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# The Units filters an alert can follow: web/src/searches.ts SEARCH_KEYS, in the same order.
SEARCH_KEYS = ("q", "compound", "price_max", "cash_max", "signing_max", "bedrooms_min", "area_min", "area_max",
               "delivery", "district", "developer", "property_type", "level", "terms", "launch", "price_dropped")
LEVELS = {"strong", "good", "in_line", "mixed", "pricier", "check", "unrated"}
TERMS = {"cash", "plan", "partial", "unknown"}
NUMBERS = {"price_max": (0, 1e9), "cash_max": (0, 1e9), "signing_max": (0, 1e9), "area_min": (0, 1e5),
           "area_max": (0, 1e5)}


class Database(Protocol):
    async def all(self, sql: str, params=()) -> list[dict]: ...
    async def run(self, sql: str, params=()) -> dict: ...


class Http(Protocol):
    async def post(self, url: str, body: dict, headers: dict | None = None) -> tuple[int, str]: ...


class PublicView(Protocol):
    """What the growth routes read from the published catalogue."""
    async def newest_unit_id(self) -> int: ...
    async def unit(self, unit_id: int) -> dict | None: ...


@dataclass
class Settings:
    turnstile_secret: str = ""
    turnstile_site_key: str = ""
    telegram_token: str = ""
    telegram_chat: str = ""
    resend_key: str = ""
    alert_from: str = "Qayem <alerts@qayem.ai>"
    admin_token: str = ""
    hash_salt: str = ""
    site: str = SITE
    environment: str = "production"

    @classmethod
    def read(cls, get: Callable[[str], Any]) -> "Settings":
        def text(name, default=""):
            try:
                value = get(name)
            except Exception:  # an unset Worker binding or secret
                value = None
            return value if isinstance(value, str) and value else default
        return cls(turnstile_secret=text("TURNSTILE_SECRET"), turnstile_site_key=text("TURNSTILE_SITE_KEY"),
                   telegram_token=text("TELEGRAM_BOT_TOKEN"), telegram_chat=text("TELEGRAM_CHAT_ID"),
                   resend_key=text("RESEND_API_KEY"), alert_from=text("ALERT_FROM", cls.alert_from),
                   admin_token=text("ADMIN_TOKEN"), hash_salt=text("HASH_SALT", "qayem-default-salt"),
                   site=text("QAYEM_SITE", SITE), environment=text("QAYEM_ENVIRONMENT", "production"))


@dataclass
class Growth:
    leads: Database | None
    public: PublicView | None
    settings: Settings
    http: Http | None
    ip: str = ""
    country: str = ""
    user_agent: str = ""
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def day(self) -> str:
        return self.now.date().isoformat()

    @property
    def ip_hash(self) -> str:
        return hashlib.sha256(f"{self.settings.hash_salt}:{self.day}:{self.ip}".encode()).hexdigest()[:20]

    @property
    def is_bot(self) -> bool:
        return not self.user_agent or bool(BOT.search(self.user_agent))

    @property
    def device(self) -> str:
        return "mobile" if re.search(r"mobile|android|iphone|ipad", self.user_agent, re.I) else "desktop"


def client_details(request: Request) -> dict:
    headers = request.headers
    ip = headers.get("cf-connecting-ip") or (request.client.host if request.client else "")
    country = (headers.get("cf-ipcountry") or "").upper()[:2]
    return {"ip": ip, "country": country if country.isalpha() else "", "user_agent": headers.get("user-agent", "")[:400]}


# --- validation ----------------------------------------------------------------------

def text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x1f\x7f<>]", " ", value)
    return " ".join(value.split())[:limit]


def phone(value: Any) -> str | None:
    """International WhatsApp number: +<country><number>, 8–15 digits. An Egyptian 01… number gets +20."""
    if not isinstance(value, str):
        return None
    raw = value.translate(DIGITS).strip()
    raw = re.sub(r"[\s().\-‎‏]", "", raw)
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if re.fullmatch(r"01[0125]\d{8}", raw):
        raw = "+20" + raw[1:]
    if raw.startswith("+200"):  # «+20» chip followed by the local 0
        raw = "+20" + raw[4:]
    return raw if re.fullmatch(r"\+[1-9]\d{7,14}", raw) else None


def email(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().casefold()
    return value if len(value) <= 254 and EMAIL.fullmatch(value) else None


def small_json(value: Any, limit: int = 2000) -> str:
    """A flat object of short strings, numbers and booleans, at most `limit` characters as JSON."""
    if not isinstance(value, dict):
        return "{}"
    clean = {}
    for key, item in list(value.items())[:30]:
        key = text(str(key), 40)
        if isinstance(item, bool) or (isinstance(item, (int, float)) and abs(item) < 1e12):
            clean[key] = item
        elif isinstance(item, str):
            clean[key] = text(item, 300)
    encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    return encoded if len(encoded) <= limit else "{}"


def local_path(value: Any) -> str:
    path = text(value, 300)
    return path if path.startswith("/") and not path.startswith("//") else ""


def referrer_host(value: Any) -> str:
    try:
        host = urlsplit(text(value, 500)).hostname or ""
    except ValueError:
        return ""
    return host.removeprefix("www.")[:100]


def search_query(value: Any) -> str | None:
    """The alert's Units filters, validated and spelled one way (the website's own order)."""
    params = dict(parse_qsl(value if isinstance(value, str) else "", keep_blank_values=False))
    clean: dict[str, str] = {}
    for key in SEARCH_KEYS:
        item = params.get(key, "").strip()
        if not item:
            continue
        if key in NUMBERS:
            try:
                number = float(item)
            except ValueError:
                return None
            low, high = NUMBERS[key]
            if not low <= number <= high:
                return None
            item = f"{number:g}" if number != int(number) else str(int(number))
        elif key == "bedrooms_min":
            if not item.isdigit() or int(item) > 12:
                return None
        elif key == "delivery":
            if not re.fullmatch(r"ready|\d{4}", item):
                return None
        elif key == "level" and item not in LEVELS or key == "terms" and item not in TERMS:
            return None
        elif key in {"launch", "price_dropped"}:
            if item != "true":
                return None
        else:
            item = text(item, 200)
        clean[key] = item
    return urlencode(clean, quote_via=quote)


def unit_filters(query: str) -> dict:
    """An alert's stored query as keyword arguments for the units filter (cloud_web.unit_clauses)."""
    params = dict(parse_qsl(query))
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key in NUMBERS:
            out[key] = float(value)
        elif key == "bedrooms_min":
            out[key] = int(value)
        elif key == "price_dropped":
            out[key] = True
        else:
            out[key] = value
    return out


# --- outbound messages -----------------------------------------------------------------

async def telegram(g: Growth, message: str) -> bool:
    """A private message to the founder's Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)."""
    if not (g.http and g.settings.telegram_token and g.settings.telegram_chat):
        return False
    ok = True
    for start in range(0, len(message), 3900):  # Telegram's limit is 4096 characters a message
        try:
            status, _ = await g.http.post(f"https://api.telegram.org/bot{g.settings.telegram_token}/sendMessage",
                                          {"chat_id": g.settings.telegram_chat, "text": message[start:start + 3900],
                                           "parse_mode": "HTML", "disable_web_page_preview": True})
            ok = ok and status == 200
        except Exception:
            ok = False
    return ok


async def verified(g: Growth, token: Any) -> bool:
    """Cloudflare Turnstile, when its secret is configured; otherwise the honeypot and limits apply alone."""
    if not g.settings.turnstile_secret:
        return True
    if not isinstance(token, str) or not token or len(token) > 2048 or not g.http:
        return False
    try:
        status, body = await g.http.post("https://challenges.cloudflare.com/turnstile/v0/siteverify",
                                         {"secret": g.settings.turnstile_secret, "response": token,
                                          "remoteip": g.ip})
        return status == 200 and bool(json.loads(body).get("success"))
    except Exception:
        return False


def wa_link(number: str, message: str = "") -> str:
    return f"https://wa.me/{number.lstrip('+')}" + (f"?text={quote(message)}" if message else "")


async def describe_unit(g: Growth, unit_id: int | None) -> str:
    if not unit_id or not g.public:
        return ""
    try:
        unit = await g.public.unit(unit_id)
    except Exception:
        unit = None
    if not unit:
        return f"unit #{unit_id}"
    place = (unit.get("compound") or {}).get("name") or unit.get("district") or ""
    return (f'<a href="{g.settings.site}/units/{unit_id}">{escape(unit["property_type"])} {unit["area_m2"]:g} m² · '
            f'{escape(place)}</a> · {unit["opportunity"]["level"]} · EGP {unit["price"] / 1e6:.2f}M')


async def lead_message(g: Growth, lead: dict) -> str:
    intent = json.loads(lead["intent"] or "{}")
    lines = [f"🔔 <b>New lead</b> · {escape(lead['kind'])}" + (f" · {escape(lead['role'])}" if lead["role"] else "")]
    if lead["name"]:
        lines.append(f"👤 {escape(lead['name'])}")
    if lead["whatsapp"]:
        hello = "أهلًا، معك قيّم بخصوص طلبك" if lead["lang"] != "en" else "Hello from Qayem about your request"
        lines.append(f'📱 <a href="{wa_link(lead["whatsapp"], hello)}">{lead["whatsapp"]}</a>')
    if lead["email"]:
        lines.append(f"✉️ {escape(lead['email'])}")
    if unit := await describe_unit(g, lead["unit_id"]):
        lines.append(f"🏠 {unit}")
    elif lead["compound_key"]:
        lines.append(f'🏘 <a href="{g.settings.site}/compounds/{quote(lead["compound_key"])}">{escape(lead["compound_key"])}</a>')
    if intent:
        lines.append("📝 " + escape(", ".join(f"{k}: {v}" for k, v in intent.items())))
    source = " / ".join(filter(None, [lead["utm_source"], lead["utm_medium"], lead["utm_campaign"]]))
    lines.append(f"🌍 {lead['country'] or '??'} · {escape(lead['page_path'] or '')}" + (f" · {escape(source)}" if source else ""))
    return "\n".join(lines)


# --- routes ------------------------------------------------------------------------------

def error(status: int, code: str) -> HTTPException:
    return HTTPException(status, code)


async def body_json(request: Request, limit: int = 8192) -> dict:
    raw = await request.body()
    if len(raw) > limit:
        raise error(413, "too_large")
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise error(422, "invalid") from None
    if not isinstance(data, dict):
        raise error(422, "invalid")
    return data


async def count(db: Database, sql: str, params) -> int:
    rows = await db.all(sql, params)
    return int(rows[0]["n"]) if rows else 0


def growth_router(resolve: Callable[[Request], Awaitable[Growth]]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/config")
    async def config(g: Growth = Depends(resolve)):
        return {"leads": g.leads is not None, "turnstile_site_key": g.settings.turnstile_site_key or None,
                "email_alerts": bool(g.settings.resend_key)}

    @router.post("/api/events", status_code=204)
    async def events(request: Request, g: Growth = Depends(resolve)):
        try:
            data = await body_json(request, 4096)
            kind = data.get("type")
            if g.leads is None or kind not in EVENT_TYPES:
                return Response(status_code=204)
            visitor = data.get("visitor") if isinstance(data.get("visitor"), str) and VISITOR.fullmatch(data["visitor"]) else None
            unit_id = data.get("unit_id") if isinstance(data.get("unit_id"), int) and 0 < data["unit_id"] < 10**12 else None
            values = [g.now.isoformat(), g.day, kind, visitor, g.ip_hash, int(g.is_bot), g.device, g.country,
                      "en" if data.get("lang") == "en" else "ar", local_path(data.get("path")), text(data.get("entity"), 200) or None,
                      unit_id, referrer_host(data.get("referrer")) or None, text(data.get("utm_source"), 80) or None,
                      text(data.get("utm_medium"), 80) or None, text(data.get("utm_campaign"), 80) or None,
                      small_json(data.get("meta"), 1000)]
            await g.leads.run(
                "INSERT INTO events(created_at,day,event_type,visitor,ip_hash,is_bot,device,country,lang,path,entity_key,"
                "unit_id,referrer,utm_source,utm_medium,utm_campaign,meta) SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? "
                "WHERE (SELECT count(*) FROM events WHERE day=? AND ip_hash=?)<?",
                (*values, g.day, g.ip_hash, EVENTS_PER_DAY))
        except Exception:
            pass  # measurement must never break the page
        return Response(status_code=204)

    @router.post("/api/leads")
    async def leads(request: Request, background: BackgroundTasks, g: Growth = Depends(resolve)):
        data = await body_json(request)
        if g.leads is None:
            raise error(503, "unavailable")
        if text(data.get("website"), 200):  # the honeypot field people never see
            return {"ok": True}
        kind, role = data.get("kind"), data.get("role") or ""
        whatsapp, mail = phone(data.get("whatsapp")), email(data.get("email"))
        if kind not in LEAD_KINDS or role not in ROLES:
            raise error(422, "invalid")
        if not whatsapp and not mail:
            raise error(422, "invalid_contact")
        if not await verified(g, data.get("turnstile")):
            raise error(403, "verification_failed")
        if await count(g.leads, "SELECT count(*) AS n FROM leads WHERE day=? AND ip_hash=?", (g.day, g.ip_hash)) >= LEADS_PER_DAY:
            raise error(429, "rate_limited")
        unit_id = data.get("unit_id") if isinstance(data.get("unit_id"), int) and 0 < data["unit_id"] < 10**12 else None
        lead = {"created_at": g.now.isoformat(), "day": g.day, "kind": kind, "role": role,
                "name": text(data.get("name"), 80) or None, "whatsapp": whatsapp, "email": mail, "country": g.country or None,
                "lang": "en" if data.get("lang") == "en" else "ar", "compound_key": text(data.get("compound"), 200) or None,
                "unit_id": unit_id, "intent": small_json(data.get("intent")), "page_path": local_path(data.get("path")) or None,
                "visitor": data.get("visitor") if isinstance(data.get("visitor"), str) and VISITOR.fullmatch(data["visitor"]) else None,
                "ip_hash": g.ip_hash, "utm_source": text(data.get("utm_source"), 80) or None,
                "utm_medium": text(data.get("utm_medium"), 80) or None, "utm_campaign": text(data.get("utm_campaign"), 80) or None}
        columns = list(lead)
        await g.leads.run(f"INSERT INTO leads({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
                          tuple(lead[c] for c in columns))

        async def notify():
            await telegram(g, await lead_message(g, lead))
        background.add_task(notify)
        return {"ok": True}

    @router.post("/api/alerts")
    async def alerts(request: Request, background: BackgroundTasks, g: Growth = Depends(resolve)):
        data = await body_json(request)
        if g.leads is None:
            raise error(503, "unavailable")
        if text(data.get("website"), 200):
            return {"ok": True}
        channel = data.get("channel")
        destination = phone(data.get("destination")) if channel == "whatsapp" else email(data.get("destination"))
        query, role = search_query(data.get("query")), data.get("role") or ""
        if channel not in CHANNELS or query is None or role not in ROLES:
            raise error(422, "invalid")
        if not destination:
            raise error(422, "invalid_contact")
        if not await verified(g, data.get("turnstile")):
            raise error(403, "verification_failed")
        if await count(g.leads, "SELECT count(*) AS n FROM alerts WHERE day=? AND ip_hash=?", (g.day, g.ip_hash)) >= ALERTS_PER_DAY:
            raise error(429, "rate_limited")
        existing = await g.leads.all("SELECT id FROM alerts WHERE destination=? AND query=? AND active=1", (destination, query))
        if existing:
            return {"ok": True, "existing": True}
        if await count(g.leads, "SELECT count(*) AS n FROM alerts WHERE destination=? AND active=1",
                       (destination,)) >= ALERTS_PER_DESTINATION:
            raise error(429, "too_many_alerts")
        newest = 0
        if g.public:
            try:
                newest = await g.public.newest_unit_id()
            except Exception:
                newest = 0
        alert = {"created_at": g.now.isoformat(), "day": g.day, "channel": channel, "destination": destination,
                 "role": role or None, "lang": "en" if data.get("lang") == "en" else "ar", "query": query,
                 "label": text(data.get("label"), 200) or "قيّم", "country": g.country or None,
                 "visitor": data.get("visitor") if isinstance(data.get("visitor"), str) and VISITOR.fullmatch(data["visitor"]) else None,
                 "ip_hash": g.ip_hash, "utm_source": text(data.get("utm_source"), 80) or None,
                 "page_path": local_path(data.get("path")) or None, "last_seen_unit": newest,
                 "last_checked": g.day, "token": secrets.token_urlsafe(24)}
        columns = list(alert)
        await g.leads.run(f"INSERT INTO alerts({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
                          tuple(alert[c] for c in columns))
        link = destination if channel == "email" else f'<a href="{wa_link(destination)}">{destination}</a>'
        message = (f"🔔 <b>New alert</b> · {channel}" + (f" · {escape(role)}" if role else "") + f"\n📱 {link}\n"
                   f'🔎 <a href="{g.settings.site}/units?{escape(query)}">{escape(alert["label"])}</a>\n'
                   f"🌍 {g.country or '??'} · {escape(alert['page_path'] or '')}")

        async def notify():
            await telegram(g, message)
        background.add_task(notify)
        return {"ok": True}

    @router.api_route("/api/alerts/unsubscribe", methods=["GET", "POST"], response_class=HTMLResponse)
    async def unsubscribe(token: str = "", g: Growth = Depends(resolve)):
        done = False
        if g.leads is not None and re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token or ""):
            await g.leads.run("UPDATE alerts SET active=0 WHERE token=? AND active=1", (token,))
            done = bool(await g.leads.all("SELECT id FROM alerts WHERE token=?", (token,)))
        message = ("تم إيقاف هذا التنبيه. لن نرسل لك رسائل أخرى عنه." if done else "هذا الرابط غير صالح أو انتهى.",
                   "This alert is off. You will not get more messages about it." if done else "This link is not valid.")
        return HTMLResponse(f"""<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>قيّم — التنبيهات</title><body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;line-height:1.7">
<h1 style="font-size:1.4rem">قيّم</h1><p>{message[0]}</p><p dir="ltr" lang="en">{message[1]}</p>
<p><a href="{g.settings.site}/watchlist">{g.settings.site.removeprefix("https://")}</a></p></body></html>""")

    @router.get("/api/admin/funnel")
    async def funnel(request: Request, days: int = 30, g: Growth = Depends(resolve)):
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not g.settings.admin_token or not hmac.compare_digest(supplied, g.settings.admin_token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        days = max(1, min(days, 365))
        since = (g.now.date() - timedelta(days=days - 1)).isoformat()
        return await funnel_report(g.leads, since)

    return router


async def funnel_report(db: Database, since: str) -> dict:
    """Humans only (bots and empty user agents excluded): visitors, the actions that matter, and leads."""
    daily = await db.all(
        "SELECT day, count(DISTINCT CASE WHEN event_type='pageview' THEN coalesce(visitor, ip_hash) END) AS visitors, "
        "sum(event_type='pageview') AS pageviews, sum(event_type='evaluate_run') AS evaluations, "
        "sum(event_type='outbound_click') AS outbound_clicks, sum(event_type='share_click') AS shares, "
        "sum(event_type='cta_click') AS cta_clicks FROM events WHERE day>=? AND is_bot=0 GROUP BY day ORDER BY day", (since,))
    leads = await db.all("SELECT day, kind, count(*) AS n FROM leads WHERE day>=? GROUP BY day, kind ORDER BY day", (since,))
    alerts = await db.all("SELECT day, channel, count(*) AS n FROM alerts WHERE day>=? GROUP BY day, channel ORDER BY day", (since,))
    totals = (await db.all(
        "SELECT count(DISTINCT coalesce(visitor, ip_hash)) AS visitors, sum(event_type='pageview') AS pageviews "
        "FROM events WHERE day>=? AND is_bot=0 AND event_type='pageview'", (since,)))[0]
    lead_total = await count(db, "SELECT count(*) AS n FROM leads WHERE day>=?", (since,))
    alert_total = await count(db, "SELECT count(*) AS n FROM alerts WHERE day>=?", (since,))
    def top(sql):
        return db.all(sql, (since,))
    return {
        "since": since, "totals": {**totals, "leads": lead_total, "alerts": alert_total,
                                   "capture_rate": round((lead_total + alert_total) / totals["visitors"], 4)
                                   if totals["visitors"] else None},
        "daily": daily, "leads": leads, "alerts": alerts,
        "pages": await top("SELECT path, count(*) AS n FROM events WHERE day>=? AND is_bot=0 AND event_type='pageview' "
                           "GROUP BY path ORDER BY n DESC LIMIT 25"),
        "sources": await top("SELECT coalesce(utm_source, referrer, 'direct') AS source, "
                             "count(DISTINCT coalesce(visitor, ip_hash)) AS visitors FROM events WHERE day>=? AND is_bot=0 "
                             "AND event_type='pageview' GROUP BY source ORDER BY visitors DESC LIMIT 20"),
        "countries": await top("SELECT coalesce(country,'??') AS country, count(DISTINCT coalesce(visitor, ip_hash)) AS visitors "
                               "FROM events WHERE day>=? AND is_bot=0 AND event_type='pageview' GROUP BY country "
                               "ORDER BY visitors DESC LIMIT 20"),
        "outbound_units": await top("SELECT unit_id, count(*) AS n FROM events WHERE day>=? AND is_bot=0 "
                                    "AND event_type='outbound_click' GROUP BY unit_id ORDER BY n DESC LIMIT 20"),
        "lead_kinds": await top("SELECT kind, coalesce(role,'') AS role, count(*) AS n FROM leads WHERE day>=? "
                                "GROUP BY kind, role ORDER BY n DESC"),
        "ctas": await top("SELECT json_extract(meta,'$.cta') AS cta, count(*) AS n FROM events WHERE day>=? AND is_bot=0 "
                          "AND event_type IN ('cta_click','lead_open','alert_open') GROUP BY cta ORDER BY n DESC LIMIT 20"),
    }


# --- a local stand-in for D1 -----------------------------------------------------------

class LocalDatabase:
    """SQLite with D1's async all/run shape, for local development (QAYEM_LEADS_DB) and tests."""

    def __init__(self, path, schema_path=None):
        import sqlite3
        from pathlib import Path
        self.path = str(path)
        schema = Path(schema_path) if schema_path else Path(__file__).resolve().parents[2] / "cloudflare" / "leads-schema.sql"
        with sqlite3.connect(self.path) as connection:
            connection.executescript(schema.read_text())
        self._sqlite = sqlite3

    async def all(self, sql, params=()):
        with self._sqlite.connect(self.path) as connection:
            connection.row_factory = self._sqlite.Row
            return [dict(row) for row in connection.execute(sql, params)]

    async def run(self, sql, params=()):
        with self._sqlite.connect(self.path) as connection:
            cursor = connection.execute(sql, params)
            return {"changes": cursor.rowcount, "last_row_id": cursor.lastrowid}


class LocalHttp:
    async def post(self, url, body, headers=None):
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=body, headers=headers)
            return response.status_code, response.text


class WorkerHttp:
    """Outbound requests from the Python Worker."""

    async def post(self, url, body, headers=None):
        from workers import fetch  # runtime-only import
        response = await fetch(url, method="POST", body=json.dumps(body),
                               headers={"Content-Type": "application/json", **(headers or {})})
        return response.status, await response.text()

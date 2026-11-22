"""Articles, first-party price observations and the WhatsApp intake, stored in the leads database.

- Articles are written by the article agent (articles.py) and posted here with the admin token. They
  publish at once (owner decision, docs/STRATEGY.md 8.2); the Worker then sends a Telegram note with
  the link and a one-tap unpublish, and pings IndexNow.
- Observations are prices Qayem collects itself: each price check run, and what visitors were quoted.
- The WhatsApp Business webhook stores broker sheets and developers' offers for extraction and review.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
from html import escape
import json
import re
import secrets
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .growth import Growth, body_json, count, error, telegram, text

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,120}$")
ARTICLE_KINDS = {"index", "move", "developer_prices", "developer_report", "rates", "explainer", "guide"}
BLOCK_TYPES = {"h2", "p", "list", "table", "figure"}
OBSERVATION_KINDS = {"price_check", "quoted_over", "developer_offer", "price_paid", "broker_sheet"}
OBSERVATIONS_PER_DAY = 60
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


def authorized(request: Request, g: Growth) -> bool:
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return bool(g.settings.admin_token) and hmac.compare_digest(supplied, g.settings.admin_token)


def clean_blocks(blocks: Any) -> list[dict]:
    """Article content as plain-text blocks (never HTML), bounded in size."""
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 80:
        raise error(422, "invalid_blocks")
    out = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in BLOCK_TYPES:
            raise error(422, "invalid_blocks")
        kind = block["type"]
        if kind in ("h2", "p"):
            out.append({"type": kind, "text": text(block.get("text"), 3000)})
        elif kind == "list":
            items = block.get("items") if isinstance(block.get("items"), list) else []
            out.append({"type": "list", "items": [text(item, 600) for item in items[:30]]})
        elif kind == "table":
            columns = [text(c, 80) for c in (block.get("columns") or [])[:8]]
            rows = [[cell if isinstance(cell, (int, float)) and not isinstance(cell, bool) else text(str(cell), 120)
                     for cell in row[:8]] for row in (block.get("rows") or [])[:60] if isinstance(row, list)]
            out.append({"type": "table", "columns": columns, "rows": rows})
        else:
            out.append({"type": "figure", "label": text(block.get("label"), 120), "value": text(str(block.get("value", "")), 60),
                        "note": text(block.get("note"), 300)})
    return out


def public_article(row: dict, full: bool = True) -> dict:
    meta = json.loads(row.get("meta") or "{}")
    item = {"slug": row["slug"], "lang": row["lang"], "title": row["title"], "summary": row["summary"],
            "kind": row["kind"], "published_at": row["published_at"], "district": meta.get("district"),
            "compound": meta.get("compound")}
    if full:
        item.update({"updated_at": row["updated_at"], "byline": "Qayem data desk", "translation": row.get("translation"),
                     "period": meta.get("period"), "sources": meta.get("sources", []),
                     "blocks": json.loads(row["body"]), "figures": meta.get("figures", [])})
    return item


async def article(g: Growth, slug: str) -> dict | None:
    if g.leads is None or not SLUG.fullmatch(slug):
        return None
    rows = await g.leads.all("SELECT * FROM articles WHERE slug=? AND status='published'", (slug,))
    return public_article(rows[0]) if rows else None


async def article_paths(g: Growth) -> list[tuple[str, str]]:
    """(path, updated day) of every published article, for the sitemap."""
    if g.leads is None:
        return []
    try:
        rows = await g.leads.all("SELECT slug, updated_at FROM articles WHERE status='published' ORDER BY published_at DESC "
                                 "LIMIT 2000")
    except Exception:
        return []
    return [(f"/articles/{row['slug']}", row["updated_at"][:10]) for row in rows]


async def ping_indexnow(g: Growth, urls: list[str]) -> bool:
    """IndexNow (Bing, and through it ChatGPT search and Copilot): new or changed URLs."""
    if not (g.http and g.settings.indexnow_key and urls) or g.settings.environment == "staging":
        return False
    host = g.settings.site.removeprefix("https://").removeprefix("http://")
    try:
        status, _ = await g.http.post("https://api.indexnow.org/indexnow", {
            "host": host, "key": g.settings.indexnow_key, "keyLocation": f"{g.settings.site}/{g.settings.indexnow_key}.txt",
            "urlList": urls[:100]})
        return status in (200, 202)
    except Exception:
        return False


def fingerprint(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if low <= parsed <= high else None


async def log_check(g: Growth, inputs: dict, status: str) -> None:
    """One asking-price observation per distinct unit checked a day (no visitor details kept)."""
    if g.leads is None or g.is_bot or status not in ("compared", "district_guide"):
        return
    compound = (inputs.get("compound") or {}).get("key")
    try:
        await g.leads.run(
            "INSERT OR IGNORE INTO observations(created_at,day,kind,source,compound,district,property_type,area_m2,price,"
            "fingerprint,ip_hash) SELECT ?,?,?,?,?,?,?,?,?,?,? WHERE (SELECT count(*) FROM observations WHERE day=? "
            "AND ip_hash=?)<?",
            (g.now.isoformat(), g.day, "price_check", "evaluate", compound, inputs.get("district"),
             inputs.get("property_type"), inputs.get("area_m2"), inputs.get("price"),
             fingerprint("price_check", g.day, compound or inputs.get("district"), inputs.get("property_type"),
                         inputs.get("area_m2"), inputs.get("price")),
             g.ip_hash, g.day, g.ip_hash, OBSERVATIONS_PER_DAY))
    except Exception:
        pass  # a record of the check must never break the check


async def compound_observations(g: Growth, compound_key: str, median_ppm: float | None = None) -> dict | None:
    """First-party observations (price checks, quoted over, developer offers, broker sheets) for one compound,
    with outliers removed (docs/STRATEGY.md 4.3, 5.2 C)."""
    if g.leads is None or not compound_key:
        return None
    since = (g.now.date() - timedelta(days=90)).isoformat()
    try:
        rows = await g.leads.all(
            "SELECT kind, area_m2, price, over, developer_price, paid_price FROM observations "
            "WHERE status='accepted' AND day>=? AND lower(compound)=? LIMIT 500",
            (since, compound_key.casefold()),
        )
    except Exception:
        return None
    if not rows:
        return None
    overs: list[float] = []
    dev_prices: list[float] = []
    kept = 0
    for row in rows:
        area, price = row.get("area_m2"), row.get("price")
        if median_ppm and area and price and area > 0:
            ppm = price / area
            if not (0.3 * median_ppm <= ppm <= 3.5 * median_ppm):
                continue
        kept += 1
        over = row.get("over")
        if isinstance(over, (int, float)) and 0 <= over <= (price or 50_000_000):
            overs.append(float(over))
        dev = row.get("developer_price")
        if isinstance(dev, (int, float)) and dev >= 100_000:
            dev_prices.append(float(dev))
    if not kept:
        return None

    def _q(values: list[float], q: float) -> float:
        ordered = sorted(values)
        pos = (len(ordered) - 1) * q
        lo = int(pos)
        hi = min(lo + 1, len(ordered) - 1)
        return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo), -3)

    return {
        "count": kept,
        "over_count": len(overs),
        "median_over": _q(overs, 0.5) if len(overs) >= 3 else None,
        "p25_over": _q(overs, 0.25) if len(overs) >= 3 else None,
        "p75_over": _q(overs, 0.75) if len(overs) >= 3 else None,
        "developer_offer_count": len(dev_prices),
        "median_developer_price": _q(dev_prices, 0.5) if len(dev_prices) >= 3 else None,
    }


def editorial_router(resolve: Callable[[Request], Awaitable[Growth]]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/articles")
    async def list_articles(lang: str = Query("", pattern="^(|ar|en)$"), page: int = Query(1, ge=1, le=1000),
                            page_size: int = Query(20, ge=1, le=50), g: Growth = Depends(resolve)):
        if g.leads is None:
            return {"items": [], "total": 0, "page": page, "pages": 0}
        where, params = "status='published'" + (" AND lang=?" if lang else ""), ((lang,) if lang else ())
        total = await count(g.leads, f"SELECT count(*) AS n FROM articles WHERE {where}", params)
        rows = await g.leads.all(f"SELECT * FROM articles WHERE {where} ORDER BY published_at DESC LIMIT ? OFFSET ?",
                                 (*params, page_size, (page - 1) * page_size))
        return {"items": [public_article(row, full=False) for row in rows], "total": total, "page": page,
                "pages": (total + page_size - 1) // page_size}

    @router.get("/api/articles/{slug}")
    async def get_article(slug: str, g: Growth = Depends(resolve)):
        item = await article(g, slug)
        if item is None:
            raise error(404, "This article is not available.")
        return item

    @router.post("/api/admin/articles")
    async def publish(request: Request, background: BackgroundTasks, g: Growth = Depends(resolve)):
        """Publish or update an article that passed the article agent's checks."""
        if not authorized(request, g):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        data = await body_json(request, 200_000)
        slug, lang, kind = data.get("slug"), data.get("lang"), data.get("kind")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug) or lang not in ("ar", "en") or kind not in ARTICLE_KINDS:
            raise error(422, "invalid")
        title, summary = text(data.get("title"), 200), text(data.get("summary"), 400)
        trigger = text(data.get("trigger_key"), 200)
        if not title or not summary or not trigger:
            raise error(422, "invalid")
        blocks = clean_blocks(data.get("blocks"))
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        meta_text = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
        if len(meta_text) > 60_000:
            raise error(413, "too_large")
        translation = data.get("translation") if isinstance(data.get("translation"), str) and SLUG.fullmatch(data["translation"]) else None
        existing = await g.leads.all("SELECT unpublish_token, published_at FROM articles WHERE slug=?", (slug,))
        token = existing[0]["unpublish_token"] if existing else secrets.token_hex(16)
        published = existing[0]["published_at"] if existing else g.now.isoformat()
        district = (meta.get("district") or {}).get("key") if isinstance(meta.get("district"), dict) else None
        compound = (meta.get("compound") or {}).get("key") if isinstance(meta.get("compound"), dict) else None
        await g.leads.run(
            "INSERT INTO articles(slug,lang,title,summary,body,kind,trigger_key,district,compound,translation,meta,status,"
            "published_at,updated_at,unpublish_token) VALUES (?,?,?,?,?,?,?,?,?,?,?,'published',?,?,?) ON CONFLICT(slug) DO "
            "UPDATE SET title=excluded.title, summary=excluded.summary, body=excluded.body, meta=excluded.meta, "
            "translation=excluded.translation, status='published', updated_at=excluded.updated_at",
            (slug, lang, title, summary, json.dumps(blocks, ensure_ascii=False, separators=(",", ":")), kind, trigger,
             district, compound, translation, meta_text, published, g.now.isoformat(), token))
        url = f"{g.settings.site}/articles/{slug}"
        unpublish = f"{g.settings.site}/api/articles/{slug}/unpublish?token={token}"

        async def announce():
            await telegram(g, f"📰 <b>Published</b> ({lang}) · {escape(title)}\n{url}\n"
                              f'↩️ <a href="{unpublish}">Unpublish</a>')
            await ping_indexnow(g, [url, f"{g.settings.site}/articles", f"{g.settings.site}/sitemap.xml"])
        background.add_task(announce)
        return {"ok": True, "url": url, "unpublish": unpublish, "updated": bool(existing)}

    @router.get("/api/admin/articles")
    async def recent(request: Request, days: int = 14, g: Growth = Depends(resolve)):
        """Recently published articles and their triggers: the agent's weekly cap and its deduplication."""
        if not authorized(request, g):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        since = (g.now - timedelta(days=max(1, min(days, 400)))).isoformat()
        rows = await g.leads.all("SELECT slug, lang, kind, trigger_key, status, published_at FROM articles "
                                 "WHERE published_at>=? ORDER BY published_at DESC", (since,))
        return {"items": rows}

    @router.api_route("/api/articles/{slug}/unpublish", methods=["GET", "POST"], response_class=HTMLResponse)
    async def unpublish(request: Request, slug: str, token: str = Query("", max_length=64), g: Growth = Depends(resolve)):
        """One tap from the Telegram note: GET shows a button (link previews never act), POST unpublishes."""
        if g.leads is None or not SLUG.fullmatch(slug):
            raise error(404, "not_found")
        rows = await g.leads.all("SELECT title, unpublish_token, status FROM articles WHERE slug=?", (slug,))
        if not rows or not token or not hmac.compare_digest(token, rows[0]["unpublish_token"]):
            raise error(404, "not_found")
        if request.method == "POST":
            await g.leads.run("UPDATE articles SET status='unpublished', updated_at=? WHERE slug=?", (g.now.isoformat(), slug))
            message = "Unpublished. The page now returns 404."
        elif rows[0]["status"] != "published":
            message = "This article is already unpublished."
        else:
            message = (f'<form method="post" action="/api/articles/{quote(slug)}/unpublish?token={quote(token)}">'
                       f'<button style="font-size:1.1rem;padding:.6rem 1.2rem">Unpublish this article</button></form>')
        return HTMLResponse(f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
                            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Qayem</title>'
                            f'<body style="font-family:system-ui;max-width:34rem;margin:12vh auto;padding:0 1rem">'
                            f'<h1 style="font-size:1.2rem">{escape(rows[0]["title"])}</h1><p>{message}</p></body>')

    @router.post("/api/observations")
    async def observe(request: Request, g: Growth = Depends(resolve)):
        """What a visitor was quoted: the over, the developer's offer, or the price paid. No contact details."""
        data = await body_json(request, 4096)
        if g.leads is None:
            raise error(503, "unavailable")
        if text(data.get("website"), 200):
            return {"ok": True}
        kind = data.get("kind")
        if kind not in ("quoted_over", "developer_offer", "price_paid"):
            raise error(422, "invalid")
        values = {"area_m2": number(data.get("area_m2"), 20, 5000), "price": number(data.get("price"), 0, 1e9),
                  "over": number(data.get("over"), 0, 1e9), "developer_price": number(data.get("developer_price"), 1e5, 1e9),
                  "paid_price": number(data.get("paid_price"), 1e5, 1e9)}
        if not any(values[k] for k in ("over", "developer_price", "paid_price")):
            raise error(422, "invalid")
        month = data.get("month") if isinstance(data.get("month"), str) and re.fullmatch(r"\d{4}-\d{2}", data["month"]) else None
        compound, kind_text = text(data.get("compound"), 200) or None, text(data.get("property_type"), 40) or None
        if g.is_bot:
            return {"ok": True}
        changes = await g.leads.run(
            "INSERT OR IGNORE INTO observations(created_at,day,kind,source,compound,property_type,area_m2,price,over,"
            "developer_price,paid_price,month,fingerprint,ip_hash) SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,? "
            "WHERE (SELECT count(*) FROM observations WHERE day=? AND ip_hash=?)<?",
            (g.now.isoformat(), g.day, kind, "visitor", compound, kind_text, values["area_m2"], values["price"],
             values["over"], values["developer_price"], values["paid_price"], month,
             fingerprint(kind, g.day, g.ip_hash, compound, values), g.ip_hash, g.day, g.ip_hash, OBSERVATIONS_PER_DAY))
        return {"ok": True, "stored": bool((changes or {}).get("changes"))}

    @router.get("/api/admin/observations")
    async def observations(request: Request, days: int = 30, g: Growth = Depends(resolve)):
        if not authorized(request, g):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        since = (g.now.date() - timedelta(days=max(1, min(days, 400)) - 1)).isoformat()
        totals = await g.leads.all("SELECT kind, status, count(*) AS n FROM observations WHERE day>=? GROUP BY kind, status",
                                   (since,))
        rows = await g.leads.all("SELECT id, day, kind, source, compound, property_type, area_m2, price, over, "
                                 "developer_price, paid_price, status FROM observations WHERE day>=? ORDER BY id DESC LIMIT 500",
                                 (since,))
        return {"since": since, "totals": totals, "items": rows,
                "all_time": await count(g.leads, "SELECT count(*) AS n FROM observations WHERE status='accepted'", ())}

    # --- WhatsApp Business (Cloud API) webhook ------------------------------------------

    @router.get("/api/whatsapp/webhook", response_class=PlainTextResponse)
    async def whatsapp_verify(request: Request, g: Growth = Depends(resolve)):
        params = request.query_params
        token = g.settings.whatsapp_verify_token
        if params.get("hub.mode") == "subscribe" and token and hmac.compare_digest(params.get("hub.verify_token", ""), token):
            return PlainTextResponse(params.get("hub.challenge", "")[:200])
        raise error(403, "forbidden")

    @router.post("/api/whatsapp/webhook")
    async def whatsapp_receive(request: Request, g: Growth = Depends(resolve)):
        raw = await request.body()
        secret = g.settings.whatsapp_app_secret
        signature = request.headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest() if secret else ""
        if not secret or not hmac.compare_digest(signature, expected):
            raise error(403, "forbidden")
        if g.leads is None:
            raise error(503, "unavailable")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise error(422, "invalid") from None
        stored = 0
        for entry in payload.get("entry", []) if isinstance(payload, dict) else []:
            for change in entry.get("changes", []):
                for message in (change.get("value") or {}).get("messages", []) or []:
                    kind = message.get("type") or "unknown"
                    body = (message.get("text") or {}).get("body") or (message.get(kind) or {}).get("caption")
                    media = (message.get(kind) or {}).get("id") if kind in ("document", "image") else None
                    sender = hashlib.sha256(f"{g.settings.hash_salt}:{message.get('from', '')}".encode()).hexdigest()[:24]
                    clean = _PHONE.sub("[number withheld]", body)[:20_000] if isinstance(body, str) else None
                    result = await g.leads.run(
                        "INSERT OR IGNORE INTO inbox(created_at,channel,message_id,sender_hash,kind,text,media_id) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (g.now.isoformat(), "whatsapp", text(message.get("id"), 200) or fingerprint(raw), sender,
                         text(kind, 20), clean, text(media, 200) or None))
                    stored += int(bool((result or {}).get("changes")))
        return {"ok": True, "stored": stored}

    @router.get("/api/admin/inbox")
    async def inbox(request: Request, status: str = Query("new", pattern="^(new|extracted|reviewed|rejected|all)$"),
                    g: Growth = Depends(resolve)):
        if not authorized(request, g):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        where, params = ("", ()) if status == "all" else (" WHERE status=?", (status,))
        rows = await g.leads.all(f"SELECT id, created_at, kind, text, media_id, status, extracted FROM inbox{where} "
                                 "ORDER BY id LIMIT 200", params)
        return {"items": rows}

    @router.post("/api/admin/inbox")
    async def add_to_inbox(request: Request, g: Growth = Depends(resolve)):
        """Pages read in the computer-use VM (developers' price lists) join the same review queue."""
        if not authorized(request, g):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        data = await body_json(request, 200_000)
        body = data.get("text") if isinstance(data.get("text"), str) else ""
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        source = text(data.get("source"), 300)
        if not body or not source:
            raise error(422, "invalid")
        result = await g.leads.run(
            "INSERT OR IGNORE INTO inbox(created_at,channel,message_id,sender_hash,kind,text,status,extracted) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (g.now.isoformat(), "computer_use", fingerprint(source, body), fingerprint(source), "developer_page",
             _PHONE.sub("[number withheld]", f"{source}\n\n{body}")[:20_000], "extracted" if rows else "new",
             json.dumps(rows[:200], ensure_ascii=False)))
        return {"ok": True, "stored": bool((result or {}).get("changes"))}

    @router.post("/api/admin/inbox/{message}")
    async def review(request: Request, message: int, g: Growth = Depends(resolve)):
        """The extraction job posts rows (`extracted`); the review page accepts or rejects them."""
        if not authorized(request, g):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        if g.leads is None:
            raise error(503, "unavailable")
        data = await body_json(request, 100_000)
        action = data.get("action")
        if action == "extracted":
            rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            await g.leads.run("UPDATE inbox SET status='extracted', extracted=? WHERE id=?",
                              (json.dumps(rows[:200], ensure_ascii=False), message))
            return {"ok": True}
        if action not in ("accept", "reject"):
            raise error(422, "invalid")
        found = await g.leads.all("SELECT extracted FROM inbox WHERE id=?", (message,))
        if not found:
            raise error(404, "not_found")
        accepted = 0
        if action == "accept":
            for row in json.loads(found[0]["extracted"] or "[]"):
                area, price = number(row.get("area_m2"), 20, 5000), number(row.get("price"), 1e5, 1e9)
                if not area or not price:
                    continue
                result = await g.leads.run(
                    "INSERT OR IGNORE INTO observations(created_at,day,kind,source,compound,district,property_type,area_m2,"
                    "price,over,fingerprint,status,inbox_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,'accepted',?)",
                    (g.now.isoformat(), g.day, "broker_sheet", "whatsapp", text(row.get("compound"), 200) or None,
                     text(row.get("district"), 200) or None, text(row.get("property_type"), 40) or None, area, price,
                     number(row.get("over"), 0, 1e9), fingerprint("sheet", message, row), message))
                accepted += int(bool((result or {}).get("changes")))
        await g.leads.run("UPDATE inbox SET status=?, reviewed_at=? WHERE id=?",
                          ("reviewed" if action == "accept" else "rejected", g.now.isoformat(), message))
        return {"ok": True, "accepted": accepted}

    @router.get("/admin/review", response_class=HTMLResponse, include_in_schema=False)
    async def review_page():
        """The review page: the admin token stays in this browser (sessionStorage) and is sent as a header."""
        return HTMLResponse(REVIEW_PAGE, headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})

    return router


REVIEW_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" content="noindex">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Qayem review</title>
<style>body{font-family:system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}pre{white-space:pre-wrap;background:#f4f1ea;
padding:.6rem;border-radius:6px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:.2rem .4rem;font-size:.85rem}
.card{border:1px solid #ccc;border-radius:8px;padding:1rem;margin:1rem 0}button{margin-inline-end:.5rem}</style>
<h1>Broker sheets and offers</h1><p><input id="t" type="password" placeholder="Admin token" size="40">
<button onclick="save()">Use token</button> <select id="s"><option>extracted</option><option>new</option>
<option>reviewed</option><option>rejected</option></select> <button onclick="load()">Load</button></p><div id="o"></div>
<script>
const token=()=>{try{return sessionStorage.getItem('qt')||''}catch(e){return ''}};
function save(){try{sessionStorage.setItem('qt',document.getElementById('t').value)}catch(e){};load()}
async function api(p,o={}){const r=await fetch(p,{...o,headers:{'Authorization':'Bearer '+token(),'Content-Type':'application/json'}});
if(!r.ok)throw new Error(r.status);return r.json()}
function el(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
async function load(){const o=document.getElementById('o');o.replaceChildren();let d;
try{d=await api('/api/admin/inbox?status='+document.getElementById('s').value)}catch(e){o.append(el('p','Error '+e.message));return}
if(!d.items.length)o.append(el('p','Nothing here.'));
for(const m of d.items){const c=el('div');c.className='card';c.append(el('b','#'+m.id+' · '+m.kind+' · '+m.created_at+' · '+m.status));
c.append(el('pre',m.text||'(media '+(m.media_id||'')+')'));const rows=JSON.parse(m.extracted||'[]');
if(rows.length){const t=el('table');const keys=Object.keys(rows[0]);const h=el('tr');keys.forEach(k=>h.append(el('th',k)));t.append(h);
rows.forEach(r=>{const tr=el('tr');keys.forEach(k=>tr.append(el('td',String(r[k]??''))));t.append(tr)});c.append(t)}
for(const a of ['accept','reject']){const b=el('button',a);b.onclick=async()=>{await api('/api/admin/inbox/'+m.id,{method:'POST',
body:JSON.stringify({action:a})});load()};c.append(b)}o.append(c)}}
</script></html>"""

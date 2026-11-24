"""Price alerts for a compound or a district: after each catalogue publication, the person who asked
hears how many listings there were added or cut in price, with a link to the guide's prices today.
No listing is sent one by one (docs/STRATEGY.md 14).

The public Worker checks every hour (a cron trigger) and sends once per published version, so
alerts follow the nightly update whenever it finishes. E-mail goes out through Resend
(RESEND_API_KEY). WhatsApp has no free sending API, so WhatsApp alerts reach the founder's
Telegram as ready-to-send wa.me links: one tap opens the chat with the message written.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from urllib.parse import quote, urlencode

from .growth import Database, Growth, Http, Settings, guide_path, telegram, unit_filters, wa_link

MAX_ALERTS = 2000


def link(settings: Settings, path: str, medium: str) -> str:
    joiner = "&" if "?" in path else "?"
    return f"{settings.site}{path}{joiner}{urlencode({'utm_source': 'alert', 'utm_medium': medium})}"


def summary_line(alert: dict, total: int) -> str:
    """What changed, counted: Qayem does not publish listings one by one, so an alert says how many
    moved and links to the guide that prices them (docs/STRATEGY.md 14)."""
    if alert["lang"] == "en":
        return (f"{total} listing{'s' if total != 1 else ''} in “{alert['label']}” "
                f"{'were' if total != 1 else 'was'} added or cut in price since your last alert.")
    return f"{total} إعلان جديد أو نزل سعره في «{alert['label']}» منذ آخر تنبيه."


def email_message(alert: dict, total: int, settings: Settings) -> dict:
    english = alert["lang"] == "en"
    guide = link(settings, guide_path(alert["query"]), "email")
    stop = f"{settings.site}/api/alerts/unsubscribe?token={quote(alert['token'])}"
    subject = (f"Qayem: {total} new for “{alert['label']}”" if english
               else f"قيّم: {total} جديد يطابق «{alert['label']}»")
    intro = summary_line(alert, total)
    see = "See today’s prices" if english else "شاهد الأسعار اليوم"
    footer = ("You asked Qayem for this alert. We never share your contact with brokers. "
              if english else "طلبت هذا التنبيه من قيّم. لن نشارك بياناتك مع سماسرة. ")
    unsubscribe = "Stop this alert" if english else "أوقف هذا التنبيه"
    direction = "ltr" if english else "rtl"
    html = (f'<div dir="{direction}" style="font-family:system-ui,Segoe UI,Tahoma,sans-serif;font-size:15px;line-height:1.7;'
            f'max-width:560px;margin:auto;color:#14201b"><h2 style="font-size:18px">{escape(alert["label"])}</h2>'
            f"<p>{escape(intro)}</p>"
            f'<p><a href="{escape(guide)}" style="background:#0b6e4f;color:#fff;padding:10px 16px;border-radius:8px;'
            f'text-decoration:none">{see}</a></p><p style="color:#66746e;font-size:13px">{footer}'
            f'<a href="{escape(stop)}" style="color:#66746e">{unsubscribe}</a></p></div>')
    plain = "\n".join([intro, f"{see}: {guide}", f"{unsubscribe}: {stop}"])
    return {"from": settings.alert_from, "to": [alert["destination"]], "subject": subject, "html": html, "text": plain,
            "headers": {"List-Unsubscribe": f"<{stop}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}}


def whatsapp_text(alert: dict, total: int, settings: Settings) -> str:
    guide = link(settings, guide_path(alert["query"]), "whatsapp")
    stop = "Reply STOP to end this alert." if alert["lang"] == "en" else "للإيقاف رد بكلمة: إيقاف"
    return "\n".join([summary_line(alert, total), guide, stop])


async def send_email(http: Http, settings: Settings, message: dict) -> bool:
    try:
        status, _ = await http.post("https://api.resend.com/emails", message,
                                    {"Authorization": f"Bearer {settings.resend_key}"})
        return 200 <= status < 300
    except Exception:
        return False


async def dispatch(store, leads: Database, http: Http | None, settings: Settings, now: datetime | None = None) -> dict:
    """Tell each active alert how many matching listings were added (higher ID) or cut in price since it
    last checked. Runs once per published catalogue version; a repeat is a no-op."""
    from .cloud_web import unit_clauses

    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    version = store.version
    done = await leads.all("SELECT value FROM state WHERE key='alerts_version'")
    if done and done[0]["value"] == version:
        return {"status": "already_sent", "version": version}
    newest = await store.newest_unit_id()
    alerts = await leads.all("SELECT * FROM alerts WHERE active=1 ORDER BY id LIMIT ?", (MAX_ALERTS,))
    summary = {"status": "sent", "version": version, "alerts": len(alerts), "matched": 0, "emailed": 0,
               "email_failed": 0, "whatsapp": 0}
    digest: list[str] = []
    for alert in alerts:
        try:
            clauses, params = await unit_clauses(store, **unit_filters(alert["query"]))
        except Exception:
            continue  # a filter that no longer applies (e.g. a retired developer key) is skipped, not fatal
        clauses.append("(id>? OR coalesce(json_extract(public,'$.price_change.at'),'')>?)")
        params.extend([alert["last_seen_unit"], alert["last_checked"] or today])
        where = " AND ".join(clauses)
        total = (await store.database.all(f"SELECT count(*) AS n FROM units WHERE {where}", params))[0]["n"]
        status = "none"
        if total:
            summary["matched"] += 1
            if alert["channel"] == "email":
                if settings.resend_key and http and await send_email(http, settings, email_message(alert, total, settings)):
                    status = "emailed"
                    summary["emailed"] += 1
                else:
                    status = "email_failed"
                    summary["email_failed"] += 1
            else:
                status = "whatsapp_queued"
                summary["whatsapp"] += 1
                text = whatsapp_text(alert, total, settings)
                digest.append(f'• {escape(alert["label"])} ({total}) → '
                              f'<a href="{escape(wa_link(alert["destination"], text))}">{alert["destination"]}</a>')
            await leads.run("INSERT OR IGNORE INTO deliveries(created_at,alert_id,version,channel,matches,status) "
                            "VALUES (?,?,?,?,?,?)", (now.isoformat(), alert["id"], version, alert["channel"], total, status))
        sent = status in {"emailed", "whatsapp_queued"}
        # A failed e-mail keeps its starting point, so the next publication counts the same listings again.
        await leads.run("UPDATE alerts SET last_seen_unit=?, last_checked=?, last_sent=coalesce(?, last_sent), "
                        "sent_count=sent_count+? WHERE id=?",
                        (alert["last_seen_unit"] if status == "email_failed" else max(newest, alert["last_seen_unit"]),
                         alert["last_checked"] if status == "email_failed" else today,
                         today if sent else None, int(sent), alert["id"]))
    if digest or summary["email_failed"]:
        g = Growth(None, None, settings, http)
        head = (f"📬 <b>Alerts for {escape(version)}</b>: {summary['emailed']} e-mailed, "
                f"{summary['email_failed']} e-mail failed, {summary['whatsapp']} WhatsApp to send (tap to open):")
        await telegram(g, "\n".join([head, *digest]))
    await leads.run("INSERT INTO state(key,value) VALUES ('alerts_version',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (version,))
    return summary


async def run_scheduled(env) -> dict | None:
    """The public Worker's cron trigger. Staging never sends."""
    from .cloud_web import D1, Store, _binding
    from .growth import WorkerHttp

    settings = Settings.read(lambda name: getattr(env, name))
    leads = _binding(env, "LEADS_DB")
    if leads is None or settings.environment == "staging":
        return None
    store = await Store(D1(env.DB)).open()
    return await dispatch(store, D1(leads), WorkerHttp(), settings)

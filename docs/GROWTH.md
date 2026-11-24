# Growth: traffic in, leads captured

Qayem had ~2–5 real visitors a day and captured nothing: watchlists and saved searches stayed in
the browser, every unit page sent people to AqarExit untracked, and every shared link showed the
same generic title. This layer fixes the plumbing. Browsing stays completely open; nothing is
gated behind a form.

## What is in place

| Area | What it does | Code |
|---|---|---|
| Canonical host | `www.qayem.ai` → `https://qayem.ai` (301, path and query kept) | `seo.canonical_redirect`, both apps' middleware |
| Page heads | Every public route gets an Arabic `<title>`, description, canonical, Open Graph/Twitter tags, JSON-LD (breadcrumbs, `Place`, `Dataset`, `FAQPage`) and a crawlable summary inside `#root` that React replaces. Unknown compounds answer 404 + `noindex`. The retired listing pages (`/units`, `/units/:id`, `/sheet/:id`) answer 301 to the guide that covers the listing (`seo.retired_redirect`). | `src/qayem/seo.py` |
| Sitemap, robots | `/sitemap.xml` (sections, districts, compounds and developers with ≥3 listings, the index and articles) and `/robots.txt` (keeps `/api` crawlable: search engines render the app) | `seo.sitemap_xml`, `seo.robots_txt` |
| District pages | `/districts`, `/districts/:key`: prices, compounds against the developer, history, FAQ | `web/src/pages/District*.tsx` |
| First-party events | `pageview`, `outbound_click` (source links), `evaluate_run`, `share_click`, `cta_click`, `lead_open`, `alert_open`, `sheet_view`, `lookup`. No cookies, no raw IPs (a salted hash that changes daily, for limits only), bots flagged by user agent. | `web/src/track.ts`, `growth.py` |
| Lead capture | Verdict-aligned cards on the evaluate page: strong/good/check → a verification checklist and transfer-fee estimate (shown immediately); in line/pricier/mixed → the developer's current offer. Seller mode (`/evaluate?mode=sell`). Two fields at most, an anti-spam pledge on every form. | `web/src/components/Capture.tsx` |
| Alerts | A compound or district can become a WhatsApp or e-mail alert: after each nightly update, how many listings there were added or cut in price, with a link to the guide. No listing is sent one by one (2026-11-24). | `growth.py` (`/api/alerts`), `alerts.py` |
| Sharing | "Send on WhatsApp" with a price check's one-line verdict and a tracked link. | `web/src/components/Share.tsx` |
| Spam | Honeypot field, per-visitor daily limits, and Cloudflare Turnstile once its keys are set. | `growth.verified` |
| Founder pings | Every lead and alert sign-up posts to a private Telegram chat with a `wa.me` link that opens the chat with a greeting. | `growth.telegram` |
| Funnel | `GET /api/admin/funnel?days=30` with `Authorization: Bearer $ADMIN_TOKEN`: visitors, pageviews, evaluations, source clicks, shares, leads by kind/role, alerts, top pages, sources, countries, capture rate. Humans only. | `growth.funnel_report` |
| History | Price changes from real edits (parser upgrades ignored), listings that left in 30 days, days on the market for listings first seen after the opening crawls, developer list-price moves for the same units over 60 days. Price-cut badges and a `price_dropped` filter. | `website_data.price_changes`, `liquidity`, `price_history` |
| Nawy resale | `QAYEM_SOURCES` defaults to `aqarexit,nawy`; `/evaluate` accepts either site's links. | `config.py`, updater `wrangler.jsonc` |
| Content | `qayem content-brief --png` writes three Arabic data stories with 1080×1350 cards and tracked links. | `src/qayem/content.py` |

## Data and where it lives

`qayem-leads` (D1, binding `LEADS_DB`, schema `cloudflare/leads-schema.sql`) holds `events`,
`leads`, `alerts`, `deliveries` and `state`. It is separate from `qayem-public`, so catalogue
publications, imports and version retention never touch it. Staging uses `qayem-leads-staging`.
Locally, set `QAYEM_LEADS_DB=/path/to/leads.db` (created on first use); without it the forms
answer that they are unavailable and events are dropped.

Read it with Wrangler, for example the newest leads:

```sh
cd cloudflare
npx wrangler@4.147.0 d1 execute qayem-leads --remote --command \
  "SELECT created_at, kind, role, name, whatsapp, email, country, unit_id, compound_key, intent FROM leads ORDER BY id DESC LIMIT 20"
```

## Alerts

The public Worker runs every hour (`17 * * * *`). When the active catalogue version differs from
the one last alerted, every active alert gets the matching units with a higher ID than it last
saw, or with a price cut since it last checked, once (`deliveries` is unique per alert and
version). E-mail goes through Resend; a failed e-mail keeps its starting point and is retried with
the next publication. WhatsApp has no free sending API, so WhatsApp alerts arrive in the founder's
Telegram as one digest of `wa.me` links with the message already written: one tap per subscriber.
Every message links to `/api/alerts/unsubscribe?token=…`. Staging never sends.

## Secrets and settings (public Worker)

Set with `cd cloudflare && npx wrangler@4.147.0 secret put NAME` (add `--env staging` for staging):

| Name | Needed for |
|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional instant lead pings, WhatsApp alert digests and post-publish article notes on Telegram. When unset, founder pings fall back to e-mail via `FOUNDER_EMAIL` + `RESEND_API_KEY`. |
| `FOUNDER_EMAIL` | Founder e-mail address (in `vars`) for lead pings, takedown alerts, WhatsApp alert digests and published-article notices via Resend when Telegram is not used. |
| `RESEND_API_KEY` | E-mail alerts and founder pings (the e-mail option appears only when this is set). Verify `qayem.ai` in Resend first. Optional `ALERT_FROM` (default `Qayem <alerts@qayem.ai>`). |
| `TURNSTILE_SECRET` + var `TURNSTILE_SITE_KEY` | Bot protection on forms (Cloudflare dashboard → Turnstile → add `qayem.ai`, managed mode). The site key is public: put it in `vars`. |
| `ADMIN_TOKEN` | The funnel report. Any long random string, e.g. `openssl rand -hex 32`. |
| `HASH_SALT` | Optional: the salt for the daily visitor hash. |

Staging already has `ADMIN_TOKEN` (stored in the ignored `.artifacts/cloudflare/staging/admin-token`) and its own
`qayem-leads-staging`, which holds the end-to-end test's sample lead and alerts.

Read the funnel:

```sh
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://qayem.ai/api/admin/funnel?days=7" | python3 -m json.tool
```

## Weekly routine

1. Sunday: read the funnel (which pages, sources and countries bring visitors; capture rate).
2. Pull fresh data (`scripts/cloud-dev.py pull`) and run
   `QAYEM_DB=.artifacts/development/qayem.db .venv/bin/qayem content-brief --png --out content-brief`.
   Post the three stories (TikTok/Reels/LinkedIn/Facebook) with their tracked links; answer
   «هل السعر ده كويس؟» threads in compound and Gulf-expat groups with a deal sheet link.
3. Follow up every Telegram lead within minutes on WhatsApp; send the WhatsApp alert digest.

## Targets before monetising

≥50–100 human visits/day, ≥8–12% visitor-to-capture rate, ≥100 alert subscribers and 30–50
direct buyer/seller/broker leads a month. Until then, everything optimises those two numbers.

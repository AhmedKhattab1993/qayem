# The price guide, the index, the map, articles and Qayem's own data

How the direction in [STRATEGY.md](STRATEGY.md) is built (phases 1–4). Everything here is free to run.

## Data layer (phase 1)

| Step | What it does | Code |
|---|---|---|
| Market districts | 59 districts buyers mean (New Cairo, Sheikh Zayed, North Coast, Alexandria, Mansoura…), each with English and Arabic aliases. A listing is placed from its district, then its compound, then its link's path (the last place named wins: `…-new-cairo-madinaty-…` is Madinaty), then its title; a crawl scope's city limits the candidates. 98–100% of every source's listings resolve. Keys equal the website's existing district URLs. | `src/qayem/market.py` |
| Market sources | Aqarmap, OpenSooq and Semsar (`QAYEM_MARKET_SOURCES`, `none` turns them off) are crawled on alternate nights and feed the figures only: their listings are never published one by one. AqarExit and Nawy stay the unit sources (`QAYEM_SOURCES`). | `config.py`, `crawl.py` (`every_days`) |
| Classify | market (resale / contract transfer / developer sale: `nawy_primary` and Aqarmap's `-projects-` links), seller, terms, quality. A price per m² below 0.3× or above 3.5× its district's median is dropped as suspect (a down payment listed as the price). | `guide.classify`, `guide.plausible` |
| Dedupe | The same unit on two sites counts once: same compound (or district) and class, area within 2%, price within 3%, seen within 30 days, different sources. The most structured copy is kept (AqarExit, Nawy, Aqarmap, OpenSooq, Semsar). | `guide.dedupe` |
| Segments | District × (all / one compound / outside compounds) × class × size band, delivery (ready / under 2 years / later) or finishing (`finished`, `semi_finished`, `core_shell`, `furnished`). Published only with ≥5 listings from ≥2 sources, or ≥10 from one ("single source", confidence *indicative*). *High*: ≥20 listings, ≥2 sources, no source above 80%. Every figure carries its 30-day period, count, source mix, median, quartiles, cash-today median, developers' list price and resale against new (today's money). | `guide.build`, `guide.stats` |
| Qayem Index | One edition a month (`/index/2026-11`), rewritten nightly while the month runs and frozen after it, in the canonical database (`index_editions`). Each day's district and compound figures go to `segment_history`, which finds ±5% moves over 30 days. | `guide.index`, `ledger.py`, `qayem record-index` |
| CBE rates & official fees | Exchange rates (EGP per USD, EUR, GBP, SAR, AED, KWD, QAR), overnight rates and inflation from cbe.org.eg, nightly; the CBE overnight deposit rate dynamically drives the installment discount rate (`website_data._cbe_discount_rate`). Yearly statutory Egypt buying/registration fee schedules (`src/qayem/data/fee_schedules.json`) live in `official.py`. | `rates.py`, `official.py`, `qayem fetch-rates` |
| Market signals | CAPMAS indicators and release calendar (JSON API), Binance P2P USDT/EGP, gold, the CBE's quarterly balance of payments, Marsad Omran's rent indices, FRA financing statistics, NUCA notices, the real-estate platform's land and housing offers, and property news, nightly into `market_signals` / `market_events`; published as `overview.signals` and shown on `/index`. Unstructured sources are read by the Claude CLI (Opus 5.5, medium effort), never by regular expressions; a figure is kept only when its quote is in the source and its number in the quote. See [DATA_SOURCES.md](DATA_SOURCES.md). | `signals.py`, `claude_cli.py`, `qayem fetch-signals` |
| Developer reports & VM pages | New earnings releases and presentations from SODIC, Madinet Masr, Palm Hills and TMG's investor pages (plain links, robots.txt respected). Monthly isolated-VM checks (`scripts/vm-developer-pages.py`, 10 top developers + `realestate.gov.eg` terms check) run strictly inside the `computer-use` OrbStack VM behind `studio.desktop_lock` (`scripts/install-vm-pages.sh`). | `reports.py`, `qayem developer-reports`, `scripts/vm-developer-pages.py` |

The nightly cloud run adds four stages after the health check: `fetch-rates`, `fetch-signals`,
`developer-reports` and `record-index` (from the sources fit to publish). None of them can hold back publication.

On the development copy (22 November 2026): 22,700 listings in the window, 2,150 cross-source
duplicates and 200 suspect prices removed, 1,713 published segments (447 high, 992 medium, 274
indicative), 84% of them resting on more than one source.

## Map and guides (phase 2)

- `/api/map`: districts (centroid, headline, every class, delivery breakdowns, bedroom counts), compounds placed from OpenStreetMap (`src/qayem/data/compound_places.json`), and ~1.6 km price hexagons (`hexes`, only cells with ≥5 listings). District outlines: `web/public/map/districts.geojson`. Rebuild both with `scripts/build-map-data.py districts|places|compounds` (one request a second, cached under `.artifacts/map/cache`). Data © OpenStreetMap contributors, ODbL.
- Map UI (`/map`): filters by unit type, colour mode (price/m² or resale vs new), delivery, bedrooms, budget, currency, and toggleable hex price grid, plus an accessible table fallback.
- Basemap: a Protomaps PMTiles extract of Egypt (z0–13, 85 MB) in the private R2 bucket `qayem-map`,
  served by the Worker at `/tiles/egypt.pmtiles` with byte ranges and edge caching (`cloud_media.serve_tiles`).
  Locally the API serves `.artifacts/map/egypt.pmtiles`. Refresh:
  `pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles egypt.pmtiles --bbox=24.6,21.9,37.0,31.8 --maxzoom=13`
  then `npx wrangler@4.147.0 r2 object put qayem-map/egypt.pmtiles --file egypt.pmtiles --remote`.
- District and compound pages open with the answer (median asking price per m², the place and the month,
  the usual range, resale against new), emit structured no-JS `<table>` figures (`seo.guide_table`), and carry `Place` JSON-LD; compound pages also show up to 5 same-district `comparable_compounds` and outlier-filtered `observations` (quoted over / developer offers). `/evaluate` works both inside compounds and for non-compound units by district (`district_guide`).
- SEO/GEO hygiene: third-party photos and listing descriptions are never served or rendered; individual listing pages are retired (2026-11-24): `/units`, `/units/:id` and `/sheet/:id` redirect with 301 to the compound or district guide; thin pages without published guide figures are `noindex,follow`; `robots.txt` explicitly allows `OAI-SearchBot`, `GPTBot`, `ClaudeBot`, `PerplexityBot`, and `Google-Extended`; `/api/admin/funnel` tracks `ai_referrals`; `scripts/geo-benchmark.py` runs the monthly 20-question AI-citation check (`src/qayem/data/geo_questions.json`).
- `/index/<month>` carries `Dataset` JSON-LD with the CSV as its distribution; articles carry `Article`.
- `/api/guide`, `/api/guide/<district>`, `/api/index`, `/api/index/<month>`; CSV at
  `/data/qayem-index-<month>.csv` and `/data/qayem-index-latest.csv` (CC BY 4.0, aggregates only).

## Articles (phase 3)

`qayem articles` (daily on the operator's Mac: the model is the local Antigravity CLI, `agy`, model
`gemini-4-neon` at `--effort medium`; override with `QAYEM_ARTICLE_MODEL` / `QAYEM_ARTICLE_EFFORT`):

1. Reads the live public API (`--site`, default `https://qayem.ai`) and the recent articles (admin token).
2. Triggers, best first: the monthly index, a CBE rate decision, a developer's quarterly results, a new
   rent index edition (`rent_index`: rents per m² with the gross yield against Qayem's asking prices, only where
   the neighbourhood names the guide district), a segment that moved ±5%, property news with ≥2 checked
   figures (`market_news`), a developer's list prices moving ≥3% over 60 days, a Search Console query gap
   (`.artifacts/articles/search-gaps.json`), then the calendar (the largest compounds and districts, each
   at most once in 60 days).
3. Builds the data pack: every figure with its period and count; gaps and ranks computed in Python
   and marked `new` (what the article adds to the guide page).
4. `agy --print … --output-format json` in an empty folder drafts Arabic and English as JSON blocks.
5. Fact check: every number in the text must be a rendering of a pack figure (in full, in thousands,
   millions or billions, a share as a percent, a count, a date part); Arabic digits are read too.
6. Gates: listings behind the headline, no single-source headline, no advice, no loaded words about
   developers, no links, the right language in each version, 150–900 words, at least one `new` figure.
7. Publishes both languages (`POST /api/admin/articles`), writes a 1080×1350 share card (`.artifacts/articles/<day>/cards/`) with a UTM-tracked link; the Worker sends the Telegram note with the
   link and a one-tap unpublish (GET shows a button, POST unpublishes) and pings IndexNow (key in
   `INDEXNOW_KEY`, served at `/<key>.txt`). The sitemap lists every published article.
8. Caps: one pair a run, three model calls a run, four pairs a rolling week. Every pack, draft and
   verdict is kept under `.artifacts/articles/<day>/`.

Schedule it with `scripts/install-articles.sh` (a LaunchAgent at 09:15 Cairo time). `agy` must be signed in
once interactively (`agy`, then follow the sign-in link).

## Qayem's own data (phase 4)

| What | Where |
|---|---|
| Every price check run | `observations` (kind `price_check`): compound, type, area, price; one per distinct unit a day. No visitor details. |
| "What over were you quoted?" / "What does the developer offer you?" | `POST /api/observations` from the price check page. |
| WhatsApp Business intake | `GET/POST /api/whatsapp/webhook` (Meta Cloud API: `WHATSAPP_VERIFY_TOKEN`, signature checked with `WHATSAPP_APP_SECRET`). Messages go to `inbox` with phone numbers withheld; `qayem extract-inbox` (Pi/GLM) proposes rows; `/admin/review` (admin token, kept in the browser tab) accepts or rejects them; accepted rows become `broker_sheet` observations. |
| Free deal check | `/deal-check`, lead kind `deal_check` (Telegram ping). |
| Takedown and corrections | `/corrections`, lead kinds `takedown` and `correction`; terms at `/terms`. |
| Monthly CSV | `/data/qayem-index-<month>.csv`. |
| Counts | `GET /api/admin/observations?days=30` (admin token). |

New tables are in `cloudflare/leads-schema.sql` (`articles`, `observations`, `inbox`); apply it with
`npx wrangler@4.147.0 d1 execute qayem-leads --remote --file leads-schema.sql` (idempotent).

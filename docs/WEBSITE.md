# Qayem website

A read-only fair-value workspace on top of the Qayem database. It answers one question for a buyer in Egypt's resale market: **what is this unit really worth?** The site values units by compound, developer, delivery date and payment plan, not by area alone, and shows how sure it is.

## Pages

| Route | Purpose |
|---|---|
| `/` | The question, headline accuracy, developer premiums vs district norms, how a unit is valued, and the evidence behind it |
| `/evaluate` | "Is this a fair price?" Describe a unit (compound, type, area, finishing, delivery, headline price, payment plan) or paste an indexed listing link. Returns fair cash value with a calibrated range and evidence grade, the plan's value in today's money, the total cost of buying (editable fee assumptions), how the value was built, what the valuation cannot see, and the closest comparables. Form state is in the URL, so results are shareable. |
| `/compounds`, `/compounds/:key` | Fair cash value per m² per property class (finished, ready, typical size), premium vs district, **resale vs the developer's current launch price** (like for like, same plan length), delivery and payment profile, stock mix, units furthest below fair value |
| `/developers`, `/developers/:key` | Developer premium vs district norm (like for like), resale vs launch prices, each compound's premium, delivery and payment profile, promised delivery dates tracked across crawls |
| `/units`, `/units/:id` | Every identified resale unit with cash-equivalent price, fair range, position (below / within / above / check this listing) and evidence grade; filters by district, developer, type, position, grade and payment terms |
| `/compare` | Up to three compounds or three developers side by side |
| `/watchlist` | Compounds and developers kept in this browser |
| `/methodology` | The model and its fitted effects, the leave-one-out backtest by evidence grade vs the naive district-median method, the cash-equivalent rule, source coverage, and the limits |

The interface opens in Arabic (right-to-left); the header button switches to English. Tables become stacked cards on phones. `⌘K`/`Ctrl+K` or `/` opens search over compounds, developers, districts and pages.

## What was removed, and why

The site used to look like a listing portal. These were removed because they did not serve evaluation or were not supported by the data:

- **"Priced below peers" opportunities.** Peers were district + type, so a quarter of flagged units were at or above their own compound's median, and installment headlines were compared with cash prices. Replaced by the backtested fair-value position.
- **The 11-check completeness score and dial.** It measured how many fields a portal filled, not whether a price was fair. Replaced by the evidence grade and an explicit "what this valuation cannot see" list.
- **Market-wide medians and the Pulse dashboard.** A median across Ras El Hekma chalets and October apartments describes the mix, not the market. Statistics now exist only inside a segment (district, compound, developer).
- **Photo cards, galleries, shortlist of listings, three-listing compare, CSV export, skyline.** Listing-portal features with republishing questions; compare and watchlist now work on compounds and developers.
- **Listing history timeline, "live index" and first-observed dates.** There is one day of observation. History-based features (trends, time on market, delivery postponements) appear once eight weeks have been observed; the developer page already counts delivery-date changes.

## Run

From the repository root:

```bash
uv venv .venv                        # only if the environment does not exist
uv pip install -e ".[dev,web]"
npm --prefix web ci
npm --prefix web run build
./scripts/serve-web.sh
```

Open <http://127.0.0.1:8000>. Set `QAYEM_PORT` to change the port and `QAYEM_DB` to select an existing SQLite database. The website never creates or modifies the database.

For live frontend development, keep the API running on port 8000, then run `npm --prefix web run dev` and open <http://127.0.0.1:5174>. Vite proxies `/api` to the Python service.

After upgrading an existing database, run `qayem renormalize nawy` once to fill delivery dates from stored Nawy payloads (no fetching, no version rows).

## Data and persistence

- The server opens SQLite with `mode=ro` and `PRAGMA query_only=ON`. Responses use an explicit allowlist: no raw payloads, phone numbers or photos.
- Included: active EGP sale listings, EGP 100,000–200 million, 20–5,000 m², with a property type and a district or compound. Identified resale listings are valued by default.
- The fair-value model is fitted when the snapshot is built and refits when the database changes, at most every `QAYEM_REFRESH_SECONDS` (default 300) so a running crawl does not trigger constant refits.
- Listings not re-observed within 14 days of their source's latest observation are hidden.
- Developer launch units (`nawy_primary`) are a benchmark only: never counted as resale inventory or used to fit the model.
- Watchlist and comparison selections live in this browser's local storage (`qayem:watch`, `qayem:compare-entities`).

## Validation

```bash
.venv/bin/python -m pytest tests/ -q
npm --prefix web run build
QAYEM_WEB_URL=http://127.0.0.1:8000 npm --prefix web run test:e2e
```

The end-to-end run opens all 13 page types in Arabic and English, at desktop (1440 px) and phone (390 px) widths. It fails on runtime errors, failed API calls, horizontal overflow or untranslated interface copy, and it drives the evaluate form on a phone. Screenshots and a JSON report go to `web/test-results/`.

See [WEB_API.md](WEB_API.md) for routes and response shapes, and the methodology page for the model.

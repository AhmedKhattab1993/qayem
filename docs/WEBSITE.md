# Qayem website

A read-only comparison workspace on top of the Qayem database. It answers one question for a buyer in Egypt's resale market: **is this unit a real opportunity?** Egypt publishes no resale sale prices and AqarExit lists each unit at its old contract price, so the site does not estimate a "fair price". It compares every unit, as listed and in today's money, with what could be bought instead: the developer's current price for a similar unit, and the similar resale units listed in the same compound.

## Pages

| Route | Purpose |
|---|---|
| `/` | The question, the best opportunities now, each developer's resale units against its own prices today, how far developer prices moved since the sellers signed, how a unit is judged, and the evidence behind it |
| `/evaluate` | "Is this a real opportunity?" Describe a unit (compound, type, area, finishing, delivery, headline price, payment plan) or paste an indexed listing link. Returns its opportunity level, the comparison with the developer today and with similar units listed now, the plan's value in today's money, the total cost of buying (editable fee assumptions), what the comparison cannot see, and the similar units. Form state is in the URL, so results are shareable. |
| `/compounds`, `/compounds/:key` | Observed prices per class (resale contract and today's-money prices per m², the developer's price today), resale vs the developer (median like-for-like gap), opportunity counts, delivery and payment profile, stock mix, best opportunities first |
| `/developers`, `/developers/:key` | Resale vs the developer's own prices today, compound by compound, opportunity counts, delivery and payment profile, promised delivery dates tracked across crawls |
| `/units`, `/units/:id` | Every identified resale unit with its contract and cash-today price, **vs developer** and **vs similar units** (with its rank) and its opportunity level; sortable and filterable by level, district, developer, type, payment terms and developer price. A unit page adds both comparisons in full, the developer's price since the seller's contract year, and the similar units it is ranked against |
| `/compare` | Up to three compounds or three developers side by side |
| `/watchlist` | Units (saved from a unit page), compounds and developers kept in this browser |
| `/methodology` | The two comparisons, the level rules with live counts, the cash-equivalent rule, source coverage, and the limits |

The interface opens in Arabic (right-to-left); the header button switches to English. Tables become stacked cards on phones. `⌘K`/`Ctrl+K` or `/` opens search over compounds, developers, districts and pages.

## What was removed, and why

The site used to look like a listing portal. These were removed because they did not serve evaluation or were not supported by the data:

- **The fair value, its range and evidence grade (2026-09-27).** The model was trained on AqarExit prices, which are the sellers' old contract prices (2023–2026) rather than market prices, so its "fair price" was the typical contract price of mixed years, and its backtest measured only how well it predicted other contracts. Replaced by the two comparisons with what can be bought now. `valuation.py` keeps the model code, unused by the website.
- **District-wide "priced below peers".** Peers were district + type, and installment headlines were compared with cash prices. Peers are now the same compound, type and size, compared both as listed and in today's money.
- **The 11-check completeness score and dial.** It measured how many fields a portal filled, not whether a price was right. Replaced by an explicit "what this comparison cannot see" list.
- **Market-wide medians and the Pulse dashboard.** A median across Ras El Hekma chalets and October apartments describes the mix, not the market. Statistics now exist only inside a segment (district, compound, developer).
- **Three-listing compare, CSV export, skyline.** Listing-portal features; compare works on compounds and developers. A unit can be saved to the watchlist (2026-09-27), which shows only what its unit page already shows: price, terms, place and opportunity level.
- **Photos came back (2026-09-27, at the user's request).** A unit page shows the photos exactly as the source published them (AqarExit's structured data), loaded from the source's own links and credited to it; lists show the first photo. `qayem backfill-images` fetched them once for units stored before the parser read photos; the nightly crawl keeps new and changed units current.
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

The home page's explainer film is not in git (the master is ~160 MB). Before the build, encode it once into `web/public/media`: `./scripts/encode-explainer.sh ~/Videos/qayem/qayem-pilot-v4.mp4` (1080p and 720p H.264 with fast start, ~24 MB and ~10 MB, plus posters). The page loads only the poster until someone presses play; phones get the 720p file. For a new cut, run the script with `VERSION=v5` and update `VERSION` in `web/src/components/Explainer.tsx` (and `SECONDS` if the length changed), so browsers do not replay a cached old file.

After upgrading an existing database, run `qayem renormalize nawy` once to fill delivery dates from stored Nawy payloads (no fetching, no version rows).

## Data and persistence

- The server opens SQLite with `mode=ro` and `PRAGMA query_only=ON`. Responses use an explicit allowlist: no raw payloads, phone numbers or photos.
- Included: active EGP sale listings, EGP 100,000–200 million, 20–5,000 m², with a property type and a district or compound. Identified resale listings are compared by default.
- The comparisons are rebuilt when the database changes, at most every `QAYEM_REFRESH_SECONDS` (default 300) so a running crawl does not trigger constant rebuilds.
- Opportunity levels (`website_data.opportunity`): each comparison's gap is the less favourable of listed price and today's money. Strong: every comparison at least 15% under and one 25% under; good: 5% and 10%; pricier: 10% over on both bases; mixed: one 10% under and another 10% over; check this listing: more than 70% under the developer, 60% under similar units, or 25% under even the cheapest similar unit (an outlier to verify: a listing error or an unusually early contract); unrated: no like-for-like developer price and fewer than four other similar units. The developer comparison counts only with the same finishing. A unit page lists all the similar units it is ranked against (the nearest six until asked), each with the year its seller signed.
- Listings not re-observed within 14 days of their source's latest observation are hidden.
- Only the sources in `QAYEM_SOURCES` (default: AqarExit) and `QAYEM_BENCHMARK_SOURCES` (default: `nawy_primary`) are read. Other sources' rows are never loaded.
- Developer launch units (`nawy_primary`) are a benchmark only: never counted as resale inventory. With no benchmark source the developer comparisons are hidden.
- Compound and developer names come from `entity_aliases` (written by `qayem resolve-entities`): every spelling of a compound shows under one canonical name, in Arabic in the Arabic interface. Low-confidence answers are ignored; unresolved spellings keep their published name.
- A unit's developer comparison uses the nearest five (by size) of the developer's current units in the same compound and of the same unit type, within 1.5× its size, and needs at least two; the median cash-equivalent per m² is scaled to the unit's area. The ranking ("cheaper than buying from the developer") keeps only like-for-like finishing and leaves out prices flagged "check this listing".
- AqarExit transfers units at the owner's original contract price, with no premium («بدون أوفر»), so its price is what the seller paid the developer. The contract year is read from the stored payload (`json_extract` of that one field; the payload itself is never selected), and a unit's developer comparison reports how the developer's list price per m² moved since then (total and per year, from mid-contract-year).
- A changed database is rebuilt in the background: requests keep getting the previous snapshot until the new one is ready. The first build starts when the server starts.
- Watchlist and comparison selections live in this browser's local storage (`qayem:watch`, `qayem:compare-entities`).

## Validation

```bash
.venv/bin/python -m pytest tests/ -q
npm --prefix web run build
QAYEM_WEB_URL=http://127.0.0.1:8000 npm --prefix web run test:e2e
```

The end-to-end run opens all 13 page types in Arabic and English, at desktop (1440 px) and phone (390 px) widths. It fails on runtime errors, failed API calls, horizontal overflow or untranslated interface copy, and it drives the evaluate form on a phone. Screenshots and a JSON report go to `web/test-results/`.

See [WEB_API.md](WEB_API.md) for routes and response shapes, and the methodology page for the model.

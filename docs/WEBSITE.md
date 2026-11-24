# Qayem website

Egypt's property price guide, read-only on top of the Qayem database. It answers the buyer's first question, **what does a square metre cost here?**, with the number, the place, the date and the sources, for every district, compound and developer; then the second, **is the price I was quoted fair?**, by comparing a unit, as listed and in today's money, with the developer's current price for a similar unit and with the similar resale units listed in the same compound. Egypt publishes no sale prices, so every figure is an asking price and says so.

The brand, its colours, type, mark and the site's structure are in [BRAND.md](BRAND.md) (the square metre, adopted 2026-11-24).

## Structure

- **Header:** Price map, Price guide, Qayem Index, Articles; search, watchlist, compare, currency, language; one action, **Check a price**. Over the home hero it sits on the same lapis field.
- **Price guide:** `/districts`, `/compounds` and `/developers` are one section with three tabs (`GuideTabs`).
- **Phones:** a tab bar (Map, Guide, Check, Index, Saved) and a menu button that lists every page in the footer's four groups, with the currency switch.
- **Footer:** Prices, Tools, Read, About Qayem; the price ramp as its top rule.

## Pages

| Route | Purpose |
|---|---|
| `/` | The hero: the line, a search for a district or compound, and a mosaic of the twelve busiest districts as square tiles shaded by price per m² (nine on a phone), over four counts (listings kept, districts, compounds, sources). Then four questions as four doors (the map, the map by budget, resale against new, the price check); the price board (eight districts, filterable by region, each with its middle half and median on one shared scale); each developer's resale units against its own prices today; the monthly index beside the latest articles; how the guide is made, with the explainer film; and the price check |
| `/evaluate` | "Is this a real opportunity?" Describe a unit (compound, type, area, finishing, delivery, headline price, payment plan) or paste an indexed listing link, which fills in the same fields. Returns its opportunity level, then the total cost of buying (editable fee assumptions; cash at signing, what is paid later and about how much each quarter), the comparison with the developer today and with similar units listed now (as figures, not as a list of listings), the plan's value in today's money and what the comparison cannot see (less the fees asked for above). Form state is in the URL, so results are shareable. |
| `/compounds`, `/compounds/:key` | Observed prices per class (the resale contract price per m² and the developer's today, with both in today's money in one line below), resale vs the developer (median like-for-like gap), opportunity counts, delivery and payment profile, stock mix |
| `/developers`, `/developers/:key` | Resale vs the developer's own prices today, compound by compound, opportunity counts, delivery and payment profile, promised delivery dates tracked across crawls |
| `/units`, `/units/:id`, `/sheet/:id` | Retired 2026-11-24: a permanent redirect to the guide that covers the listing (its compound, else its district, else `/map`; `/units?compound=…` and `?district=…` to that guide). Formerly every identified resale unit with its contract and cash-today price, **vs developer** and **vs similar units** (with its rank) and its opportunity level; each plan unit shows about what it costs per quarter. Filterable first by a buyer's budget and needs (asking price, cash today, paid at signing, bedrooms, area, delivery), then by district, developer, type, level, payment terms and developer price; sortable, including newest listings first. A filtered search can be saved to the watchlist. A unit page opens with its verdict (level, both gaps, rank, the source link), then its figures, then both comparisons in full, the developer's price since the seller's contract year, and the similar units it is ranked against |
| `/compare` | Up to three compounds or three developers side by side |
| `/watchlist` | Compounds and developers, kept in this browser. A compound or district page can turn on a WhatsApp or e-mail alert |
| `/districts`, `/districts/:key` | The directory: every district with a published figure, grouped by region, each with its median asking price per m². A district page opens with its answer sentence, then its segments (each range drawn as a bar on the table's own scale), its compounds against the developer, delivery and payment, history and the questions buyers ask |
| `/privacy` | What Qayem keeps when someone asks for an alert or a callback, and why |
| `/methodology` | The two comparisons, the level rules with live counts, the cash-equivalent rule, source coverage, and the limits |

The interface opens in Arabic (right-to-left); the header button switches to English. Tables become stacked cards on phones. `⌘K`/`Ctrl+K` or `/` opens search over compounds, developers, districts and pages.

Styles are five files in `web/src/styles`: `base.css` (tokens, type, buttons, forms), `shell.css` (header, menu, footer, tab bar, search, states), `ui.css` (sections, page heads, tables, figures, tags), `home.css` and `pages.css`.

## What was removed, and why

The site used to look like a listing portal. These were removed because they did not serve evaluation or were not supported by the data:

- **The fair value, its range and evidence grade (2026-09-27).** The model was trained on AqarExit prices, which are the sellers' old contract prices (2023–2026) rather than market prices, so its "fair price" was the typical contract price of mixed years, and its backtest measured only how well it predicted other contracts. Replaced by the two comparisons with what can be bought now. `valuation.py` keeps the model code, unused by the website.
- **District-wide "priced below peers".** Peers were district + type, and installment headlines were compared with cash prices. Peers are now the same compound, type and size, compared both as listed and in today's money.
- **The 11-check completeness score and dial.** It measured how many fields a portal filled, not whether a price was right. Replaced by an explicit "what this comparison cannot see" list.
- **Market-wide medians and the Pulse dashboard.** A median across Ras El Hekma chalets and October apartments describes the mix, not the market. Statistics now exist only inside a segment (district, compound, developer).
- **Three-listing compare, CSV export, skyline.** Listing-portal features; compare works on compounds and developers. A unit can be saved to the watchlist (2026-09-27), which shows only what its unit page already shows: price, terms, place and opportunity level.
- **Unit compare came back (2026-10-10).** Buyers shortlist two or three units and choose between them. It compares like the rest of the site: cash today, at signing, per quarter, both gaps and the price per m² in today's money; only like-for-like figures are marked as lowest. Budget filters, quarterly installments and saved searches were added in the same pass.
- **Lead capture and alerts (2026-11-21).** With a handful of visitors a day and nothing captured, the site now asks, after the verdict and never before it, whether the reader wants the next step: a checklist before paying a deposit (good deals), the developer's own current offer (when buying new costs less), alerts for a search, compound or district, or buyer interest for a seller. Contact details go to a separate database and are never shared with brokers without permission. See [GROWTH.md](GROWTH.md).
- **History came back (2026-11-21).** With more than eight weeks observed, compound, developer and district pages show listings that left the market in 30 days, days on the market, price cuts and the developer's list-price moves; units show their own price cut.
- **Photos came back (2026-09-27, at the user's request).** A unit page shows the photos exactly as the source published them (AqarExit's structured data), loaded from the source's own links and credited to it; lists show the first photo. `qayem backfill-images` fetched them once for units stored before the parser read photos; the nightly crawl keeps new and changed units current.
- **Photos removed again (2026-11-22).** Sources' photos are their copyright, so the API serves none (`images` is empty, `photo` is null) and shared links use Qayem's own card. See [STRATEGY.md](STRATEGY.md), section 11.
- **No personal data from sources (2026-11-22).** Parsers keep no phone numbers, names or contact keys; free text has contacts replaced. `qayem scrub-personal` removed what earlier crawls stored, in rows and history, and runs in every nightly update.
- **`/llms.txt` (2026-11-22).** A short map of the site for AI assistants, beside `robots.txt` and the sitemap.
- **Individual listings (2026-11-24).** The strategy of 2026-11-22 makes Qayem a price guide, not a listing portal ([STRATEGY.md](STRATEGY.md), sections 2 and 14). The Units search, unit pages, deal sheets, unit tables on compound and district pages, saved searches, unit compare and the units on the watchlist are gone, and so are `/api/units` and `/api/units/{id}`. Old addresses redirect permanently to the guide that covers the listing. Listings remain the input to every median, range and comparison. A pasted listing link fills in the price check's fields instead of opening a listing, the check no longer lists the similar units behind it, and alerts say how many listings in a compound or district were added or cut in price, with a link to the guide.
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
- Opportunity levels (`website_data.opportunity`): each comparison's gap is the less favourable of listed price and today's money. Strong: every comparison at least 15% under and one 25% under; good: 5% and 10%; pricier: 10% over on both bases; mixed: one 10% under and another 10% over; check this listing: more than 70% under the developer, 60% under similar units, or 25% under even the cheapest similar unit (an outlier to verify: a listing error or an unusually early contract); unrated: no like-for-like developer price and fewer than four other similar units. The developer comparison counts only with the same finishing.
- Listings not re-observed within 14 days of their source's latest observation are hidden.
- Only the sources in `QAYEM_SOURCES` (default: AqarExit and Nawy resale) and `QAYEM_BENCHMARK_SOURCES` (default: `nawy_primary`) are read. Other sources' rows are never loaded.
- Developer launch units (`nawy_primary`) are a benchmark only: never counted as resale inventory. With no benchmark source the developer comparisons are hidden.
- Compound and developer names come from `entity_aliases` (written by `qayem resolve-entities`): every spelling of a compound shows under one canonical name, in Arabic in the Arabic interface. Low-confidence answers are ignored; unresolved spellings keep their published name.
- A unit's developer comparison uses the nearest five (by size) of the developer's current units in the same compound and of the same unit type, within 1.5× its size, and needs at least two; the median cash-equivalent per m² is scaled to the unit's area. The ranking ("cheaper than buying from the developer") keeps only like-for-like finishing and leaves out prices flagged "check this listing".
- AqarExit transfers units at the owner's original contract price, with no premium («بدون أوفر»), so its price is what the seller paid the developer. The contract year is read from the stored payload (`json_extract` of that one field; the payload itself is never selected), and a unit's developer comparison reports how the developer's list price per m² moved since then (total and per year, from mid-contract-year).
- A changed database is rebuilt in the background: requests keep getting the previous snapshot until the new one is ready. The first build starts when the server starts.
- Watchlist and comparison selections live in this browser's local storage (`qayem:watch`, `qayem:compare-entities`); units saved there before 2026-11-24 are ignored. Alerts, leads and first-party visit counts go to the separate leads database (`QAYEM_LEADS_DB` locally, `qayem-leads` on Cloudflare); see [GROWTH.md](GROWTH.md).
- Each public route's head (title, description, canonical, Open Graph, JSON-LD) and a short crawlable summary are written by the server from the same documents the API serves (`src/qayem/seo.py`); `/sitemap.xml` and `/robots.txt` are generated from the catalogue.
- The quarterly installment is the balance still owed divided into equal quarterly payments over the remaining years, the same assumption the today's-money conversion makes. Sources do not publish the actual schedule, so it is shown as approximate.

## Validation

```bash
.venv/bin/python -m pytest tests/ -q
npm --prefix web run build
QAYEM_WEB_URL=http://127.0.0.1:8000 npm --prefix web run test:e2e
```

The end-to-end run opens every page type in Arabic and English, at desktop (1440 px) and phone (390 px) widths. It fails on runtime errors, failed API calls, horizontal overflow (including a table scrolling sideways inside its card) or untranslated interface copy. It drives the evaluate form and the unit filters on a phone, checks that a unit's verdict starts on the first screen, applies a budget and saves the search, and compares two units on desktop and phone. Screenshots and a JSON report go to `web/test-results/`.

See [WEB_API.md](WEB_API.md) for routes and response shapes, and the methodology page for the model.

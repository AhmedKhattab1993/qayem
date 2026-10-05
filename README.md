# Qayem — what is this resale unit really worth?

**Qayem (قيم / تقييم) — "to evaluate."** Egypt's resale market is priced by
compound, developer, delivery date and payment plan, yet listings are compared
by area. Qayem reads the secondary market from AqarExit's contract-transfer
(تنازل) marketplace, converts every payment plan to cash-today terms, and compares
each unit with what could be bought instead: the developer's current price for a
similar unit and the similar resale units listed in the same compound. It does not
estimate a "fair price": AqarExit lists units at their old contract prices, and
Egypt publishes no resale sale prices.

**Sources in use.** AqarExit is the only complete record of the secondary market
(paid amount, balance and installments for every unit), so the website, the model,
the nightly crawl and description enrichment use AqarExit only. The other parsers
below still work and their rows stay in the database, unused. `QAYEM_SOURCES`
changes the selection: `QAYEM_SOURCES=aqarexit,nawy` or `QAYEM_SOURCES=all`.

**Developer prices.** Nawy's developer-sale units (`nawy_primary`: each developer's
current price and payment plan, per unit) are crawled nightly as a price benchmark
(`QAYEM_BENCHMARK_SOURCES`, `none` turns it off). They are never listed, fitted or
enriched; the website compares each AqarExit unit with the developer's current price
for a similar unit in the same compound. AqarExit's compound and developer names are
free text («باديا», «Badya», «بادية»), so `qayem resolve-entities` maps each spelling to
a canonical compound, its Arabic name and Nawy's name for it (`src/qayem/entities.py`).
Property Finder's new-projects section was considered and is walled (CloudFront 403,
even for robots.txt); it is not crawled.

- **Opportunity levels:** strong / good / in line / mixed / pricier / check this
  listing / unrated, from the two comparisons, each on the less favourable of listed
  price and today's money. Details: the website's Methodology page and
  `src/qayem/website_data.py`. (`src/qayem/valuation.py` still holds the earlier
  fair-value model; the website no longer uses it.)
- **Website:** compare a unit, compounds, developers, units, compare, watchlist
  and methodology, in Arabic and English. See [docs/WEBSITE.md](docs/WEBSITE.md).
- **Pipeline:** eight parsers into one SQLite database with a full lifecycle per
  listing and a nightly crawl. See [docs/OPERATIONS.md](docs/OPERATIONS.md).
- Product direction: [docs/VISION.md](docs/VISION.md).

## Website

```bash
uv pip install -e ".[dev,web]"
npm --prefix web ci
npm --prefix web run build
./scripts/serve-web.sh
```

Open <http://127.0.0.1:8000>. The website reads `qayem.db` read-only.

## Sources

| Source   | What it parses                                                        | Resale signal |
|----------|------------------------------------------------------------------------|---------------|
| `nawy`   | `/search?sale_type=resale` units via `__NEXT_DATA__` (~12.5k units, delivery dates, full payment plans) | By filter construction |
| `nawy_primary` | `/search?sale_type=developer_sale` launch units (~6.8k) | Primary market: launch-price benchmark only |
| `aqarexit` | Sitemap of every contract-transfer (تنازل) unit page (~7.3k), incremental by `lastmod`; cash now, balance owed, installment and years left per unit | By construction; documents verified by AqarExit |
| `opensooq` | City category SERPs via `__NEXT_DATA__` (apartments/villas/buildings/townhouses/farms-chalets) | Keyword heuristic |
| `aqarmap` | `/en/for-sale/property-type/{city}/` SSR cards + RSC `isResaleInstallment` flag | Flag + heuristic |
| `semsar` | `/3akarat?r=70&g=0&cid=…&p=N` schema.org microdata cards (all governorates) | «تمليك» heuristic |
| `gpm`    | Dedicated `/en/resale` catalogue + detail pages                         | Dedicated catalogue |
| `coldwellbanker` | Property sitemap (~23.8k URLs) + detail "Sale Type" field       | Per-listing `Sale Type: Resale` field |

Sources assessed and not added (Property Finder, Dubizzle, Bayut are
protection-walled; others lack structural resale data) are listed in
[docs/OPERATIONS.md](docs/OPERATIONS.md).

## Install

```bash
uv venv .venv                       # or: python3 -m venv .venv
uv pip install -e ".[dev]"          # or: .venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
qayem init                          # create qayem.db (path: QAYEM_DB env var overrides)

qayem parse nawy                    # full run (completes naturally → enables removal marking)
qayem parse opensooq                # cairo apartments (source default scope)
qayem parse opensooq --city giza --category villas
qayem parse aqarmap --city cairo --max-pages 5
qayem parse semsar --category villas
qayem parse gpm                     # resale catalogue, 100-detail budget
qayem parse coldwellbanker          # newest 200 sitemap properties
qayem parse all --dry-run           # everything, no DB writes

qayem crawl                         # the full nightly plan: every scope, each with a time budget
qayem health                        # per-source health; exit 1 if any source needs attention
qayem renormalize nawy              # re-parse stored payloads with the current parser (no fetching)
qayem renormalize semsar            # fill empty columns from Semsar's template descriptions
qayem renormalize aqarexit          # derive missing installment terms from stored AqarExit payloads
./scripts/install-cron.sh           # schedule the nightly crawl (02:30); see docs/OPERATIONS.md

qayem status                        # last run per source + DB totals
qayem list --source nawy --resale --min-price 3000000
qayem list --status removed         # what disappeared from sources
qayem show 42                       # one property + full change history
qayem removed --since 2026-09-01    # removal audit

qayem enrich-descriptions --dry-run  # preview the next batch of 40 listings
qayem enrich-descriptions            # one batch: 40 listings in one headless Pi call
qayem enrich-descriptions --batches 5 --source opensooq
qayem enrich-descriptions --batches 0  # continue until no eligible rows remain
qayem enrich-descriptions --retry-failed --batches 0 --workers 4  # retry recorded failures
qayem enrich-descriptions --since 2026-09-26 --batches 0  # only listings first seen since
qayem enrich-revoke --dry-run        # fills from earlier prompt versions that would be undone
qayem enrich-status                  # claimed / done / failed counts

qayem resolve-entities --dry-run     # spelling pairs waiting for canonical names
qayem resolve-entities               # resolve them (glm-5.3-flash, 120 pairs per Pi call)
```

Every `parse` prints a summary: pages fetched, seen / created / updated /
unchanged / relisted / removed counts.

`enrich-descriptions` sends **only each listing's title and description** —
40 listings per fresh headless Pi call — to `zai-coding-cn/glm-5.3-flash`
with low reasoning effort. The extraction rules in
`src/qayem/enrichment_spec.md` and a sparse JSON schema constrain the response.
The runner disables tools, extensions, skills, project context and session storage;
it checks the returned provider, model, completion status and JSON schema before
accepting any facts. Configure this provider in Pi locally and verify it with
`pi auth check --provider zai-coding-cn --model glm-5.3-flash`.

The older Codex precision benchmark in `bench/enrichment/RESULTS.md` is historical;
it is not an accuracy measurement for GLM. Live Arabic and English extraction
fixtures have been checked with the new runner and the same grounding validators.

Only listings the website could show are sent, newest first: active,
not Nawy (its title and description are generated from the payload the
parser already reads), for sale in EGP within the website's price
range, a unit type the valuation covers (or none yet), at least one missing
field the website or valuation uses (unit type, area, resale, finishing,
delivery, compound, down payment, plan length), and text that mentions one of
them. This cut the candidates from 29,114 to about 3.6k; on the benchmark the
text pre-filter kept 261 of 266 extractable facts.

Every proposed value must then be grounded in the listing's own text: the
unit type, finishing and delivery wording must appear, names must appear as
written, amounts and plan lengths must match numbers in the text, and room
counts must sit next to their label. Only columns the source left empty are
filled; a known source value is never overwritten. Multi-unit ads (projects,
several units) get nothing applied, and a stated down payment equal to the
listing's price is refused and noted, since that price is probably the down
payment. Listings missing from a batch answer are asked once more, then
recorded as failed. By default one batch runs; `--batches 0` processes all
eligible active listings. The Pi CLI must be installed and authenticated
on the machine running the job.

The `property_enrichments` table stores the latest durable outcome per
property, with the model, reasoning effort and prompt version used. Each
property is claimed before its call, and ordinary later runs skip it whether
the result fills fields, returns no clear facts, fails, or is interrupted.
`--retry-failed` explicitly reclaims only failed rows; successful results
remain untouched. A timed-out call is retried once (600 seconds per attempt).
`enrich-status` shows the outcomes; a `claimed` row after interruption is
intentionally skipped. `enrich-revoke` undoes fills from earlier prompt
versions (a column is reset only while it still holds the old value; every
reverted value is written to `logs/enrich-revoke-*.json` first) and makes
those listings eligible again. Accepted values are reapplied on a later source parse
only while the listing's title and description are unchanged and the source
still leaves that field missing.

## State tracking

- Each listing is keyed by `(source, source_listing_id)`; content changes are
  detected by hash and stored as `property_versions` rows with field-level
  diffs (old → new).
- Listings that disappear are marked `status='removed'` (rows are never
  deleted) and are automatically **relisted** if they reappear.
- **Guarded removals:** a scope only marks removals when it finished *complete*
  (pagination ended naturally, or a complete inventory such as a sitemap was
  read; not capped by `--max-pages`, a time budget, or a block). Truncated or
  failed runs are recorded as `partial`/`failed` and never produce false
  removals. Listings confirmed present without a fetch (AqarExit's sitemap)
  are refreshed before removals are computed.

## Politeness & blocks

All sources share one fetcher: browser User-Agent, per-host rate limit
(2 s ± 1 s jitter by default, tune with `--min-interval`), retries on
timeouts and 5xx with 3/9/27/60 s backoff, and immediate abort on 403/429 or a
challenge page (WAF block) — the run is recorded as `partial` and nothing is
marked removed. Nothing is fetched that robots.txt disallows, and no bot
protection is bypassed. Aqarmap's WAF is path-sensitive:
only the exact URL shapes in `sources/aqarmap.py` are used.

## Development

```bash
.venv/bin/python -m pytest tests/ -q
```

Tests run entirely on captured fixtures (`tests/fixtures/`) — no network
needed. When a source's markup changes, refresh its fixture and update the
assertions. Source payloads are also kept in each property's `raw` JSON
column so data can be re-normalized later without re-fetching.

For website changes, use local development, then
[Cloudflare staging](docs/CLOUDFLARE.md#development-and-staging), then production.
Staging has a separate database and manual refresh from saved cloud data, reusing
existing enrichment instead of running another crawl or AI batch.


## Cloudflare backend

The React site and an async Python Workers API can serve the same endpoints from
Cloudflare D1. The isolated cloud updater schedules crawling, entity resolution
and Pi enrichment at 02:30 Africa/Cairo. Its canonical SQLite database is restored
from and checkpointed to private R2; complete, healthy catalogues are published
to D1. See [cloud updates and commissioning status](docs/CLOUD_UPDATES.md) and
[website deployment](docs/CLOUDFLARE.md). Website releases use the active cloud
dataset; publishing the local database requires `QAYEM_LOCAL_PUBLISH=1` explicitly.

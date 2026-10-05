# Operations: scheduled crawling and source health

History is Qayem's moat: time on market, price cuts, delivery postponements and trends all need the same listings observed again and again. A nightly crawl keeps that history accruing.

## The cloud nightly crawl

The independent Cloudflare updater is scheduled at 02:30 Africa/Cairo. It runs
the same crawl plan and Pi stages, saves the canonical database privately in R2,
and publishes a verified D1 catalogue after health checks. Follow its migration
status and operating commands in [CLOUD_UPDATES.md](CLOUD_UPDATES.md).

## The local crawl (fallback)

```bash
./scripts/install-cron.sh              # installs: 30 2 * * * scripts/crawl.sh (02:30 local time)
QAYEM_CRAWL_TIME="15 4" ./scripts/install-cron.sh   # or choose another minute/hour
crontab -l                             # the line is tagged "# qayem-nightly-crawl"
```

`scripts/crawl.sh` (safe to run by hand):

1. takes `logs/crawl.lock`, so a second invocation exits and notes it in `logs/crawl-skipped.log`;
2. runs `qayem crawl`, the production plan in `src/qayem/crawl.py`, limited to the sources in
   use (`QAYEM_SOURCES`, AqarExit by default; `qayem health` and enrichment follow the same setting)
   and the price benchmarks (`QAYEM_BENCHMARK_SOURCES`, Nawy's developer sales by default);
3. runs `qayem resolve-entities --max-minutes 30` (override with `QAYEM_ENTITY_MINUTES`), which
   gives new compound/developer spellings their canonical names and Nawy match; only new pairs
   are sent, so a night costs a call or two;
4. runs `qayem enrich-descriptions --batches 0 --max-minutes 120` (override the budget with
   `QAYEM_ENRICH_MINUTES`), which fills missing fields of new listings from their text with
   `pi --print` (`/opt/homebrew/bin` and `~/.local/bin` are on cron's PATH; see the README);
5. runs `qayem health --write logs/health.json`;
6. logs to `logs/crawl-YYYY-MM-DD.log` and deletes logs older than 30 days.

Enrichment failures never fail the crawl. A run starts no new batch after its time budget or
after two consecutive batches failed entirely (a Pi/provider outage, logout or quota), so one bad
night costs at most a few batches. Failed listings are retried on later nights, up to three
runs in total (`--retry-failed` forces another try); claims left by a crashed run are taken
again after six hours.

## The crawl plan

| Scope | Budget | Notes |
|---|---|---|
| `nawy` (resale) | 100 min, 3 s/request | ~1,050 pages. A page that still fails after retries is skipped; 5 in a row end the scope. |
| `nawy_primary` (developer launches) | 110 min, 3 s/request | ~570 pages (its search pages respond slowly). Launch-price benchmark only, never resale evidence. |
| `aqarexit` | 120 min | Sitemap-driven: every unit page listed in `sitemap.xml` is present; only new or changed pages (by `lastmod`) are fetched. |
| `gpm` | 60 min | Dedicated resale catalogue plus details. |
| `opensooq` × 3 cities × 5 categories | 15 min each | Capped by the site at 50 pages per query. |
| `aqarmap` × cairo, giza, alexandria | 45 min each | Path-sensitive WAF: known URL shapes only. Cairo exceeds 1,000 pages (~20k listings, mostly not resale), so each night refreshes the first ~1,000 pages and the scope is recorded partial. |
| `semsar` × apartments, villas, chalets | 60 min each | Classifieds. Paging moved to `/3akarat?r=70&g=0&a=0&cid=…&p=N` in 2026-09; the old `.asp` form returned page 1 for every page number. |
| `coldwellbanker` | 40 min | Newest 400 of ~24k sitemap URLs per night (partial by design). |

Rules the engine enforces:

- **Only complete scopes mark removals.** A scope stopped by its budget, an error, or a page cap is recorded `partial` and never marks unseen listings as removed.
- **Presence without a fetch counts.** A source that confirms a listing is still listed (the AqarExit sitemap) refreshes its `last_seen_at` before removals are computed.
- **One run per source at a time.** A per-source lock (`.qayem-locks/`) makes a concurrent `qayem parse X` or crawl of the same source skip.
- **Broken paging is caught.** A run that sees each listing more than twice on average (a site returning the same page for every page number) records an error and marks no removals; Semsar also stops as soon as a page repeats the previous one.
- **Crashes are recorded.** An exception in one source marks its run `failed` and the crawl moves on. Runs left `running` for more than 6 hours by a killed process are closed as failed at the next crawl.
- **Short write transactions.** Commits every 100 listings or 15 seconds; the database runs in WAL mode so the website never waits on a crawl.
- **Retries.** Timeouts and 5xx responses retry with 3, 9, 27 and 60 s pauses. A 403/429 or challenge page (WAF) is never retried.

## Source health

```bash
.venv/bin/qayem health        # exit code 1 if any scheduled source needs attention
```

| State | Meaning |
|---|---|
| `ok` | Produced listings recently at its usual volume |
| `running` | A run is in progress (started under 6 hours ago) |
| `stale` | No listings for more than 36 hours |
| `dropped` | Latest run produced under half its recent median for the same scope: a markup change or block |
| `failing` | The last two runs failed, or no run has ever produced listings |
| `never` | No run recorded |

`qayem health` also reports an `enrichment` row: `failing` when at least 10 listings and over 20%
of those finished in the last 24 hours failed, `stale` when listings are waiting and nothing was
enriched for 36 hours, otherwise `ok` (with the backlog and any abandoned claims in the detail).
The JSON report carries the same numbers under `enrichment`.

The website hides listings that were not re-observed within 14 days of their source's latest observation, so a source that only samples its inventory cannot leave sold units looking active.

## Backfills and upgrades

```bash
.venv/bin/qayem parse aqarexit               # one-off, no time budget (first sitemap backfill: ~7,300 pages, ~5 h)
.venv/bin/qayem renormalize nawy             # re-parse stored payloads after a parser change; no fetching
.venv/bin/qayem renormalize nawy_primary
.venv/bin/qayem renormalize aqarexit         # derive missing installment terms (balance ÷ installment, ≤ 10 years)
```

## Sources not added, and why

| Source | Status from this host (2026-09-26) | Decision |
|---|---|---|
| Property Finder Egypt | CloudFront 403 on every path, including robots.txt | Needs a data agreement; Qayem does not bypass protection |
| Dubizzle Egypt | Cloudflare 403 on every path | Needs a data agreement |
| Bayut Egypt | JavaScript challenge (503) | Needs a data agreement |
| Aqar Misr (realestate.eg), Aqar Ya Masr | Reachable | Resale is not marked structurally; keyword classification would add noise, not credibility |
| Inland Properties (IPG) | Reachable | ~90 resale units identified only by title; low yield |

Nawy still supplies most identified resale listings. The most effective way to reduce that dependence is a data partnership with one of the three large portals.

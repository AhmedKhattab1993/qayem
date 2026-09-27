# What Qayem is

## The one-line version

Qayem answers the buyer's question in Egypt's secondary property market:
**what is this unit really worth?** It values units by compound, developer,
delivery date and payment plan, not by area alone, publishes how accurate
that is, and says so when the evidence is too thin. A user marketplace is the
designed endgame, deliberately deferred until the data and the trust layer
are strong enough to carry it.

## The name

**Qayem — from قيم / تقييم: to value, to evaluate.** The platform's job is
evaluation: of individual units (is this offering fairly priced and fully
documented?) and of the market as a whole (where are prices, how fast do
units move, what is resale trading at versus primary?).

## The problem

Egypt's property conversation is dominated by primary-market marketing:
"starting from" prices, 8-year plans, renders of buildings that don't exist.
The secondary market — where real units change hands — is where prices are
actually discovered, but it leaves almost no public trace:

- It is fragmented across classifieds (OpenSooq, Semsar), proptech platforms
  (Nawy, AqarExit), and brokerages (GPM, Coldwell Banker), each with its own
  schema and its own blind spots.
- Listings are ephemeral and unaudited. A unit sells and its only price
  evidence vanishes; incomplete and bait listings sit next to serious ones
  with no way to tell them apart.
- Nobody publishes time-on-market, price-cut behavior, or a resale-vs-primary
  spread. Buyers evaluate by gut and by what a broker tells them.

## The core (now): evaluation & analytics engine

A sync engine that watches secondary-market listings across eight sources and keeps a lifecycle per unit — `new → repriced → removed →
relisted`, with field-level diffs and guarded, scope-aware removals. From
regular runs it produces what no portal publishes:

- asking-price medians over time, by city / district / compound / type
- time-to-delist and price-cut frequency — i.e. liquidity
- installment-structure comparisons (cash-now vs total, down payments)
- a resale-vs-launch spread per compound (developer launch prices from Nawy,
  priced like for like against the resale model)

This is the moat: it compounds. Every week of crawl history makes every
evaluation sharper, and no competitor can backfill it.

## The fair-value standard

Portals list prices; Qayem values them. The standard is public:

- **Cash today first.** A headline on a seven-year plan is not a cash price.
  Remaining installments are discounted to today's money before any comparison.
- **The compound sets the price.** Each unit is valued from its district, its
  developer within that district, and its compound, each level trusted in
  proportion to its evidence, then adjusted for unit type, finishing,
  delivery, plan length and size.
- **Measured, not asserted.** Every value carries an evidence grade (A/B/C) and
  a range calibrated on units the model has not seen; the backtest is published.
- **No guessing.** Thin evidence, unknown payment terms, or a price 2.5× away
  from any comparable get "not positioned", "insufficient" or "check this
  listing", never a confident number.

The completeness score it replaced measured how many fields a portal filled
in, not whether a price was fair. The same fair-value standard will later be
the first thing a user-submitted listing shows.

## Content — video and market analysis

The analytics engine makes content cheap and defensible: recurring
market-analysis videos (price movements, liquidity by area, resale-vs-primary
spreads) generated from Qayem's own index. Unit spotlights come later and only
for stock whose rights we hold (verified or first-party). Content is how the
evaluation brand reaches the market before any listing product exists.

## Deferred by design: listings & marketplace

Qayem is designed to become a curated secondary marketplace — user listings
valued by the same fair-value standard, verification badges, evaluation context
per unit. Deferred for now, deliberately:

- **The engine compounds; the marketplace doesn't.** Every week of crawl
  history makes evaluation better. A marketplace is mostly ops (verification,
  moderation, trust) until it reaches critical mass.
- **Coverage isn't there yet.** The biggest resale source (Dubizzle) is still
  outside the pipeline; the marketplace promise would rest on partial data.
- **The brand must be earned.** An evaluation platform that also sells
  listings has a ratings-agency-rates-its-own-clients problem; entering
  listings late — with visible scoring, labeled first-party vs aggregator
  stock, and an established index — turns that risk into a feature.

When the time comes, the transition is cheap: the schema, the scoring, and
the evaluation context are exactly what a listing form and a listing page
need.

## What exists today

- Eight parsers (Nawy resale, Nawy developer launches, AqarExit's full sitemap,
  OpenSooq, Aqarmap, Semsar Masr, GPM, Coldwell Banker) into one normalized
  schema, with source payload and resale evidence kept per row.
- A lifecycle engine with guarded, scope-aware removals, a nightly crawl with
  per-source time budgets, locks and a health check (docs/OPERATIONS.md).
- The fair-value model and backtest (`src/qayem/valuation.py`).
- The website: evaluate a unit, compounds, developers, units, compare,
  watchlist and methodology, in Arabic and English.

## Sequencing

1. **Coverage + freshness** (running): nightly crawl; history accrues from
   2026-09-26. Reduce Nawy concentration through a data agreement with
   Property Finder, Dubizzle or Bayut (all protection-walled to crawlers).
2. **Fair value** (live): model, backtest, evaluate tool, compound and
   developer benchmarks, resale-vs-launch spread.
3. **History analytics** (after 8 weeks of observation): time on market,
   price cuts, delivery postponements per developer, trends.
4. **Content loop**: market-analysis videos from the index.
5. **Curated listing surface** (deferred): read-only display over clean data.
6. **User marketplace + verification** (deferred): listings, documents,
   badges, first-party data.

## Open questions to settle deliberately

- **Republishing rights**: aggregator listings are used for analytics now;
  any future public display needs attribution + link-through until direct
  agreements exist. User listings are unambiguously ours.
- **Verification**: what "documents verified" means concretely (AqarExit
  already does contract + receipts review; the bar must be as high or the
  badge is worthless).
- **Valuation credibility**: fair values rest on asking prices, not
  transactions. Until transaction evidence exists (a partner, or first-party
  deals), the published backtest and ranges are the honesty mechanism.

## Principles

1. **Nothing is deleted.** Removal is a state, not an operation.
2. **Scope honesty.** A partial crawl never produces conclusions.
3. **Evaluation before listing.** If we can't value it with evidence, we say so.
4. **One standard.** Aggregator and first-party listings are valued
   identically and labeled distinctly.
5. **Be a polite guest.** Rate-limited, no protection bypassing — the data
   must stay reproducible tomorrow.
6. **Keep the raw.** Parsers will break; stored payloads make recovery cheap.

# Qayem web API

Read-only JSON over the Qayem SQLite database. All money is EGP. Shapes are summarized; `web/src/types.ts` is the typed reference.

## Core objects

```ts
Payment = {terms: 'cash' | 'plan' | 'partial' | 'unknown', cash_equivalent: number | null,
           remaining: number | null, remaining_share: number | null, years: number | null, discount: number | null}
Valuation = {status: 'valued' | 'insufficient' | 'not_modelled', reason?: string,
             grade?: 'A' | 'B' | 'C', fair_value?, fair_low?, fair_high?, fair_ppm?,
             basis?: 'cash_equivalent' | null, compared_price?: number | null, deviation?: number | null,
             verdict?: 'below' | 'within' | 'above' | 'suspect' | null, fair_headline?: number | null}
Unit = {id, source, source_name, source_url, title, property_type, class: 'apartment' | 'chalet' | 'house' | null,
        price, area_m2, price_per_m2, bedrooms, district, compound: {key, name} | null, developer: {key, name} | null,
        finishing_class, delivery: {bucket, date, years}, payment: Payment, valuation: Valuation, is_resale}
```

- `terms`: `cash` (structured source, no plan), `plan` (down payment and term known), `partial` (installments, term unknown), `unknown`.
- `cash_equivalent` = paid at signing + remaining balance in equal quarterly installments discounted at 20% a year.
- `verdict` is only set when the price is known in cash-equivalent terms. It is `below` / `above` outside the grade's calibrated 80% range, and `suspect` beyond 2.5× from the fair value (a likely listing error). Units with unknown or partial terms are valued but not positioned.
- `grade`: A = compound with ≥6 comparable listings; B = compound with 2–5, or developer-in-district with ≥6; C = district only. No grade → `insufficient`.

## Routes

- `GET /api/health`
- `GET /api/overview` → counts, `observation_days`, `history_ready`, `sources[]` (count, resale_count, valued_count, status), `scope` (source shares), `backtest` (overall, per grade, naive baseline), `effects` (type, finishing, delivery, plan, area_doubling), `payment_terms`, `plan_median_discount`, `verdicts`, `developer_premiums[]`.
- `GET /api/catalog` → `{districts[], compounds[], developers[], property_types[]}` for search and forms.
- `/api/units` and `/api/units/{id}` were retired on 2026-11-24 and return 404: Qayem publishes prices, not listings (docs/STRATEGY.md, section 14). Listings stay the input to every figure below.
- `GET /api/compounds?q=&district=&developer=&sort=units|premium_desc|premium_asc|name&page=&page_size=` → `Page<Compound> & {district: District | null}`.
- `GET /api/compounds/{key}` → `{compound, district, developer}`. `compound.launch` (and `developer.launch`) compares the developer's current launch units with the model's resale value for the same unit on the same plan: `{units, median_spread, median_headline_ppm, median_cash_ppm, median_plan_years, median_down_share, latest_delivery_year, phases[]}` or `null`. A compound has `classes[]` (reference fair ppm for a finished, ready, typical-size unit, grade, premium vs district, median asking and cash-equivalent ppm), a delivery and payment profile, `types`, `area_range` and `scope`.
- `GET /api/developers?q=&sort=&page=&page_size=` → `Page<Developer>`. Premium sorts include developers with ≥20 valued units.
- `GET /api/developers/{key}` → premium vs district (with `premium_basis`), `compounds[]`, `districts[]`, `delivery_changes` (tracked units, postponed, brought forward), profile and scope.
- `GET /api/districts/{key}` → district benchmark per class, profile and scope.
- `GET /api/evaluate?property_type=&area=&price=&compound=&district=&developer=&down_payment=&installment_years=&delivery=ready|YYYY|YYYY-MM&finishing=` → `{inputs, payment, launch, peers, opportunity, unknowns[], status, district_guide?}`; the similar listings behind `peers` are not returned. Needs a compound or a district. An unknown compound falls back to district level (`notes: ['compound_not_found']`); a district without a compound uses the non-compound benchmark and may be `insufficient`.
- `GET /api/lookup?url=` → `{query: {property_type, area, price, compound | district, down_payment?, installment_years?, delivery?, finishing?}}` for an indexed listing link (host and path compared; links shared by several listings do not match): the listing's facts as `/api/evaluate` parameters, so the price check runs on them.

- Compounds, developers, districts and the overview carry `history`: `delisted_30d`, `turnover_30d`, `new_30d`, `median_days_listed`, `tracked_delisted`, `price_cuts_60d`, `price_rises_60d`, `median_cut`, `developer_change_60d` (average list-price change of the developer's same units), `developer_tracked`, `developer_rising`, `developer_falling`. The overview's adds `cohort_start`. A district lists its `compounds[]` (largest first, with `median_gap`) and `good_count`.

### Growth routes (separate leads database)

- `GET /api/config` → `{leads, turnstile_site_key, email_alerts}`: which forms can be offered.
- `POST /api/events` `{type, path, visitor, unit_id?, entity?, referrer?, utm_*?, meta?}` → 204 always. Types: pageview, outbound_click, evaluate_run, share_click, cta_click, lead_open, alert_open, sheet_view, lookup.
- `POST /api/leads` `{kind, role?, name?, whatsapp? | email?, unit_id?, compound?, intent?, path?, utm_*?, lang?, turnstile?, website (honeypot)}` → `{ok}`. Kinds: developer_price, resale_check, deal_sheet, seller, broker, general. Errors: 422 `invalid` / `invalid_contact`, 403 `verification_failed`, 429 `rate_limited`, 503 `unavailable`.
- `POST /api/alerts` `{channel: email|whatsapp, destination, query, label, role?, lang?, turnstile?, website}` → `{ok, existing?}`. The website sends `compound=<key>` or `district=<key>`; alerts saved earlier with the retired Units search's filters keep working. Each message says how many matching listings were added or cut in price and links to the compound, district or developer guide (`growth.guide_path`), never to a listing.
- `GET|POST /api/alerts/unsubscribe?token=` → a small HTML confirmation.
- `GET /api/admin/funnel?days=30` with `Authorization: Bearer <ADMIN_TOKEN>` → daily humans, actions, leads, alerts, top pages, sources, countries, capture rate.

### Pages

`/sitemap.xml`, `/robots.txt`, and every page route (`/`, `/compounds/:key`, `/developers/:key`, `/districts/:key`, …) return `index.html` with that route's head and summary (`src/qayem/seo.py`); unknown compounds, developers and districts return it with status 404 and `noindex`. `www.qayem.ai` redirects to `qayem.ai`. The retired `/units`, `/units/:id` and `/sheet/:id` redirect with 301 to the guide that covers the listing (`seo.retired_redirect`): its compound, else its district, else `/map`.

Unknown `/api/*` paths return JSON 404.

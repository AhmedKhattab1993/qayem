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
- `GET /api/units?q=&district=&compound=&developer=&property_type=&verdict=&grade=&terms=&source=&resale=true|all&sort=grade|value|price_asc|price_desc|area_desc|cash_ppm_asc&page=&page_size=` → `Page<Unit>`. `sort=value` orders by deviation and excludes unpositioned and suspect units.
- `GET /api/units/{id}` → `{unit: Unit & {bathrooms, finishing, installments, down_payment, installment_months, resale_evidence, last_seen_at, unknowns[], description}, breakdown: {levels[], adjustments[]} | null, comparables: (Unit & {cash_ppm})[]}`. Listings in the training set are valued leave-one-out.
- `GET /api/compounds?q=&district=&developer=&sort=units|premium_desc|premium_asc|name&page=&page_size=` → `Page<Compound> & {district: District | null}`.
- `GET /api/compounds/{key}` → `{compound, district, developer}`. `compound.launch` (and `developer.launch`) compares the developer's current launch units with the model's resale value for the same unit on the same plan: `{units, median_spread, median_headline_ppm, median_cash_ppm, median_plan_years, median_down_share, latest_delivery_year, phases[]}` or `null`. A compound has `classes[]` (reference fair ppm for a finished, ready, typical-size unit, grade, premium vs district, median asking and cash-equivalent ppm), a delivery and payment profile, `types`, `area_range` and `scope`.
- `GET /api/developers?q=&sort=&page=&page_size=` → `Page<Developer>`. Premium sorts include developers with ≥20 valued units.
- `GET /api/developers/{key}` → premium vs district (with `premium_basis`), `compounds[]`, `districts[]`, `delivery_changes` (tracked units, postponed, brought forward), profile and scope.
- `GET /api/districts/{key}` → district benchmark per class, profile and scope.
- `GET /api/evaluate?property_type=&area=&price=&compound=&district=&developer=&down_payment=&installment_years=&delivery=ready|YYYY|YYYY-MM&finishing=` → `{inputs, payment, valuation, notes[], breakdown, comparables[], unknowns[]}`. Needs a compound or a district. An unknown compound falls back to district level (`notes: ['compound_not_found']`); a district without a compound uses the non-compound benchmark and may be `insufficient`.
- `GET /api/lookup?url=` → `{id}` for an indexed listing link (host and path compared; links shared by several listings do not match).

Unknown `/api/*` paths return JSON 404. Every other path serves the single-page app.

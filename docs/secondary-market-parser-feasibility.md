# Secondary-Market (Resale) Listing Parsers — Feasibility Study

> **Status update (2026-09-26).** Built: Nawy (resale and developer-sale launches), OpenSooq, Aqarmap, Semsar Masr, GPM, Coldwell Banker, and AqarExit through its full sitemap (~7.3k unit pages, robots-allowed) instead of the ~340-card grid. Re-probed from the production host: Property Finder, Dubizzle and Bayut remain protection-walled. Current source decisions and the crawl schedule: [OPERATIONS.md](OPERATIONS.md).

**Date:** 2026-09-21
**Scope:** 20 Egyptian + international portals listed in the source table. For each: can we build a parser for secondary-market (resale) listings, how, and what stands in the way.
**Method:** Live HTTP probing (curl with a full Chrome UA), inspection of served HTML for embedded structured data (`__NEXT_DATA__`, JSON-LD, schema.org microdata, RSC payloads), discovery of sitemaps/API endpoints, and anti-bot fingerprinting. Light probing only (~5–15 requests per site), no protection bypassing. Key findings were independently spot-checked.

> **Caveats.** Probes ran from a datacenter egress (EU PoPs) on one day. Sites using IP-reputation filtering (Dubizzle, Properstar, 4Sw) may behave differently from Egyptian residential IPs. Rendering claims for fully-blocked sites rest on secondary sources. robots.txt/ToS should be reviewed per site before any production crawler.

---

## 1. Executive summary

| # | Site | Parser? | Resale targeting | Access method | Est. resale inventory | Blocking |
|---|------|---------|------------------|---------------|----------------------|----------|
| 1 | Nawy | ✅ **HIGH** | Explicit (`sale_type=resale`) | SSR `__NEXT_DATA__` JSON | ~12,533 units | None |
| 2 | Aqarmap | ✅ **HIGH** | Implicit (`isResaleInstallment` flag, developer-vs-resale compound tabs) | SSR HTML + JSON-LD + RSC JSON | Large (mixed feed) | CloudFront WAF, path-sensitive |
| 3 | OpenSooq Egypt | ✅ **HIGH** | None — classify from data | SSR `__NEXT_DATA__` (`serpApiResponse`) | High volume, mixed | None |
| 4 | Semsar Masr | ✅ **HIGH** | None — `تمليك`/sale-vs-rent in microdata | SSR HTML + schema.org microdata | Predominantly resale | None |
| 5 | GPM Egypt | ✅ **HIGH** | Dedicated `/en/resale` catalogue | SSR HTML + sitemap (421 resale URLs) | ~430 units | None (passive CF) |
| 6 | Coldwell Banker Egypt | ✅ **HIGH** | Dedicated residential/commercial resale hubs | SSR (RSC) + JSON-LD + 23,844-URL sitemap | Mixed, resale hubs explicit | None (passive CF) |
| 7 | Inland Properties (IPG) | ✅ **HIGH** | None — title regex ("resale") | SSR HTML + JSON-LD + sitemap (2,245 URLs) | ~4% of catalog (~90) | None |
| 8 | Aqar Ya Masr | ⚠️ **MEDIUM** | None (compounds listed separately) | SSR HTML + sitemap; AJAX pagination needs CSRF | Mostly resale classifieds | Passive CF |
| 9 | Aqar Misr (realestate.eg) | ⚠️ **MEDIUM** | None — `/en/resale` removed (410) | SSR HTML + huge sitemaps (15k URLs) | Mixed, resale by keyword only | None |
| 10 | Rightmove Overseas | ⚠️ **MEDIUM** | None | SSR `__NEXT_DATA__` on list pages | 569 Egypt results | None today; known rate-limiter at volume |
| 11 | Bayut Egypt | ⚠️ **MEDIUM** | Unverified (blocked) | Needs headless browser (first-party JS challenge) | Mixed | Humbucker JS challenge (503) |
| 12 | A Place in the Sun | ✅ **HIGH** (small) | Complement of `IsNewBuild` filter | SSR + GET search endpoint + sitemaps | ~38 resale of 189 Egypt | None |
| 13 | Resale Misr (rsmisr.com) | ✅ technically, negligible value | Whole site is resale | Open WordPress REST API | **~10 listings total** | None |
| 14 | Egypt Best Properties | ⚠️ technically trivial, no resale volume | Facet exists (`listing_type:Resale`) | Public Algolia index (credentials in JS bundle) | **3 resale of 1,458** | Passive CF |
| 15 | Dubizzle Egypt | ❌ **LOW** (from here) | Unknown (blocked) | Next.js `__NEXT_DATA__` (unverified) | Largest C2C resale board | Cloudflare WAF 403 everywhere incl. robots.txt |
| 16 | Property Finder Egypt | ❌ **LOW** (from here) | Unverified (blocked) | Internal GraphQL (blocked) | Mixed | CloudFront WAF 403 everywhere |
| 17 | 4Sw — FourSwap | ❌ **LOW** (from here) | Exists per public info (unverified) | Unknown; mobile apps imply a private API | Unknown | Hard WAF "Blocked" 403 on all paths |
| 18 | Properstar | ❌ **LOW** (from here) | "Property condition" facet (unverified) | Blocked | ~1,420 Red Sea listings (per index) | Azure Front Door WAF 429 |
| 19 | Prian Property | ❌ **LOW** | Designed-in resale facet (unverified) | Blocked | ~320 Egypt offers (RU portal) | NGENIX JS challenge / Cloudflare |
| 20 | Zoopla Overseas | ❌ **SKIP** | N/A | N/A | **Section defunct — no Egypt listings** | Cloudflare (moot) |

**Bottom line:** 7 sites are immediately parseable with plain HTTP and structured data (6 Egyptian + 1 international). 2 more Egyptian brokerages are parseable but need light extra work (CSRF/keyword classification). The three biggest Egyptian portals (Dubizzle, Property Finder, Bayut) plus 4Sw are hard-blocked from datacenter IPs — they need headless-browser sessions from Egyptian/residential egress, or should be deferred. Zoopla has no overseas product left to parse.

---

## 2. Recommended build order

**Tier 1 — build now (plain HTTP, structured data, no bot wall):**
1. **Nawy** — best structured resale source in Egypt: first-class `sale_type=resale` filter, ~12.5k units, every unit server-rendered as JSON in `__NEXT_DATA__` (price, area, beds/baths, finishing, compound, developer). No anti-bot, `robots.txt: Allow: /`.
2. **OpenSooq Egypt** — highest classifieds volume reachable: `__NEXT_DATA__.props.pageProps.serpApiResponse` with 30 listings/page, price/currency/rooms/area/masked-phone/member type, `?page=N` pagination (cap 50 pages/query). Needs own new-vs-resale classification (no filter).
3. **Aqarmap** — large SSR feed with per-listing `isResaleInstallment` flag and developer-vs-resale tabs on compound units; JSON-LD `ItemList`+`Offer`; `?page=N`. Respect the path-sensitive CloudFront WAF (stick to known-good URL shapes, low rate).
4. **Semsar Masr** — classic resale classifieds; every card carries full schema.org microdata (`Offer` EGP price, `businessFunction` Sell/LeaseOut, rooms, m², address). Decode windows-1256 before parsing.
5. **GPM Egypt** — dedicated `/en/resale` catalogue (~430 units incl. compounds), sitemap-driven, phones/WhatsApp in HTML.
6. **Coldwell Banker Egypt** — residential + commercial resale hubs, 23,844-URL property sitemap, JSON-LD; parse RSC payloads for price.

**Tier 2 — parseable, smaller/limited resale yield:**
7. **IPG** — open SSR site; resale units identified by title regex (~90 of 2,245). JSON-LD prices, sitemap, no protection.
8. **Aqar Ya Masr** — SSR Laravel, sitemap (~1k URLs); AJAX load-more needs session+CSRF cookie handling.
9. **A Place in the Sun** — trivially scrapeable GET search endpoint; resale = complement of `IsNewBuild` (~38 units). Small but clean.
10. **Rightmove Overseas** — `__NEXT_DATA__` gives 569 Egypt listings incl. coordinates; no resale flag; keep request rate human-like (known escalation at volume). Prices forced to GBP.

**Tier 3 — requires infrastructure investment (headless browser + Egyptian/residential egress), or low expected yield:**
11. **Bayut** — one headless-browser session clears the Humbucker challenge; category pages are SEO-intended. robots forbids `/search/`, `/api/`, `/ajax/` → parse HTML only.
12. **Dubizzle Egypt** — biggest resale classifieds pool, but full Cloudflare WAF; stealth browser at very low rate, or licensed data vendor.
13. **Property Finder Egypt** — uniform WAF block incl. GraphQL endpoint; stealth browser or private mobile-app API (separate effort).
14. **4Sw** — hard IP-class block; capture the mobile apps' API traffic first, retry from Egyptian egress.
15. **Properstar** — Azure WAF 429; robots is permissive so blocking is reputation-based — retry from residential IP with cookies.
16. **Prian** — JS challenges on both domains; revisit with headless session against `prian.ru/en/egypt/` (has a designed resale facet; ~320 Egypt offers).
17. **EBP** — don't scrape HTML; the Algolia index (public credentials in bundle, facet `listing_type:Resale`) is one query away — but only 3 resale units exist, so treat as primary-market source and keep on watch.
18. **Resale Misr** — one call to `/wp-json/wp/v2/properties` returns the whole (~10-listing) catalog; poll occasionally, expect negligible coverage.

**Skip:**
19. **Zoopla Overseas** — overseas listings product was scaled back (~2021–22); no Egyptian inventory exists; domain is also fully challenge-walled. Re-check quarterly only if it relaunches.

---

## 3. Detailed per-site findings

### Egyptian portals & classifieds

#### 1. Dubizzle Egypt — dubizzle.com.eg — ❌ LOW (blocked)
- `/en/properties/for-sale/apartments/` and even `/robots.txt` → **403 Cloudflare** WAF block ("Sorry, you have been blocked", challenge-platform loader). WebFetch also 403.
- Rendering unverified live; multiple secondary sources (scraper marketplaces, a GitHub project built on scraped data) consistently describe Next.js with per-page `__NEXT_DATA__` listing JSON. No official public API.
- Resale filter: unverifiable; as ex-OLX Egypt, inventory is predominantly C2C secondary-market.
- **Path:** stealth headless browser + residential egress at very low rate, or licensed vendor. Deprioritize until others are built.

#### 2. Aqarmap — aqarmap.com.eg — ✅ HIGH
- Working listing URLs: `https://aqarmap.com.eg/{en|ar}/for-sale/property-type/<city>/` → 200, ~124–139 KB, 22 SSR `listing-card`s per page. Legacy `/en/for-sale/apartments/...` pattern 403/500s (WAF is path-sensitive).
- Resale signals: embedded RSC JSON carries `isResaleInstallment` per listing; compound unit tabs embed `resalePropertyTypes` ("للبيع - معلنين") vs developer tab. No site-wide `?resale=` param — general feed is mixed.
- Data: JSON-LD `ItemList` + `Offer`s (price EGP); embedded RSC/Flight state with `price`, `down_payment`, `duration`.
- Pagination: SSR `?page=N` links with `rel="next"`.
- Risks: CloudFront WAF fingerprints unknown paths; robots.txt itself 403s, so disallow rules unreadable. Keep to observed URL shapes, low rate.

#### 3. Property Finder Egypt — propertyfinder.eg — ❌ LOW (blocked)
- Every surface (search, robots.txt, one probe POST to `/graphql`) → uniform **CloudFront 403** "Request blocked". WebFetch 403.
- Known internally to run a search GraphQL API; endpoint unreachable from this egress.
- **Path:** stealth browser with clean IPs, or reverse-engineer the mobile app's private API (separate effort).

#### 4. Bayut Egypt — bayut.eg — ⚠️ MEDIUM
- `/` → **503 + 631 KB first-party JS challenge** ("التحقق الأمني | بيوت", `/.humbucker/clients/browser.js?client=hb-challenge`) behind CloudFront. WebFetch 401.
- `/robots.txt` → 200: disallows `/search/`, `/ajax/`, `/api/`, `/property/get_*` — confirming internal API surfaces exist but are off-limits by policy; category pages are SEO-intended.
- **Path:** headless browser clears the challenge once, keep the session cookie, fetch robots-allowed category HTML at low rate.

#### 5. OpenSooq Egypt — eg.opensooq.com — ✅ HIGH
- `https://eg.opensooq.com/en/<city>/property/apartments-for-sale` → 200 (city comes first in path). No anti-bot (nginx, no challenge).
- Data: `__NEXT_DATA__.props.pageProps.serpApiResponse.listings.items` — 30/page with `id, title, price_amount, price_currency_iso, highlights ("2 Bedrooms » 2 Bathrooms » 130 m2"), city/nhood, posted_at, member_id, member_display_name, has_phone, phone_number (masked "010916661XX"), phone_reveal_key, post_url`. Detail pages add JSON-LD `Apartment`+`Offer` (exact price, rooms, floorSize, PostalAddress).
- Pagination: `?page=N`, capped at 50 pages × 30 = 1,500/query; `meta.count` gives true total (e.g. 1,471 Cairo apartments-for-sale). `/_next/data/` JSON routes are disabled (410).
- No resale filter — inventory mixes compound/new units with ordinary resale; classify from title/highlights.

#### 6. Aqar Ya Masr — aqaryamasr.com — ⚠️ MEDIUM
- SSR Laravel/Blade; `/realestate_filter` renders a results grid (73 cards observed); `sitemap.realestate.xml` lists ~1,029 listing URLs. Cloudflare CDN present but passive (curl passes).
- Filters: `main_type, contract_type (بيع/إيجار), city_id, district_id, building_age` — no resale flag; `/compounds/*` tree is the new-development side, so the main feed is predominantly secondary-market.
- Pagination is "load-more" AJAX POST to `/realestate_filter` requiring `laravel_session` + `XSRF-TOKEN` cookies and CSRF token.
- **Path:** enumerate via sitemap, parse SSR card/detail HTML + `Product` JSON-LD (price range, geo, agent phone in JSON-LD description); replicate POST pagination only if sitemap depth is insufficient.

#### 7. Semsar Masr — semsarmasr.com — ✅ HIGH
- `https://www.semsarmasr.com/3akarat.asp?p=1&cid=765&r=70&g=984` → 200. Taxonomy: `cid` (765 apartments, 766 land, 767 villas/palaces, 769 buildings, 770 chalets, 771 commercial), `r` governorate, `g` city, `p` page (Cairo apartments paginate to ~381 pages). Cleaner SEO routes `/3akarat/<gov>/<category>` also live; English mirror at `/en/property.asp`.
- Data: **schema.org microdata on every SSR card** (verified): `itemtype="…/Apartment"` (also House/Building/Place/LocalBusiness), `Offer` with `price`, `priceCurrency EGP`, `priceValidUntil`, and `businessFunction` `#Sell` (sale/تمليك) vs `#LeaseOut` (rent) — a built-in sale-vs-rent discriminator; `numberOfRooms`, `floorSize MTK`, `PostalAddress` (region/locality), title/description.
- Encoding: **windows-1256** — decode before parsing (raw bytes break naive grep/parsers). Detail pages additionally carry JSON-LD (`Apartment`/`Product`) and microdata; phone numbers plainly in HTML.
- No resale flag per se; "تمليك" (freehold resale) in description + `#Sell` covers it. No anti-bot (Cloudflare passive). Data quality is classifieds-grade (negotiable prices, description-duplicated numbers).

#### 8. 4Sw — FourSwap — 4sw.app — ❌ LOW (blocked)
- Every request (apex, www, full Chrome header set) → **403 with a literal 7-byte "Blocked"** — a hard WAF IP-class/geo rule, not a JS challenge. Nothing verifiable.
- Concept (swap + resale apartments "شقق ريسيل") is the most resale-aligned of the classifieds group; Android/iOS apps exist, implying an undocumented mobile JSON API.
- **Path:** capture app API traffic and re-probe from Egyptian residential egress before writing any parser.

### Brokerage & resale-focused platforms

#### 9. Nawy — nawy.com — ✅ HIGH (best structured resale source)
- Resale search: `https://www.nawy.com/search?sale_type=resale&page_number=1&category=property` → 200 (verified: `loadedSearchResultsSSR`, tag `"Resale"`, **`total: 12533`**). `/resale` as a path 404s — resale is a query filter.
- Data: `__NEXT_DATA__` (pages router) — 12 fully-structured units per page: id, slug, propertyType, compound, area, developer, finishing, unitArea, numberOfBedrooms/Bathrooms, `paymentPlan.minPrice` + `currency EGP`. JSON-LD `Residence` on pages; `sitemap.xml` (declared in robots) for detail discovery (`/compound/{slug}/property/{slug}`); implied `/_next/data/{buildId}/...` route (buildId `m1kJJpyh9eKgZ23I-5k13`).
- No anti-bot; `robots.txt: Allow: /`.
- Caveats: price only as `paymentPlan.minPrice`; no seller phone in HTML (lead-gen model).

#### 10. Coldwell Banker Egypt — coldwellbanker-eg.com — ✅ HIGH
- Domain is **coldwellbanker-eg.com** (coldwellbanker.com.eg does not resolve). Resale hubs: `/en/residential-resale-properties-egypt`, `/en/commercial-resale-units` (200, SSR cards).
- Data: Next.js App Router RSC (no `__NEXT_DATA__`; state in `self.__next_f.push()` payloads, incl. `"price":2797000`); JSON-LD `Residence`/`BreadcrumbList` on details; sitemap index → `ecms.coldwellbanker-eg.com/properties.xml` (**23,844 URLs**) + `projects.xml`, `locations.xml`.
- Cloudflare present but passive. Pagination `?page=N` + loadMore.
- Risks: RSC payload parsing is brittle across Next.js upgrades; resale-vs-primary classification comes from hub membership, not a per-listing field.

#### 11. Aqar Misr — realestate.eg — ⚠️ MEDIUM
- Domain is **realestate.eg**. Huge open sitemaps: `sitemap.listing_en_1.xml` = 14,999 URLs (plus `_2`, `_ar`, `for_sale.xml` 3,360 category URLs). SSR Laravel + jQuery; cards fully in first HTML; `?page=N` plus an AJAX stream endpoint (`/en/for-sale/unit-pages/stream`).
- Resale: **`/en/resale` → 410 Gone**; no resale/purpose filter in the form (only price/area/beds/type/sort). Resale units must be classified by description/badge keywords. Their PF profile advertises 421 resale listings, so stock exists but isn't structurally segmented.
- No anti-bot. Risks: noisy resale classification; AJAX endpoints may shift with deploys; the removed resale hub suggests strategy in flux.

#### 12. GPM Egypt — gpmegypt.com — ✅ HIGH
- Dedicated catalogue: `https://gpmegypt.com/en/resale` → 200; details at `/en/resale-real-estate/{slug}-{code}`; **421 resale URLs in sitemap.xml** (3,242 total), 12 cards/page, `?page=2..36` (~430 units) covering New Cairo, New Capital, North Coast, Ain Sokhna compounds.
- SSR Laravel; prices EGP, area, and phone/WhatsApp (`wa.me/201070399500`) in HTML. No JSON-LD → CSS selectors required. No anti-bot (passive CF); notably permissive AI/robots signals (`x-ai-content: allowed`, `Content-signal: ai-input=yes`, `Allow: /`).

#### 13. Resale Misr — rsmisr.com — ✅ technically / negligible value
- Domain is **rsmisr.com** (resalemisr.com is a parked stub — do not use). Open WordPress + Astra/Elementor + ACF; **WP REST confirmed**: `GET /wp-json/wp/v2/properties` returns full records; `wp-sitemap-posts-properties-1.xml` exists. No anti-bot.
- **Whole catalog ≈ 10 listings.** Entire site is resale-niche, but coverage is negligible — poll occasionally at near-zero cost.

#### 14. Egypt Best Properties — egyptbestproperties.com — ⚠️ trivial access, no resale volume
- Search is client-side **Algolia InstantSearch**; public credentials embedded in the JS bundle (App ID `RFO023Q3CL`, search key `c042c0a6149bd598d28301cbd949cd74`, indexes `properties`/`properties_ar`). Live query verified: 1,458 hits with id, title, price, area_m2, bedrooms/bathrooms, property_type/kind, `listing_type`, compound/project, images.
- Resale facet exists (`listing_type`) and homepage has a Primary/Resale toggle — but live counts: **Primary 1,455 vs Resale 3**. It's a primary/off-plan site with a cosmetic resale option.
- robots disallows `/api/`, `*/search`, `/*?*` — stick to the Algolia API, not HTML crawling.

#### 15. Inland Properties Group — ipgegypt.com — ✅ HIGH
- Domain is **ipgegypt.com**. SSR Laravel; `/en/properties?page=N`; JSON-LD `Product`+`Offer` (EGP price) + `BreadcrumbList` on details; `sitemap-properties.xml` with 2,245 EN property URLs; phones in HTML. No anti-bot.
- Resale: no filter; **~92 of 2,245 sitemap URLs contain "resale"** in the title (e.g. "Resale Chalet 76m in…") — title-regex classification. Sitemap appears to include stale URLs (sitemap 2,245 vs ~9/page live index) → dedupe/404 handling needed.

### International portals carrying Egyptian properties

#### 16. Properstar — properstar.com — ❌ LOW (from this egress)
- All HTML/sitemap paths → **429 Azure Front Door WAF** ("The request is blocked."); WebFetch 403. robots.txt is permissive (`Crawl-delay: 10`) and reachable — blocking is IP-reputation-based, so residential egress with cookies may pass.
- Search index shows real Egypt inventory (≈410 apartments/houses nationwide; ~1,420 in Red Sea Governorate) at `properstar.com/egypt/{region}/listings/for-sale`; a "property condition" (new/resale) facet exists platform-wide but was unverifiable. Largest international resale potential — revisit with residential IPs.

#### 17. A Place in the Sun — aplacetinthesun.com — ✅ HIGH (small volume)
- Egypt: `/property/egypt` → 200; a **GET-renderable search endpoint** `/umbraco/api/propertysearchform/Index?Location=Egypt…` returns the full results page honoring `Location`, `IsNewBuild`, `MinPrice`, `MaxPrice`. Filters include `IsNewBuild` but no "resale" — verified `IsNewBuild=true` → 151 of 189, so resale ≈ **38 existing homes** (Hurghada, Sahl Hasheesh, El Gouna, Sharm).
- SSR (ASP.NET WebForms/Umbraco), pager params in `data-total-num-pages="24"`; sitemap index `/xmlsitemap/index.xml` (39 sub-sitemaps, daily). No JSON-LD; prices converted to GBP/USD (original EGP only in agent description text).

#### 18. Rightmove Overseas — rightmove.co.uk — ⚠️ MEDIUM
- `https://www.rightmove.co.uk/overseas-property-for-sale/Egypt.html` → 200; list pages are Next.js with `__NEXT_DATA__` containing the complete `searchResults` model — verified **resultCount 569** for Egypt (`locationIdentifier=WORLD_REGION^54`), 25 properties/page with id, price (`amount`, `currencyCode: GBP`), displayAddress, bedrooms, subType, coordinates, images, keyFeatures. Pagination `find.html?…&index=24` confirmed.
- No resale facet (keyword search only). No challenge observed today via curl — but Rightmove is a known aggressive rate-limiter at volume; pace requests humanly.
- Detail pages are legacy stack (escaped-JSON, no `__NEXT_DATA__`, no JSON-LD). Prices forced to GBP (EGP lost at source).

#### 19. Zoopla Overseas — zoopla.co.uk — ❌ SKIP
- `/overseas-property/egypt/` and homepage → **Cloudflare challenge**; search index shows **no Egyptian overseas listing pages at all** (only a UK street named "Egypt Lane"). Consistent with Zoopla's overseas scale-back (~2021–22). Double disqualifier: no product + full challenge wall. Watch-list quarterly at most.

#### 20. Prian Property — prian.ru / prianproperty.com — ❌ LOW
- `prian.ru/en/egypt/` → **503 NGENIX JS challenge** (all paths incl. robots.txt, `ngenix_jscc` cookie); `prianproperty.com/egypt/` → **403 Cloudflare**. Nothing verifiable live.
- Prian's product has a designed new/resale («вторичка») facet; catalog indexes show ~320 Egypt offers on the RU portal, ~20 on the English mirror. Modest yield; revisit only with a JS-capable session against prian.ru.

---

## 4. Cross-cutting notes for parser design

- **Common schema.** Normalize into one listing record: `source, source_listing_id, url, title, description_raw, purpose (sale/rent), is_resale (bool + evidence), property_type, price (value, currency, is_installment, down_payment, installment_months), area_m2, bedrooms, bathrooms, finishing, delivery_status, compound/project, developer, city, district, lat/lng, seller_type (owner/broker/developer), phone, posted_at, images, scraped_at`.
- **Resale classification fallback.** Sites without a resale flag (OpenSooq, Semsar, Aqar Ya Masr, Aqar Misr, IPG, Rightmove) need a rule-based + model-assisted classifier over title/description: signals like «تمليك», "resale", «استلام فوري» (immediate handover), «من المالك» (owner), compound-vs-developer context, `businessFunction #Sell`, `isResaleInstallment`, `listing_type` facets where present.
- **Anti-bot tiers observed:** none (Nawy, OpenSooq, Semsar, brokerages) → passive CDN (CloudFront/Cloudflare present but transparent) → path-sensitive WAF (Aqarmap) → first-party JS challenge (Bayut) → hard blocks (Dubizzle, Property Finder, 4Sw, Properstar, Prian, Zoopla). Infrastructure needed scales with tier; the first two tiers need nothing beyond a browser-like UA and polite pacing.
- **Encoding & data quality.** Semsar is windows-1256; several sources duplicate prices inside free-text descriptions with "قابل للتفاوض" (negotiable) qualifiers; installment prices carry down-payment + months rather than a single figure (Aqarmap `down_payment`/`duration`, Semsar "مقدم X" cards). Normalize carefully.
- **Compliance.** Verify robots.txt/ToS per source before production (Bayut explicitly forbids its `/api/`/`/ajax/` surfaces; EBP forbids site crawling but offers a public search index). Phone numbers are PII — mask/store per policy (OpenSooq already masks them in list data).
- **Volatility.** Embedded-state formats (`__NEXT_DATA__`, RSC `self.__next_f`) and the realestate.eg resale-hub removal show parsers need schema-drift monitoring (canary fields + alerting per source).

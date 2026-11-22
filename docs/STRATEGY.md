# Qayem strategy: Egypt's property price guide

Adopted 2026-11-22. Nothing here is built yet unless marked **exists**.
Earlier context: [VISION.md](VISION.md) (the comparison standard), [GROWTH.md](GROWTH.md) (heads,
leads, alerts, funnel).

## 1. The direction in one paragraph

Qayem becomes **the place a regular buyer, in Egypt or abroad, goes to understand what property
costs anywhere in Egypt**: by district, by compound, by developer, resale against buying new, in
cash-today terms. Not a data-science dashboard and not a listing portal: plain answers, a map, and
articles that explain the numbers. It is found through Google **and** through AI assistants
(ChatGPT, Gemini, Perplexity, Claude), so every page is written to be quoted. Its data comes from
many public sources used only as input to Qayem's own aggregates, plus data Qayem collects itself,
so no single site can switch it off.

**Constraints this strategy accepts:** no data partnerships; legal safety over coverage; one person
operating it, so everything repeatable is automated and the rest is a short weekly review.

**Owner decisions, 2026-11-22:**
- **Computer use runs only in the Linux VM**, never on the Mac (section 5.4).
- **Articles publish without approval**, behind automatic gates (section 8.2).
- **Everything is free for now:** free tools and free tiers only, and nothing is charged to users
  (sections 10 and 14).

## 2. What changes

| Today | Direction |
|---|---|
| Rates individual AqarExit listings (production: 10,435 units, 100% AqarExit) | Publishes market prices per district, compound and developer, from many sources |
| Unit pages are the main surface | The map, district and compound guides, and articles are the main surfaces; unit-level detail fades out |
| Source photos shown on unit pages | No third-party photos or descriptions; Qayem's own charts and maps |
| Compounds only | All of Egypt: compounds **and** the non-compound city market (Nasr City, Maadi, Alexandria…) |
| Content: a weekly brief posted by hand (**exists**: `qayem content-brief`) | An agent drafts articles when the data changes; a human approves |
| SEO heads and sitemap (**exists**: `src/qayem/seo.py`) | SEO plus GEO: pages built to be cited by AI answer engines |
| Arabic first | Arabic first, full English, prices also in USD / SAR / AED for buyers abroad |

## 3. Who it is for and what they ask

The pages and the articles are built from these questions, in the buyer's own words.

| Buyer | Typical questions |
|---|---|
| First-time buyer in Cairo / Giza | "How much is a 3-bedroom in New Cairo?" «سعر المتر في التجمع كام؟» "Is Sheikh Zayed cheaper than October?" |
| Egyptian abroad (Gulf, Europe) | "What does 5 million get me, and where?" "Resale or new from the developer?" "How much in dollars?" |
| Resale buyer | "Is this price fair for this compound?" «الأوفر الطبيعي كام؟» "What does the developer sell the same unit for today?" |
| Seller | "What can I ask?" "How long do units in my compound take to sell?" |
| Investor | "Which areas went up most this year?" "Where are prices below the developer's?" |

The test of every page: does it answer one of these in the first two sentences, with a number and
a date?

## 4. Product surfaces

1. **The map** (section 7): Egypt by market district and compound, coloured by price, as the home page's
   main entry.
2. **District guides** (`/districts/:key`, **exists**, to be expanded): price per m² by type and
   size, resale against new, trend, how fast units sell, the compounds inside, FAQ.
3. **Compound guides** (`/compounds/:key`, **exists**, to be rebuilt as a guide): the monthly
   price guide, the over people pay, the developer's price today, history, comparable compounds.
4. **Developer pages** (**exists**): price moves, delivery record, resale against their own prices.
5. **Price check** (`/evaluate`, **exists**): a unit the user describes or pastes, checked against
   the guide.
6. **Articles** (section 8): data stories and explainers, each tied to a guide page.
7. **The Qayem Index** (monthly): one named, dated set of figures per district and compound. It
   gives the press, AI assistants and the articles one stable thing to cite.

## 5. Data: sources, how each is read, what it is used for

### 5.1 Principles

- **Aggregates, not copies.** Public listings are an input to Qayem's medians and ranges. Qayem does
  not republish another site's listings, photos or descriptions.
- **Facts only.** Store price, area, type, plan, location, dates, the source and its link. No
  names, phone numbers, photos or free text kept beyond extraction.
- **Polite collection.** Respect robots.txt, rate limits, no logins, stop on a block (**exists**:
  the shared fetcher). Computer use (section 5.4) is for sites that allow access but have no clean
  feed, **never** to get past bot protection or a login wall.
- **No single source dominates a published figure.** Each figure shows its source mix; a figure
  resting on one source is labelled.
- **Qayem's own data grows until the scraped part is optional.**

### 5.2 Source inventory

Active rows from the development database on 2026-11-21. No source currently provides coordinates.

**A. Public listings, automated crawl (parsers exist)**

| Source | Active rows | What it adds | Use |
|---|---|---|---|
| AqarExit | 10,592 | Contract transfers with paid, owed and installments per unit | Resale contract prices, plan structure |
| Nawy resale | 12,739 | Owners' asking prices with plans | Resale asking prices. Not on production yet: fix first |
| Nawy developer launches | 6,757 | The developer's current price and plan per unit | Resale-against-new benchmark |
| Aqarmap | 21,877 | The widest coverage, 1,365 district spellings, non-compound market | City-market asking prices |
| OpenSooq | 3,339 | Classifieds, owners and brokers | City-market asking prices |
| Semsar | 2,180 | Classifieds, all governorates | Governorate coverage |
| GPM, Coldwell Banker | 421, 400 | Brokerage resale catalogues | Cross-check only |

**B. Public official and corporate data, automated**

| Source | What it adds | Method | Frequency |
|---|---|---|---|
| Central Bank of Egypt | Policy rate, inflation, exchange rates | Scheduled fetch | Monthly; on rate decisions |
| CAPMAS | Inflation, building-material and construction statistics | Scheduled fetch or entry | Monthly |
| Stock-exchange-listed developers (TMG, Palm Hills, SODIC, Emaar Misr, Madinet Masr…) | Contracted sales, price trends, delivery schedules | Download investor PDFs, AI extraction, check | Quarterly |
| New Urban Communities Authority, Ministry of Housing | Land allotment and government housing prices: an official floor per new city | Check announcements | Monthly |
| Registry and transfer fee schedules | Total cost of buying | Manual entry | Yearly |
| OpenStreetMap | Boundaries, compound outlines, names (section 7) | Geofabrik extract | Monthly |

**C. Qayem's own data, automated intake**

| Source | What it adds | Method |
|---|---|---|
| Price checks run (`/evaluate`) | An asking-price observation per unit checked | Store each run, remove duplicates and outliers |
| User reports | The over quoted, the developer's offer, the price paid | One question after a check; sellers get a free pricing report |
| Broker WhatsApp inventory sheets | Resale asking prices **with the over** | A dedicated number on the official WhatsApp Business API → webhook → AI extraction → review |
| Developer sales agents' offers | Developer prices for "call for price" developers | Ask once through their enquiry form; their messages arrive on the same number |
| Paid deal-check clients | Final prices, the best data there is | Recorded with the client's permission, without names |

**D. Computer use or a human in the loop**

| Source | Why it is not a crawl | Method |
|---|---|---|
| Developers' price lists and brochures behind script-heavy pages | No feed; a person-like browse is allowed | Computer use in the VM (5.4) monthly for the top developers; extraction to the review queue |
| The official Egyptian real estate platform (`realestate.gov.eg`) | Government listings and auctions; terms to be checked first | Computer use in the VM, if the terms allow it |
| Investor presentations behind download forms | One form per report | Computer use in the VM quarterly |
| Facebook compound groups | Login wall; their terms forbid scraping | Read by a person; used for questions to answer and topics, not data |

**E. Excluded**

Property Finder, Dubizzle and Bayut block automated access (403s and challenges on every path,
including robots.txt). They stay out: Qayem does not bypass protection, with a browser or otherwise.

### 5.3 From raw rows to published figures

```
collect → normalize → resolve names → dedupe → classify → segment → aggregate → label → publish
```

1. **Normalize** (**exists**): one schema across sources; payment plans converted to cash today.
2. **Resolve names** (**exists**: `qayem resolve-entities`): every spelling of a compound or
   developer mapped to one canonical name. Extend to districts, because Aqarmap alone has 1,365
   district spellings.
3. **Dedupe across sources:** the same unit listed on several sites counts once. Match on compound,
   type, area within 2%, and price within 3%, in a 30-day window; keep the link to every copy.
4. **Classify** each row:
   - market: resale / transfer / developer sale
   - seller: owner / broker / developer
   - terms: cash / plan / partial
   - quality: complete, suspect price, down payment shown as the price (**exists** for AqarExit), stale
5. **Segment:** market district × compound (or "outside compounds") × type × size band × finishing ×
   delivery (ready / under 2 years / later).
6. **Aggregate:** median and interquartile range of price per m², asking and cash today, the
   resale-against-new gap, days on market and price cuts (**exists** in part). Publish a segment
   only with at least 5 listings from at least 2 sources, or 10 from one source with a
   "single source" label.
7. **Label** every figure with its period, number of listings, source mix and a confidence level
   (high / medium / indicative).
8. **Publish** as the monthly Qayem Index, and continuously on the guide pages.

### 5.4 Computer use: the VM only

Owner rule, 2026-11-22: Qayem's computer use runs **only** in the isolated Linux VM that
content-engine set up, **never on the Mac's own desktop**.

**The VM**
- OrbStack Ubuntu 24.04 GUI VM named `computer-use` (`DISPLAY=:1`).
- Live viewer: `http://computer-use.orb.local:6080`.
- Driven from the host through `cua-driver` with `~/.local/bin/vm-cu`. Driver calls go through
  `vm-cu cua-call <tool> '<json>'`.
- See content-engine's `docs/POSTING_PLATFORMS.md`, "Isolated Linux Computer-Use VM".

**The browser**
- Qayem's own Brave profile in the VM: `vm-cu brave qayem [url]`, with its data in
  `~/.config/brave-qayem` and the systemd unit `computer-use-brave@qayem.service`. Check it with
  `vm-cu brave-status`.
- Brave is driven only through `cua-driver` (the accessibility tree, the pointer and the
  keyboard). No remote debugging port (CDP), and no other profile or browser as a substitute.

**Lock first: every computer-use step holds content-engine's shared desktop lock**
- Run it from content-engine's checkout:
  `python -m studio.desktop_lock run --brand qayem --owner <who> --task <task> --wait <s> -- <cmd>`
  (or `acquire` / `release`).
- Exit code 75 means the lock was not taken: do no computer use, and do not carry on after a lock
  wait times out. Never hand-roll the lock.

**If anything is unavailable** (the VM, the driver, the Qayem profile or its sign-in), report the
blocker. Never fall back to the Mac's desktop, the Mac's Brave, or another device.

**What it is for:**
- the source group D tasks in section 5.2
- dashboard settings with no API (Cloudflare's AI crawler setting, Search Console, Bing Webmaster)

The rules in 5.1 apply here too: no logins to sources, no getting past blocks.

### 5.5 Personal data

**Personal data clean-up first:** the development database holds 4,163 sellers' phone numbers
(every OpenSooq and GPM row) and raw source pages that can contain names. Stop storing phone
numbers, delete the stored ones, and keep only the fields above from raw pages.

## 6. Pricing language for regular buyers

- Lead with one sentence: «سعر المتر للشقق الجاهزة في التجمع الخامس حوالي X ألف جنيه (نوفمبر 2026)»
  ("Ready apartments in the Fifth Settlement cost about X thousand pounds per m², November 2026").
- Say "asking price" when it is one; Egypt publishes no sale prices, and Qayem says so on every page.
- Show a range, not a single "fair price": "most 3-bedrooms here list between X and Y".
- Resale against new is the headline comparison: "Buying resale here costs about 12% less than buying the same unit from the developer today."
- Cash today is shown beside the headline price and explained in one tooltip, not up front.
- Currency switch: EGP, USD, SAR, AED at the Central Bank of Egypt rate of the day.

## 7. The map

### 7.1 What it shows

A light, flat map: land, roads, water and Arabic and English place names, with Qayem's layers on
top. No satellite imagery.

| Layer | Shows | Zoom |
|---|---|---|
| Market districts | Fill by median price per m² (or resale against new, as a toggle), with the name and the figure | Country to city |
| Compounds | A dot per compound, sized by listings, coloured like the districts; outlines where OpenStreetMap has them | City to neighbourhood |
| Price grid (the "heat map") | Hexagons (H3, ~1–2 km) coloured by median price per m², **only where a hexagon has at least 5 listings** | City |
| Filters | Type, bedrooms, budget, ready or not, currency | All |

Tapping a district or compound opens a summary card (median, range, trend, number of listings)
with a link to its guide page. On phones the map opens as a full screen with a list toggle.

A continuous heat map over sparse data invents prices where there are none, so the price grid
shows only hexagons with enough data, and everything else stays blank.

### 7.2 Where the geography comes from

| Need | Source | Licence notes |
|---|---|---|
| Base map (roads, water, names) | Protomaps basemap from OpenStreetMap, as one PMTiles file | ODbL: "© OpenStreetMap contributors" on the map |
| Governorates and official districts | UN OCHA's administrative boundaries for Egypt (HDX) | Check the dataset's licence (usually CC BY-IGO). Avoid GADM: it does not allow commercial use |
| **Market districts** (what buyers mean: Fifth Settlement, Sheikh Zayed, New Capital, North Coast) | Built by Qayem: new-city boundaries from OpenStreetMap, the rest drawn by hand for the ~45 districts in use | Qayem's own layer. Where it is derived from OSM, ODbL share-alike applies if the layer is published as data |
| Compound locations | OpenStreetMap features with the compound's name, matched through `resolve-entities`; the rest placed by hand from public maps, with AI matching and a review queue | Store a point for every compound and an outline where OSM has one |

The official administrative boundaries rarely match how the market names areas, so the market-district
layer is Qayem's own and is versioned in the repository.

### 7.3 How it is built

- **MapLibre GL JS** with a minimal custom style, so labels are Arabic first and colours match the site.
- **PMTiles** for the base map and Qayem's layers, served from Cloudflare (R2 or static assets):
  no tile server and no per-view cost.
- District and compound figures come from the same snapshot the API serves, as GeoJSON (small,
  ~45 districts and ~500 compounds) or vector tiles if they grow.
- **Search engines and AI assistants cannot read a map.** Every region on it is also a crawlable
  guide page, and the map page carries a text table of the same figures.

## 8. The article agent

### 8.1 Triggers

| Trigger | Example article |
|---|---|
| The monthly index is published | «أسعار العقارات في مصر – نوفمبر 2026: أكبر 10 تحركات» ("Egypt property prices, November 2026: the 10 biggest moves") |
| A segment moves more than a threshold (e.g. ±5% month on month, with enough data) | "Resale prices in Badya fell 6% in a month" |
| A developer changes its list prices | "SODIC raised its prices X% in Sheikh Zayed" |
| A Central Bank rate decision | "What the rate cut means for installment buyers" |
| A quarterly report from a listed developer | "TMG's sales in Q3 2026, in numbers" |
| Search Console: a query with impressions and no good page | A guide or explainer built for that exact question |
| Calendar | Each compound's monthly report, rotated by search demand |

### 8.2 Pipeline

```
trigger → data pack → draft → fact check → quality gates → approval → publish → distribute
```

1. **Data pack:** the trigger builds a JSON of every figure the article may use, from the snapshot,
   with period and listing counts.
2. **Draft:** the model writes in Arabic, then English, from the data pack and a template for that
   article type. Rule: no number that is not in the pack.
3. **Fact check (automatic):** every number and date in the draft is matched against the pack; any
   mismatch rejects the draft.
4. **Quality gates:**
   - enough data behind each claim
   - no investment advice ("buy now")
   - neutral wording about named developers
   - no copy from any source
   - the article adds at least one figure not already on its guide page
5. **No approval step** (owner decision, 2026-11-22): a draft that passes the fact check and every
   gate publishes directly. A draft that fails any of them is not published, and is logged with
   the reason. After publishing, a Telegram message sends the link and a one-tap unpublish, for
   information only.
6. **Publish:** an article page with its JSON-LD; update the sitemap; ping IndexNow (Bing, and
   through it ChatGPT search and Copilot).
7. **Distribute:** a share card (**exists**: `content.py` renders 1080×1350 cards) and tracked links
   for social posts.

### 8.3 Guarding against "AI spam"

Google's spam policies target scaled content without value, whoever writes it. So:

- every article carries data no one else has
- the volume is capped (start at 2–4 a week)
- no near-duplicate pages per compound
- thin pages stay `noindex` until they have data
- the byline says "Qayem data desk", and the methodology page states that articles are written with AI from Qayem's data and checked automatically
- with no human approval, the automatic gates are the only safeguard, so they stay strict: when in doubt the draft is not published

## 9. Search and AI answer engines (SEO and GEO)

GEO, generative engine optimization (also called AEO, answer engine optimization), means being the
source an AI assistant quotes. Most of it is good SEO, plus a few specifics.

**Crawlability**
- **Exists:** server-written heads and crawlable summaries.
- Make the full answer, not only a summary, readable without JavaScript.
- Check Cloudflare's AI crawler setting, which can block AI bots by default, and allow the crawlers
  wanted in robots.txt: OAI-SearchBot and GPTBot, ClaudeBot, PerplexityBot, Google-Extended.
- Publish `/llms.txt`: a short map of the site and the methodology, cheap to do.

**Answer-first writing**
- Each page opens with the answer: one sentence with the number, the place and the month.
- Then a small table, then the explanation.
- Questions as headings, in the words buyers use, in Arabic and English.

**Structured data**
- **Exists:** `FAQPage` and breadcrumbs.
- Add `Dataset` for the index, `Article` with dates, `Place` for districts and compounds, and
  `Organization` with the methodology.

**Citability**
- A named, dated index ("Qayem Index, November 2026") with stable URLs.
- A public methodology page.
- A downloadable monthly CSV of district and compound figures under CC BY, with attribution.
  Aggregates only.

**Freshness:** "updated" dates on every page; monthly figures replace last month's on the same URL;
the archive stays on its own dated URL.

**Measurement**
- Referrals from `chatgpt.com`, `perplexity.ai`, `gemini.google.com`, `copilot.microsoft.com` in
  the funnel report.
- Search Console and Bing Webmaster (**exists**: both verified).
- A monthly test of 20 buyer questions in each assistant: is Qayem cited?

## 10. Free now, and how it can earn later

**Owner decision, 2026-11-22: everything is free for now.**
- **Nothing is charged to users:** the guides, the map, the articles, the price check, the deal
  check and the monthly CSV are all free.
- **Only free tools and free tiers:**
  - OpenStreetMap, Protomaps, MapLibre and H3
  - Cloudflare's free allowances (Workers, D1, R2)
  - the current Pi / GLM model setup
  - Telegram, Search Console, Bing Webmaster and IndexNow
  - WhatsApp Business API: receiving messages only
  - Resend's free tier
- **Nothing that adds a cost is introduced.** If a step would need a paid plan, it waits, or a free
  alternative is used.

The free deal check (verdict, the developer's current offer, the transfer checklist and a call,
aimed first at buyers abroad) is the main way leads and first-party prices are captured.

Later options, once traffic justifies them, in order:
1. **A paid deal check.**
2. **A buyer-side fee** for handling a purchase, paid only by the buyer and stated on every page.
   Check whether this needs a broker registration.
3. **Paid reports** for brokers and investors.

Never: selling leads to developers or brokers, or ads from developers. They conflict with being
the neutral guide.

## 11. Legal guardrails

To review with an Egyptian lawyer before anything is charged.

- **Anti-Cyber and IT Crimes Law 175/2018 (access without permission):** never bypass a block or log in to collect.
- **IP Law 82/2002 (databases and photos are protected, facts are not):** publish aggregates, never a site's listings, photos or descriptions.
- **Terms of use:** no accounts on sources; a takedown address; stop collecting from a site that asks.
- **Personal Data Protection Law 151/2020:**
  - no personal data from sources
  - consent and the privacy page for leads (**exists**)
  - delete the 4,163 stored phone numbers
- **Statements about developers:** figures with dates and sources, neutral wording, a corrections process.
- **Terms of use for Qayem:** comparisons and asking prices, not valuations or investment advice.

## 12. Roadmap

**Phase 0: clean-up and foundations (weeks 1–2)**. Status 2026-11-22:
- Done and live on production:
  - No phone numbers or contact fields are stored. `qayem scrub-personal` ran on every local copy and
    on the cloud database, and runs every night.
  - No source photos are served.
  - `/llms.txt` is published.
  - AI crawlers are allowed (checked 2026-11-22): AI Crawl Control blocks no crawler; the Search, Training
    and Agents policies are all "Allow"; Bot Fight Mode and AI Labyrinth are off.
  - Nawy resale is on the site: 23,651 resale units, 17,612 rated (unrated down from 43% to 26%).
  - A failing source no longer freezes publication.
- Open:
  - 66 older database checkpoints in R2 (`canonical/<run>/`) still hold the phone numbers.
  - A takedown e-mail address needs a working inbox (Cloudflare Email Routing).

- Delete the stored phone numbers and stop storing them; strip personal fields from raw pages.
- Remove third-party photos from the site.
- Get Nawy resale onto production.
- Allow AI crawlers; add `llms.txt`.
- Write Qayem's terms of use and a takedown address.

**Phase 1: data layer (weeks 3–6)**
- District name resolution across all sources.
- Cross-source dedupe and the classification fields.
- The segment table and aggregates with minimum counts and labels.
- The first monthly Qayem Index (internal).
- Scheduled jobs for Central Bank rates and developer reports.

**Phase 2: map and guides (weeks 5–10)**
- The market-district layer (~45 districts) and compound locations.
- Map v1: districts and compounds, with the price grid where data allows.
- District and compound guides rebuilt answer-first, with `Dataset` and `Place` data.
- The currency switch.

**Phase 3: articles (weeks 8–12)**
- The data pack, templates, fact checker, automatic gates and direct publishing, with an
  after-publish Telegram note.
- Triggers: monthly index, segment moves, developer price changes.
- 2–4 articles a week, Arabic and English.

**Phase 4: own data and revenue (weeks 10–16)**
- The WhatsApp intake for broker sheets and developer offers, with a review page.
- "What over were you quoted?" in the price check.
- The free deal-check page.
- The public monthly CSV.
- The computer-use jobs in the VM (section 5.4): developer brochures and investor reports.

## 13. Targets

| By | Measure | Target |
|---|---|---|
| Week 6 | Segments published with "high" confidence | ≥150 |
| Week 10 | Districts and compounds on the map with figures | 45 districts, ≥300 compounds |
| Week 12 | Human visits a day (from ~2–5 on 2026-11-21) | ≥50 |
| Week 12 | Pages cited in the monthly AI-assistant test | ≥3 of 20 questions |
| Week 16 | Share of published figures not relying on any single source | ≥70% |
| Week 16 | First-party price observations (checks, reports, broker sheets) | ≥1,000 |
| Week 16 | Free deal-check requests | ≥20 a month |

## 14. Decisions

Settled 2026-11-22. The owner asked for no approval steps, and for everything to be free for now.

| Question | Decision |
|---|---|
| "Global" | All of Egypt, for buyers inside and outside Egypt (Arabic, English, prices in EGP / USD / SAR / AED) |
| Unit pages | Fade them out; no third-party photos meanwhile |
| AI crawlers | Allow all major ones (search and assistant crawlers) |
| Article model | The current Pi / GLM setup: no added cost |
| Approval | None. Articles that pass the automatic gates publish directly |
| Public CSV | Published free under CC BY (aggregates only) |
| Charging | Nothing for now (section 10) |
| Computer use | The Linux VM only, behind the shared desktop lock (section 5.4) |

## 15. Risks

| Risk | Mitigation |
|---|---|
| A large source blocks Qayem | Many sources; own data grows; published figures never rest on one source |
| AI-written articles judged low quality by Google | Unique data in every article, capped volume, strict automatic gates, `noindex` thin pages |
| An article with a wrong figure publishes with no one reviewing it | The fact checker rejects any number not in the data pack; the after-publish Telegram note has a one-tap unpublish |
| Computer use clashes with content-engine runs on the same VM | The shared desktop lock; exit 75 means wait for the next run, never force it |
| Errors in automated figures damage trust | Minimum counts, confidence labels, the fact checker, a corrections page |
| Too much to build for one person | The phases are in value order; Phase 0 and the index alone already improve the site |
| Map work grows without end | Start with districts and compound dots; outlines and the price grid only where data supports them |
| A complaint from a developer or a site | Neutral wording, sources and dates on figures, the takedown process |

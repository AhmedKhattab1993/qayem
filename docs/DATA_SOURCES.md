# Data sources for Egypt: what can be ingested, and how

Reference inventory, researched 2026-11-25. It lists every source found that can help Qayem's
analytics: property prices and supply, and everything that moves them, such as rates, the pound,
inflation, building costs, credit, policy, population, geography and demand signals. Each source is
classified by **how it can be read**, which follows the rules in [STRATEGY.md](STRATEGY.md) 5.1
and 5.4.

**How it was checked.** Every URL marked as checked was requested on 2026-11-25 from the operator's
Mac, which is on an Egyptian IP, with a normal browser User-Agent. The nightly updater runs in a
Cloudflare container outside Egypt, so a source that answers here can still time out or block there
(Nawy did on 2026-11-22, see [CLOUD_UPDATES.md](CLOUD_UPDATES.md)). Government `.gov.eg` hosts are
the most likely to behave differently. Rows marked *not probed* come from desk research only.

## Classes

| Class | Meaning | How Qayem reads it |
|---|---|---|
| **S: script** | A public API, feed, file or plain HTML page. No challenge and no login, and robots.txt and the terms allow it. | The shared fetcher (`httpx`, polite rate limit, robots respected), on a schedule. |
| **S-key: script with a free key** | Same as S, but a free account or API key is needed first. | Create the key once (by hand or by computer use), keep it in secrets, then script. |
| **CU: computer use** | Public, and a person may browse it, but there is no clean feed: script-heavy pages, PDFs behind a form, dashboards, price lists in images. | VM only, behind the desktop lock ([STRATEGY.md](STRATEGY.md) 5.4), on a monthly or quarterly schedule, with extraction to the review queue. |
| **H: human or press** | No machine route. The figure only appears in news, a phone call, an event or a printed booklet. | Read through the news feeds below, or entered by hand into `observations`. |
| **L: licence or agreement** | The data exists but is paid, behind a client login, or the terms forbid extraction. | Out under the current direction (free only, no partnerships), unless the owner decides otherwise. |
| **X: excluded** | Bot protection (403, a JS challenge, a WAF 202) or terms that forbid automated access. | Not read, by any method. Computer use is never used to get past a block. |

Status codes in the tables: `200` OK, `202` empty WAF challenge, `403` blocked, `429` rate limited,
`503` JS challenge, `timeout`, `DNS` name does not resolve, `TLS` certificate or handshake error.

---

## 1. Property listings and transactions

| Source | What it gives | Access | Class | Checked 2026-11-25 |
|---|---|---|---|---|
| AqarExit | Contract-transfer units: cash, balance, installments | sitemap + unit pages | **S** (in use) | 200 |
| Nawy (resale and developer sale) | Resale asking prices and developer launch prices with plans | `__NEXT_DATA__` | **S** (in use) | 200 (timed out from the container on 22 Nov) |
| Aqarmap, OpenSooq, Semsar | City-market asking prices across governorates | SSR / `__NEXT_DATA__` / microdata | **S** (in use, market sources) | Aqarmap 200 |
| GPM, Coldwell Banker | Brokerage resale catalogues | HTML / sitemap | **S** (in use, cross-check) | not re-probed |
| Aqarmap Trends report | Yearly market report: price index, demand index, top areas | `https://i.aqarmap.com/trends/aqarmap-trends-2025-en-full.pdf` | **S** (yearly PDF, AI extraction) | 200, PDF 3 MB |
| Official Egyptian Real Estate Platform (`realestate.gov.eg`, Egypt MLS) | Licensed-broker listings with `mlsId`, price, area, beds, location, served in the Next.js payload; mortgage page; terms | `/en/buy/residential-for-sale/...`, `sitemap.xml` | **L** | 200, robots allows `/`. **Terms §11 forbid "extract or reuse data without authorization".** Needs written permission. |
| Government auctions (`auctions.realestate.gov.eg`) | Property and land auctions | web app | **CU** if the terms allow it, otherwise **L** | timeout |
| Property Finder Egypt | The largest portal (about 600k visits a month) | site | **X** | Homepage and `sitemaps/index-sitemap.xml` now answer 200, but listing and Insights Hub pages return an empty WAF `202`. robots disallows `/search?`. Still excluded. |
| Bayut Egypt | Portal, plus MyBayut market notes | site | **X** | Homepage 503 challenge. robots and sitemaps 200, MyBayut WP-JSON 401. |
| Dubizzle Egypt (formerly OLX) | Classifieds | site | **X** | 503 challenge (robots.txt is readable) |
| RE/MAX Egypt (`remax.com.eg`) | Brokerage catalogue | HTML | **S** candidate (no resale flag checked yet) | 200 |
| Sakneen (`sakneen.com`) | Developer inventory platform | HTML | **S** candidate | 200 |
| Eshtri Aqar (`eshtriaqar.com`) | Classifieds | HTML (small shell, likely JS) | **CU** candidate | 200, 20 kB |
| Aqar Misr (`realestate.eg`), Aqar Ya Masr | Classifieds | HTML | **S**, assessed and not added ([OPERATIONS.md](OPERATIONS.md)) | 200 |
| NewHomez, Century 21 Egypt, ElWaseet | Portals and brokers | site | unknown | timeout / DNS |
| Airbnb | Short-term rents, North Coast and Cairo | site | **X** (terms forbid scraping) | 200 |
| Inside Airbnb | Open Airbnb scrapes | `insideairbnb.com/get-the-data/` | not usable | 200, **no Egyptian city** |
| AirDNA | Short-term rental analytics | app | **L** (paid) | 403 |
| Booking.com | Coastal hotel and apartment prices | site | **X** | 202 challenge |
| Real Estate Publicity Department (الشهر العقاري), Ministry of Justice | Registered transfers: the only true transaction prices | `moj.gov.eg` | **H** (no public statistics; counts appear in the press) | 200 |
| Broker WhatsApp sheets, price checks, user reports | Asking prices with the over, prices paid | Qayem's own intake | in use ([PRICE_GUIDE.md](PRICE_GUIDE.md) phase 4) | n/a |

## 2. Developers and listed companies

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| TMG, Palm Hills, SODIC, Madinet Masr investor pages | Contracted sales, launches, delivery, price moves | IR pages and PDFs | **S** (in use, `reports.py`) | 200 |
| Emaar Misr investor relations | Same | `emaarmisr.com/en/investor-relations/` | **X** to scripts. Use its press releases (section 9). | 403 |
| ORA Developers IR | Same | `ir.oradevelopers.com` | unknown (find the right host) | DNS |
| Mountain View, Hassan Allam and other unlisted developers | Launch price lists, brochures, payment plans | sites, often script-heavy or "call for price" | **CU** (planned: `scripts/vm-developer-pages.py`) | 200 |
| Egyptian Exchange (EGX): disclosures, index data, real-estate sector index | Filings, share prices | `egx.com.eg` | **X**: F5/Shape JS challenge (`bobcmn`) on every page | 200 with challenge body |
| Mubasher (`mubasher.info`) | EGX quotes and disclosures | Angular SPA | **CU** or skip (terms not checked) | 200 shell |
| Yahoo Finance `.CA` tickers (for example `TMGH.CA`) | Daily developer share prices | unofficial chart API | **L/X** (unofficial, rate-limited) | 429 |
| Argaam, MarketScreener | Quotes and financials | site | **X** / **L** | 200 / 403 |
| The Board Consulting, KW Egypt "Property Market Intelligence" | Top-10 developers' contracted sales (EGP 1.065 trn in 9M 2026) | reports through the press | **H** (figures from news) | `theboardconsulting.com` 200 |
| Association of Real Estate Developers (ARED) | Industry price-change estimates | press | **H** | `ared-eg.org` DNS |

## 3. Government housing, land and urban development

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| New Urban Communities Authority (NUCA, `newcities.gov.eg`) | Land offerings and auctions with EGP per m² (an official floor per new city), city announcements | HTML | **S** (in use, `official.py`) | **https times out, http answers 200**. Switch the parser to http or add a fallback. |
| Real-estate platform news (`blogs.realestate.gov.eg`) | NUCA land offerings with prices per m², social-housing offerings and terms, mortgage terms, CAPMAS housing figures | WordPress REST: `/wp-json/wp/v2/news` (the `posts` type holds marketing guides) | **S** | 200 JSON |
| Social Housing and Mortgage Finance Fund (SHMFF) | Social-housing unit prices, mortgage rates (8% and 12%), offerings ("Housing for All") | `shmff.gov.eg` | **H** (read through the news and the platform blog) | 500 / timeout |
| "Housing for All" terms booklets | Unit prices, sizes and locations per offering | PDFs on NUCA and Digital Egypt | **CU** (per offering, some are paid booklets) | not probed |
| Ministry of Housing (`mhuc.gov.eg`) | Announcements | HTML | **CU** (833-byte shell) | 200 |
| New Administrative Capital (ACUD, `acud.eg`) | District launches, land prices | HTML | **CU** | TLS |
| General Organization for Physical Planning (GOPP) | Strategic city plans, land use | site | **CU** | TLS |
| Informal Settlements Development Fund | Informal-area upgrades | site | unknown | DNS |
| Building-violation reconciliation (Law 187/2023) and permits | Permits issued, units reconciled | governorate sites (`cairo.gov.eg` 200), press | **H** | 200 |
| Unified Building Code (back since October 2024) | Height and density limits per area | press, official gazette | **H** | n/a |

## 4. Money, credit and the pound

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| Central Bank of Egypt: rates pages | FX rates, overnight rates, inflation | HTML | **S** (in use, `rates.py`) | 200 |
| CBE time series (`/en/economic-research/time-series`) | **Only the balance of payments is current** (quarterly, to April–June 2026); the other groups stop at June 2023. XLSX downloads in 14 groups: **Domestic Credit** (credit to households and real estate), **Deposits**, **Balance of Payments** (non-residents' real-estate investment: USD 2.8 bn in FY2025/26), **Investments by economic sectors**, **Interest Rates** (deposit and loan rates), **Tourism** (tourist nights), Inflation, GDP, State Budget, Domestic and External Debt | `/-/media/project/cbe/listing/time-series/.../*.xlsx` from `downloadlist?category=<id>` | **S** | 200 |
| CBE T-bill auctions, CONIA, interbank | Risk-free yields: what a buyer gives up by buying property | `/en/auctions/egp-t-bills`, `/en/economic-research/statistics/conia` | **S** | 200 |
| CBE Monetary Policy Committee | Rate-decision calendar and statements (an article trigger already) | `/en/monetary-policy` | **S** | 200 |
| CBE Residential Property Price Index | An official RPPI, being built (2026 conference paper) | not published yet | watch | n/a |
| Financial Regulatory Authority (FRA) | Monthly non-bank financing statistics: **mortgage finance value and contracts**, real-estate funds, real-estate crowdfunding (approved July 2026) | WordPress REST: `fra.gov.eg/en/wp-json/wp/v2/fra_news` | **S** (press releases, figures in text) | 200 JSON |
| Egyptian Mortgage Refinance Company | Refinanced volume | site | unknown | DNS |
| Bank savings certificates and mortgage products (NBE, Banque Misr, CIB, HDB) | Certificate rates (the main alternative to property), mortgage rates and terms | bank sites (SPAs) | **CU** monthly; the averages are in the CBE XLSX | 200 (shells) |
| Parallel USD rate: Binance P2P USDT/EGP | Market price of the dollar, used for USD figures and to see devaluation fear | `POST p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search` | **S** (undocumented endpoint, low frequency) | 200 JSON, asks at EGP 55.50 per USDT |
| Investing.com USD/EGPp | Parallel-rate history | site | **X** | 403 |
| Official FX mid-rates (`open.er-api.com`) | Backup to CBE | JSON | **S** | 200 |
| Gold prices in EGP (iSagha, gold-price-today, Gold Bullion Egypt, eDahab) | Gold per gram, 21k: the other store of value Egyptians use | HTML | **S** (one site, daily) | 200 |

## 5. Macroeconomy and prices

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| **CAPMAS JSON API** (found in the new site's bundle) | Headline indicators (inflation 12.0% in Oct 2026, unemployment, imports and exports), **release calendar** (`api/Calendar/GetHomeCalendar`), news, subjects, publications, `EgyptPopulation`, `GovernoratePopulation` | `https://www.capmas.gov.eg:8080/api/...` (also `:8087` search, `:8090` external trade) | **S** | 200 JSON, robots allows all. Publication search parameters still to work out. |
| CAPMAS old pages | Formerly read by `official.py` (`Pages/StaticPages.aspx?page_id=5035`) | HTML | — | Returns the 1.4 kB SPA shell; replaced by the API above (2026-11-25). |
| CAPMAS publications | Bulletin of Housing (units built: 212k in FY2024/25), building permits, **monthly building-materials price bulletin**, construction statistics, marriages (household formation), income and expenditure survey (HIECS), 2017 census (old-rent units) | `api/Publication*`, PDFs | **S** for the catalogue, **CU** or paid for some downloads (`PublicationPrice`) | API 200 |
| CAPMAS data archive (NADA, `censusinfo.capmas.gov.eg`) | Survey metadata, DDI | was a NADA catalogue | moved: `www.censusinfo…` now redirects to `metadata.capmas.gov.eg`, old paths 404 | DNS / 404 |
| Ministry of Planning (MPED) | Quarterly GDP growth by sector (real estate, construction), investment plan | `mped.gov.eg` HTML | **CU** | 200 |
| Ministry of Finance | Monthly financial report, budget, real-estate tax revenue | `mof.gov.eg` | **CU** (report URL moved) | 200 / 404 |
| Cabinet IDSC | Polls and studies | SPA | **CU** | 200 shell |
| GAFI | New companies by sector (real-estate company formation) | HTML | **CU** | 200 |
| S&P Global Egypt PMI | Monthly non-oil activity and input costs (47.2 in Oct 2026) | press-release list | **S** (headline from the release); history **L** | 200 |
| World Bank API | Annual macro, urbanisation (42.9% urban, 2025), population | `api.worldbank.org/v2/country/EGY/...` | **S** | 200 JSON |
| IMF | IFS, WEO forecasts | `api.imf.org/external/sdmx/2.1` (SDMX) | **S** | SDMX 200. **DataMapper API 403 from this host.** |
| DBnomics | Mirror of IMF, World Bank, BIS and others in one JSON API (for example `IMF/IFS/M.EG.PCPI_IX`) | `api.db.nomics.world/v22` | **S** | 200 JSON |
| BIS | Policy rates, effective exchange rates | `stats.bis.org` SDMX | **S** (series key to fix) | 404 for the key tried |
| UN SDG API, ILO (rplumber), OECD SDMX | Development and labour indicators | JSON / CSV | **S** | 200 |
| UN Comtrade | Egypt imports of rebar, cement and inputs (cost pressure) | `comtradeapi.un.org/public/v1/preview` (key for full data) | **S** / **S-key** | 200 |
| FRED | World Bank-sourced Egypt series | API | **S-key** | not usable from curl here (HTTP/2 error) |
| World Bank Microdata, ERF OAMDI, IPUMS, DHS | Household microdata (incomes, housing, tenure) | catalogues | **S** metadata, data by application (**L**) | 200 |
| Trading Economics, CEIC, Statista, Global Property Guide, Numbeo | Aggregated series and indices | sites or paid APIs | **L** | 200 / 403 |
| Centre for Affordable Housing Finance in Africa | Yearly Egypt housing-finance profile | site | **CU** or download by hand | 403 |

## 6. Building costs

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| Arab Steel Summit (`aisusteel.org`) | Weekly Egyptian rebar price reports (EGP per ton, by producer) | HTML articles | **S** | 200 |
| Ezz Steel, Suez Cement, Arabian Cement, Lafarge Egypt | Producer sites (no public price lists found) | HTML | **H** | 200 |
| Daily "steel and cement prices today" articles (Masrawy, Youm7, Al Watan) | Daily rebar and cement prices | news feeds (section 9) | **S** through news extraction | 200 |
| CAPMAS building-materials bulletin | Official monthly retail prices of materials by governorate | CAPMAS publications | see section 5 | — |
| EgyptERA electricity tariffs, EGAS household gas connections | Running cost of a home; new household connections as an occupancy proxy | HTML, yearly reports | **CU** | 200 |

## 7. Rents and yields

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| **Marsad Omran** (built-environment observatory) | **Cairo, Giza and Alexandria Rent Price Indices** (rent per m² by district, from listings; Giza and Alexandria editions in Nov 2026), housing-bulletin analysis, policy briefs (old-rent law, developers' federation draft law) | WordPress REST: `marsadomran.info/wp-json/wp/v2/posts` | **S** | 200 JSON |
| JLL Cairo Living reports | Quarterly asking rents and sale prices, New Cairo and 6th of October | PDFs on `jll.com` (some direct, some behind forms) | **CU** quarterly | Cairo market page 404 (moved) |
| Old-rent law (Law 164/2025) | About 1.6 m residential units being released over 7 years, 15% yearly rent rises from Sept 2026 | CAPMAS 2017 census, press | **H** | n/a |
| Rent listings on the existing market sources (Aqarmap, OpenSooq, Semsar) | Rent asking prices: Qayem's own gross yields | existing parsers, with new rent scopes | **S** | in use (sale only today) |

## 8. Demand and attention signals

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| Google Search Console, Bing Webmaster (Qayem's own) | Queries, impressions (article triggers already) | APIs with OAuth or key | **S-key** | n/a |
| Google Trends (Egypt: "شقق", compound names, "تنازل") | Relative search interest per area | unofficial endpoints rate-limited; official API is an alpha by application | **CU** (monthly CSV export) or apply for the API | 429 |
| Wikipedia pageviews | Interest in new cities (New Administrative Capital, New Alamein…) | `wikimedia.org/api/rest_v1/metrics/pageviews/...` | **S** | 200 JSON |
| GDELT DOC 2.0 | Volume and tone of Egyptian real-estate news | `api.gdeltproject.org/api/v2/doc/doc` | **S** (one request every 5 s) | 200 (429 above the limit) |
| Meta Ad Library | How many ads each developer runs (launch intensity) | API covers only political ads in Egypt; the web library shows all ads | **CU** only if no login is needed, otherwise out | API 400 without a token |
| Semrush, Similarweb | Portal traffic | sites | **L** (public summary pages readable by hand) | 200 |
| Reddit r/Egypt | Buyer questions | JSON API | **X** | 403 |
| Facebook compound groups | Questions, quoted prices | login wall | **H** (already decided, [STRATEGY.md](STRATEGY.md) 5.2 D) | n/a |

## 9. News and research (event triggers and figures only the press carries)

| Source | Access | Class | Checked |
|---|---|---|---|
| Daily News Egypt | RSS `dailynewsegypt.com/feed/` | **S** | 200 |
| Enterprise | RSS `enterpriseam.com/egypt/feed/` (headlines; much of the text is paid) | **S** | 200 |
| Amwal Al Ghad | WP REST `/wp-json/wp/v2/posts` | **S** | 200 |
| Al Borsa News | WP REST `/wp-json/wp/v2/posts` | **S** | 200 |
| Invest-Gate | WP REST `/wp-json/wp/v2/posts` | **S** | 200 |
| Youm7 section RSS, Masrawy RSS | RSS (section id to confirm) | **S** | 200 |
| Google News RSS search | `news.google.com/rss/search?q=...&gl=EG` | **X**: robots.txt disallows the feed path | 200, but disallowed |
| Nawy blog | RSS `nawy.com/blog/feed` | **S** | 200 |
| Ahram Online, Zawya, Arab Finance, Al Mal News | HTML (no working feed found: `/rss/` 404, Zawya RSS 403, Arab Finance RSS 410, Al Mal 404) | **CU** or Google News RSS | 200 pages |
| Knight Frank, Savills research | report pages, downloads behind forms | **CU** | 200 |
| CBRE, Colliers research | sites | **X** | 403 |
| EFG Hermes, CI Capital, HC, Beltone research | client portals, some public PDFs | **L** / **CU** for public PDFs | 247-byte shells / 200 / 404 |

## 10. Geography, population and infrastructure

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| OpenStreetMap: Geofabrik extract, Nominatim, Overpass | Boundaries, compound outlines, roads, metro and monorail lines, schools, hospitals | files / APIs | **S** (in use, `build-map-data.py`) | Geofabrik 200, Nominatim 200 (1 request a second), `overpass-api.de` 502 today (use another instance) |
| Protomaps basemap | Vector tiles | PMTiles | **S** (in use) | n/a |
| Overture Maps | Buildings, places (POIs), addresses, beyond OSM | GeoParquet on S3 / Azure | **S** | 200 |
| Google Open Buildings, Microsoft building footprints | Every building's footprint: density, new construction per compound | files | **S** | 200 |
| GHSL (EU JRC) | Built-up area and population grids over time: where cities grow | downloads | **S** | 200 |
| WorldPop | 100 m population counts and density | `hub.worldpop.org/rest/data/pop/wpgp?iso3=EGY` | **S** | 200 JSON |
| HDX | Admin boundaries (COD-AB), Meta high-resolution population, **Meta Relative Wealth Index** (neighbourhood wealth) | CKAN API `data.humdata.org/api/3/action/...` | **S** through the API | API 200; dataset pages give a WAF 202 |
| geoBoundaries | Admin levels 1 and 2 | JSON API | **S** | 200 |
| Ookla open data | Fixed and mobile internet speed per tile: a neighbourhood-quality signal | Parquet on S3 | **S** | 200 |
| VIIRS night lights (Colorado School of Mines EOG), NASA Black Marble | Monthly night lights: occupancy of new cities, North Coast seasonality | downloads after free sign-up | **S-key** | 200 |
| Sentinel-2 / Landsat through STAC (Element84 Earth Search, Microsoft Planetary Computer, Copernicus) | Satellite images: construction progress per compound, delivery checks | STAC APIs | **S** (search keyless; Copernicus downloads need a free account) | 200 |
| National Authority for Tunnels, Ministry of Transport | Metro, LRT and monorail project status | sites | **H** (status through the press) | `nat.gov.eg` DNS (www resolves), MoT 200 shell |
| Open-Meteo, NASA POWER | Climate (summer heat, coastal season) | JSON | **S** | 200 |

## 11. Tourism, foreign and expatriate demand

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| CBE time series: tourists and tourist nights | Monthly arrivals: coastal and resort demand | XLSX | **S** | 200 |
| CBE balance of payments | Remittances and non-residents' real-estate investment | XLSX | **S** | 200 |
| Ministry of Tourism and Antiquities | Announcements, hotel capacity | `mota.gov.eg` | **CU** | 200 |
| Foreign-ownership and residency-by-property rules | Who may buy, and how much | press, official gazette | **H** | n/a |

## 12. Law and policy

| Source | What it gives | Access | Class | Checked |
|---|---|---|---|---|
| House of Representatives | Draft laws (developers' federation, rent, registration) | `parliament.gov.eg` | **CU** | 200 |
| Supreme Constitutional Court | Rulings (old rent, 2024) | `cc.gov.eg` | **CU** | 200 |
| Manshurat (legal database) | Law texts | `manshurat.org` | **CU** | 200 |
| Statutory fee schedules | Registration and transfer costs | `src/qayem/data/fee_schedules.json` | by hand yearly (in use) | n/a |
| Cabinet, State Information Service, governorates | Decisions, permit freezes, reconciliation | sites | **H** | 200 |

---

## Integrated (2026-11-25)

`qayem fetch-signals` (`src/qayem/signals.py`) runs nightly in the cloud run after `fetch-rates`, writes
`market_signals` (one value per name and period) and `market_events`, and publishes them as
`overview.signals`: the `/index` page panel and the article agent's `rent_index` and `market_news` triggers.

| Source | Read as | Kept |
|---|---|---|
| CAPMAS `:8080/api/SelectedIndicator`, `Calendar/GetHomeCalendar` | JSON | `capmas_*` with the Arabic study period (the English one lags); release calendar |
| Binance P2P | JSON (POST) | `usdt_egp_p2p_buy`, `_sell`, midpoint: medians of 10 offers each way |
| World Bank API, DBnomics (IMF IFS) | JSON | `wb_*`, `imf_*` (the IFS series lag by about a year) |
| iSagha | Claude | `gold_24k`, `gold_21k`, `gold_18k`, `gold_pound` (midpoint of buy and sell), daily |
| NUCA home page (http) | Claude | `nuca_notice` events (land and housing offers, auctions, lotteries, tenders) |
| CBE balance of payments, latest quarterly sheet | Claude over the sheet's rows | `cbe_bop_*`: remittances, travel and Suez Canal receipts, FDI, portfolio, overall balance |
| Marsad Omran rent indices (WP REST) | Claude | `rent_*:<city>:<neighbourhood>` per quarter; a neighbourhood links to a guide district only when the district's name carries it (Dokki → Mohandessin & Dokki, not Zamalek → Central Cairo) |
| FRA releases (WP REST, latest plus relevance search) | Claude | `fra_<item>_<basis>`: month, year to date or outstanding, kept apart |
| Real-estate platform news (WP REST `news`) | Claude | `land_offer`, `housing_offer`, `mortgage_terms` events; `nuca_land_ppm:<city>:<use>` |
| Daily News Egypt, Enterprise (RSS); Amwal Al Ghad, Al Borsa, Invest-Gate (WP REST) | Claude screens the last 3 days | `news` events with their stated figures |

**How Claude is used.** `src/qayem/claude_cli.py` runs `claude -p --model claude-opus-5-5 --effort medium`
with no tools, MCP servers, settings or session, a JSON Schema for the answer, and checks that Opus
answered. No regular expressions extract figures (owner rule, 2026-11-25). Every figure carries a quote;
it is kept only when the quote is in the source and its number is in the quote. A document already read
(same address, same content) is not sent again, so a normal night makes 2 to 4 calls (gold, NUCA when its
page changes, the news, new posts).

**Live check, 2026-11-25** (from this Mac, about 2.5 minutes, all 11 sources OK): CAPMAS inflation
12.0% (Oct 2026); P2P dollar EGP 55.96; gold 21k EGP 5,545 a gram; remittances US$ 12,361.5 m and FDI
US$ 4,961.4 m in April–June 2026; Cairo rent EGP 80 per m² a month (Q3 2026), Dokki EGP 179, a 5.4%
gross yield against Mohandessin & Dokki's asking prices; FRA mortgage finance EGP 2.9 bn in January 2026.

## What the checks found

1. **CAPMAS has a public JSON API (now used), and the old CAPMAS parser was broken.** The new
   capmas.gov.eg is a React app; the page `official.py` read returned the app's empty shell.
   The app reads `https://www.capmas.gov.eg:8080/api/...` with no login: headline indicators, the
   release calendar, population and publications. robots.txt allows everything.
2. **The official real-estate platform is an MLS with clean data, but its terms forbid extraction.**
   Listings carry `mlsId`, price, area, beds and location in the page payload. Terms §11: users
   agree not to "extract or reuse data without authorization". It needs written permission.
3. **Property Finder's homepage and sitemaps now answer**, but every listing and Insights Hub page
   is an empty WAF 202. It stays excluded.
4. **CBE publishes downloadable XLSX time series** (credit, deposits, balance of payments with
   non-residents' real-estate investment, sector investments, tourism, interest rates) beyond the rate
   pages Qayem already reads.
5. **Several WordPress sites expose a REST API**: FRA (mortgage finance statistics), the real-estate
   platform's news (NUCA land prices per m², social-housing terms), Marsad Omran (rent indices for
   Cairo, Giza and Alexandria) and the business press (Amwal Al Ghad, Al Borsa, Invest-Gate).
6. **NUCA answers only on http** from this host (https times out).
7. **IMF DataMapper is blocked here (403)**; the IMF SDMX API and DBnomics both work.
8. **EGX sits behind F5/Shape bot protection.** Share prices and disclosures come from company IR
   pages and the press instead.

## What is next

Done on 2026-11-25: the CAPMAS API (replacing the broken parser), the CBE balance of payments, Marsad
Omran's rents, FRA, the real-estate platform's offers, NUCA, Binance P2P, gold, the World Bank, DBnomics
and the news feeds (see "Integrated"). The CBE's other time series were not added: they stop at June 2023.

| # | Source | Why | Effort |
|---|---|---|---|
| 1 | Rent scopes on Aqarmap, OpenSooq and Semsar | Qayem's own yields, with the same dedupe and segments | medium |
| 2 | Rebar and cement (Arab Steel Summit, daily price articles) | Construction-cost pressure behind developers' list prices | small |
| 3 | GDELT volume and tone | News attention per area, beyond the five feeds | small |
| 4 | Night lights, Sentinel-2, building footprints | Occupancy and construction progress per compound | large |
| 5 | Computer use: JLL and Knight Frank PDFs, Housing for All booklets, bank certificate rates | Quarterly context with no feed | medium, VM rules apply |

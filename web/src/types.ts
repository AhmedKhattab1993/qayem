export type Terms = "cash" | "plan" | "partial" | "unknown";
export type PropertyClass = "apartment" | "chalet" | "house";
/** How a unit compares with what can be bought now: the developer today and similar resale units. */
export type Level = "strong" | "good" | "in_line" | "mixed" | "pricier" | "check" | "unrated";

export interface Ref {
  key: string;
  name: string;
  name_ar?: string | null;
}
export interface Payment {
  terms: Terms;
  cash_equivalent: number | null;
  remaining: number | null;
  remaining_share: number | null;
  years: number | null;
  discount: number | null;
}
export interface Delivery {
  bucket: "ready" | "under_1y" | "1_2y" | "2_3y" | "3y_plus" | "unknown";
  date: string | null;
  years: number | null;
}
export interface Opportunity {
  level: Level;
  /** Mean of the comparisons' gaps (the less favourable basis of each); lower is better. */
  score: number | null;
  signals: ("developer" | "peers")[];
}
/** The unit against similar resale units listed now in the same compound. */
export interface Peers {
  count: number;
  rank: number;
  cash_ppm: number;
  median_cash_ppm: number;
  median_headline_ppm: number;
  gap: number;
  cash_gap: number;
  headline_gap: number;
  /** The cheapest similar unit, and this unit against it on the less favourable basis. */
  min_cash_ppm: number;
  min_headline_ppm: number;
  cheapest_gap: number;
  same_finishing: boolean;
}
/** The developer's current price for a similar unit in the same compound (Nawy developer sales). */
export interface UnitLaunch {
  gap: number;
  cash_gap: number;
  headline_gap: number;
  units: number;
  developer_cash: number;
  developer_price: number;
  cash_ppm: number;
  headline_ppm: number;
  down_share: number | null;
  plan_years: number | null;
  delivery_year: number | null;
  area_range: [number, number];
  types: string[];
  finishing: string;
  same_finishing: boolean;
  /** The developer's list price per m² today against the seller's contract price (AqarExit sells at contract price). */
  since_contract: { year: number; contract_ppm: number; change: number; annual: number | null } | null;
}
/** A listed price change over the last 60 days, from the seller's or developer's own edits. */
export interface PriceChange {
  from: number;
  to: number;
  change: number;
  at: string;
  edits: number;
}
/** How fast stock leaves and how prices move, from Qayem's own record of every crawl. */
export interface History {
  delisted_30d: number;
  turnover_30d: number | null;
  new_30d: number;
  median_days_listed: number | null;
  tracked_delisted: number;
  price_cuts_60d: number;
  price_rises_60d: number;
  median_cut: number | null;
  developer_change_60d: number | null;
  developer_tracked: number;
  developer_rising: number;
  developer_falling: number;
}
export interface Unit {
  id: number;
  source: string;
  source_name: string;
  source_url: string | null;
  title: string | null;
  /** The source's first photo of the unit, if it published any. */
  photo: string | null;
  property_type: string;
  class: PropertyClass | null;
  price: number;
  area_m2: number;
  price_per_m2: number;
  bedrooms: number | null;
  district: string | null;
  compound: Ref | null;
  developer: Ref | null;
  finishing_class: string;
  delivery: Delivery;
  payment: Payment;
  launch: UnitLaunch | null;
  peers: Peers | null;
  opportunity: Opportunity;
  contract_year: number | null;
  is_resale: boolean | null;
  price_change?: PriceChange | null;
}
export interface UnitFull extends Unit {
  /** Every photo the source published, in its order. */
  images: string[];
  bathrooms: number | null;
  finishing: string | null;
  installments: boolean | null;
  down_payment: number | null;
  installment_months: number | null;
  resale_evidence: string | null;
  last_seen_at: string | null;
  first_seen_at?: string | null;
  unknowns: string[];
  description: string | null;
}
export interface Comparable extends Unit {
  cash_ppm: number;
}
export interface UnitDetail {
  unit: UnitFull;
  comparables: Comparable[];
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
export interface Scope {
  count: number;
  sources: { id: string; name: string; count: number; share: number }[];
}
/** Observed prices per class: resale contract and cash-today prices, and the developer's today. */
export interface ClassSummary {
  class: PropertyClass;
  units: number;
  median_asking_ppm: number | null;
  median_cash_ppm: number | null;
  developer_ppm: number | null;
  developer_cash_ppm: number | null;
  median_gap: number | null;
  compared: number;
  median_contract_year: number | null;
}
export interface Profile {
  ready_share: number | null;
  delivery_known: number;
  median_years_to_delivery: number | null;
  latest_delivery_year: number | null;
  plan_share: number | null;
  median_remaining_share: number | null;
  median_plan_years: number | null;
  median_plan_discount: number | null;
  finishing: Record<string, number>;
  opportunities: Partial<Record<Level, number>>;
  scope: Scope;
}
/** The developer's current units in a compound (or across a developer) against its resale units. */
export interface Launch {
  units: number;
  median_headline_ppm: number | null;
  median_cash_ppm: number | null;
  median_plan_years: number | null;
  median_down_share: number | null;
  latest_delivery_year: number | null;
  phases: string[];
  compared: number;
  median_gap: number | null;
  median_since_contract: number | null;
}
export interface Compound extends Profile {
  launch: Launch | null;
  key: string;
  name: string;
  name_ar: string | null;
  district: string;
  district_key: string;
  developer: Ref | null;
  units: number;
  good_count: number;
  classes: ClassSummary[];
  area_range: [number, number];
  types: Record<string, number>;
  history?: History;
  guide?: EntityGuide | null;
}
export interface Developer extends Profile {
  launch: Launch | null;
  key: string;
  name: string;
  name_ar: string | null;
  units: number;
  good_count: number;
  compounds: {
    key: string;
    name: string;
    name_ar: string | null;
    district: string;
    units: number;
    good_count: number;
    median_gap: number | null;
  }[];
  districts: { name: string; units: number }[];
  delivery_changes: { tracked_units: number; postponed: number; brought_forward: number };
  history?: History;
}
export interface District extends Profile {
  key: string;
  name: string;
  name_ar?: string | null;
  region?: string | null;
  location?: { lat: number; lon: number } | null;
  /** Every listing in the price guide, across all sources (resale units compared are `units`). */
  listings?: number;
  guide?: EntityGuide | null;
  units: number;
  good_count?: number;
  classes: ClassSummary[];
  compound_count: number;
  compounds?: {
    key: string;
    name: string;
    name_ar: string | null;
    units: number;
    good_count: number;
    developer: Ref | null;
    median_gap: number | null;
    compared: number;
  }[];
  history?: History;
}
export interface CompoundDetail {
  compound: Compound;
  district: District | null;
  developer: Developer | null;
}
export interface Overview {
  total_records: number;
  total_eligible: number;
  total_resale: number;
  rated_count: number;
  opportunities: Partial<Record<Level, number>>;
  compound_count: number;
  developer_count: number;
  district_count: number;
  last_updated: string | null;
  first_observed: string | null;
  observation_days: number;
  history_ready: boolean;
  sources: {
    id: string;
    name: string;
    count: number;
    resale_count: number;
    rated_count: number;
    last_seen_at: string | null;
    status: string;
  }[];
  /** Developers' current prices, read only to compare resale against. */
  benchmarks: { id: string; name: string; count: number; last_seen_at: string | null; status: string }[];
  scope: Scope;
  payment_terms: Partial<Record<Terms, number>>;
  plan_median_discount: number | null;
  discount_rate: number;
  launch: { units: number; matched: number; unmatched: number; compounds: number; compared: number; median_gap: number | null };
  peers: { ranked: number; min_similar: number };
  since_contract: { units: number; median_annual: number | null };
  thresholds: {
    strong_all: number;
    strong_one: number;
    good_all: number;
    good_one: number;
    pricier: number;
    check_developer: number;
    check_peers: number;
    check_cheapest: number;
  };
  developer_gaps: { key: string; name: string; name_ar: string | null; gap: number; units: number }[];
  history?: History & { cohort_start: string | null; liquidity_days: number; price_days: number };
  /** The Central Bank of Egypt's rates of the day, for the currency switch. */
  rates?: Rates | null;
  guide?: GuideCounts | null;
  /** Months with a published Qayem Index, newest first. */
  index_months?: string[];
}
export interface Catalog {
  districts: { key: string; name: string; units: number }[];
  compounds: {
    key: string;
    name: string;
    name_ar: string | null;
    district: string;
    developer: string | null;
    developer_ar: string | null;
    units: number;
  }[];
  developers: { key: string; name: string; name_ar: string | null; units: number }[];
  property_types: { value: string; class: PropertyClass | null; count: number }[];
}
export interface Evaluation {
  status: "compared" | "compound_not_found";
  inputs: {
    property_type: string;
    class: PropertyClass | null;
    area_m2: number;
    price: number;
    price_per_m2: number;
    finishing_class: string;
    compound: Ref | null;
    developer: Ref | null;
    district: string | null;
    delivery?: Delivery;
  };
  payment: Payment;
  launch: UnitLaunch | null;
  peers: Peers | null;
  opportunity: Opportunity;
  comparables: Comparable[];
  unknowns: string[];
}

/* ——— The price guide, the map and the Qayem Index ——— */
export type Confidence = "high" | "medium" | "indicative";
export interface Rates {
  day: string;
  source: string;
  /** EGP per one unit of each currency, keyed by lower-case code. */
  egp_per: Record<string, number>;
  key?: Record<string, { day: string; value: number } | null>;
}
export interface SourceShare {
  id: string;
  name: string;
  count: number;
  share: number;
}
export interface Period {
  start: string;
  end: string;
  days?: number;
}
export interface GuideRules {
  min_multi: number;
  min_single: number;
  high_min: number;
  high_max_share: number;
  window_days: number;
  method_version?: string;
  [key: string]: unknown;
}
export interface GuideCounts {
  listings: number;
  kept: number;
  duplicates: number;
  suspect: number;
  developer_listings: number;
  segments: number;
  high: number;
  medium: number;
  indicative: number;
  multi_source_share: number;
  sources: SourceShare[];
  period?: Period;
  rules?: GuideRules;
  index_month?: string;
}
/** One class's figures in a district or compound (the map, the guide's headline, the index). */
export interface GuideRow {
  class: PropertyClass;
  count: number;
  confidence: Confidence;
  single_source: boolean;
  median_ppm: number;
  p25_ppm: number;
  p75_ppm: number;
  median_cash_ppm: number | null;
  median_price: number;
  /** Resale against buying new today, in today's money: negative means resale is cheaper. */
  resale_vs_new: number | null;
  sources: string[];
  developer_ppm: number | null;
}
export interface GuideDistrict {
  key: string;
  name: string;
  name_ar: string | null;
  region: string;
  listings: number;
  units: number;
  headline: GuideRow | null;
}
export interface Guide {
  period: Period;
  counts: GuideCounts;
  rules: GuideRules;
  index_month: string;
  regions: Record<string, { name: string; name_ar: string }>;
  districts: GuideDistrict[];
  moves: IndexChange[];
}
export interface Segment {
  key: string;
  district: string;
  district_name: string;
  district_name_ar: string | null;
  region: string;
  /** "*" for the whole district, "outside" for listings outside any compound, else the compound's key. */
  compound: string;
  compound_name: string | null;
  compound_name_ar: string | null;
  class: PropertyClass;
  size: string;
  delivery: "*" | "ready" | "under_2y" | "later";
  count: number;
  sources: SourceShare[];
  single_source: boolean;
  confidence: Confidence;
  median_ppm: number;
  p25_ppm: number;
  p75_ppm: number;
  median_cash_ppm: number | null;
  median_price: number;
  p25_price: number;
  p75_price: number;
  median_area: number;
  plan_share: number | null;
  price_cuts: number | null;
  developer: { count: number; median_ppm: number | null; median_cash_ppm: number | null } | null;
  resale_vs_new: number | null;
}
export interface EntityGuide {
  period: Period;
  segments: Segment[];
  headline: Segment | null;
}
export interface MapDistrict extends GuideDistrict {
  lat: number;
  lon: number;
  classes: GuideRow[];
}
export interface MapCompound {
  key: string;
  name: string;
  name_ar: string | null;
  district: string;
  lat: number;
  lon: number;
  units: number;
  listings: number;
  headline: GuideRow | null;
  developer: Ref | string | null;
}
export interface MapData {
  period: Period;
  month: string;
  districts: MapDistrict[];
  compounds: MapCompound[];
  attribution: string;
  placed_compounds: number;
  compounds_with_figures: number;
}
export interface IndexChange {
  kind: string;
  key: string;
  name: string;
  name_ar: string | null;
  class: PropertyClass;
  from: number;
  to: number;
  change: number;
  count: number;
  previous_count: number;
}
export interface QayemIndex {
  name: string;
  name_ar: string;
  month: string;
  label: string;
  label_ar: string;
  period: Period;
  as_of: string;
  provisional: boolean;
  method_version: string;
  counts: GuideCounts;
  districts: { key: string; name: string; name_ar: string | null; region: string; count: number; classes: GuideRow[] }[];
  compounds: {
    key: string;
    name: string;
    name_ar: string | null;
    district: string;
    district_name: string;
    count: number;
    classes: GuideRow[];
  }[];
  changes: IndexChange[];
  licence: string;
  attribution: string;
}

/* ——— Articles ——— */
export interface ArticleRef {
  key: string;
  name: string;
  name_ar: string | null;
}
export interface ArticleSummary {
  slug: string;
  lang: "ar" | "en";
  title: string;
  summary: string;
  kind: string;
  published_at: string;
  district: ArticleRef | null;
  compound: ArticleRef | null;
}
export type ArticleBlock =
  | { type: "h2"; text: string }
  | { type: "p"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; columns: string[]; rows: (string | number)[][] }
  | { type: "figure"; label: string; value: string | number; note?: string };
export interface Article extends ArticleSummary {
  updated_at: string | null;
  byline: string;
  translation: string | null;
  period: Period | null;
  sources: { name: string; url?: string }[];
  blocks: ArticleBlock[];
}
export interface ArticlePage {
  items: ArticleSummary[];
  total: number;
  page: number;
  pages: number;
}

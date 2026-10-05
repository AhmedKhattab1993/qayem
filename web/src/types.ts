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
}
export interface District extends Profile {
  key: string;
  name: string;
  units: number;
  classes: ClassSummary[];
  compound_count: number;
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

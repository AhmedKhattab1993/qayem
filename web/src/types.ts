export type Grade = "A" | "B" | "C";
export type Verdict = "below" | "within" | "above" | "suspect";
export type Terms = "cash" | "plan" | "partial" | "unknown";
export type PropertyClass = "apartment" | "chalet" | "house";

export interface Ref {
  key: string;
  name: string;
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
export interface Valuation {
  status: "valued" | "insufficient" | "not_modelled";
  reason?: string;
  grade?: Grade;
  fair_value?: number;
  fair_low?: number;
  fair_high?: number;
  fair_ppm?: number;
  basis?: "cash_equivalent" | null;
  compared_price?: number | null;
  deviation?: number | null;
  verdict?: Verdict | null;
  fair_headline?: number | null;
}
export interface Unit {
  id: number;
  source: string;
  source_name: string;
  source_url: string | null;
  title: string | null;
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
  valuation: Valuation;
  is_resale: boolean | null;
}
export interface UnitFull extends Unit {
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
export interface Breakdown {
  levels: { level: string; label: string | null; listings: number; change: number; ppm: number }[];
  adjustments: { factor: string; value: string | number; typical?: number; change: number }[];
}
export interface Comparable extends Unit {
  cash_ppm: number;
}
export interface UnitDetail {
  unit: UnitFull;
  breakdown: Breakdown | null;
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
export interface ClassSummary {
  class: PropertyClass;
  units: number;
  grade: Grade | null;
  reference_ppm: number | null;
  premium_vs_district: number | null;
  median_asking_ppm: number | null;
  median_cash_ppm: number | null;
  median_area: number | null;
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
  verdicts: Partial<Record<Verdict, number>>;
  scope: Scope;
}
export interface Launch {
  units: number;
  median_spread: number | null;
  median_headline_ppm: number | null;
  median_cash_ppm: number | null;
  median_plan_years: number | null;
  median_down_share: number | null;
  latest_delivery_year: number | null;
  phases: string[];
}
export interface Compound extends Profile {
  launch: Launch | null;
  key: string;
  name: string;
  district: string;
  district_key: string;
  developer: Ref | null;
  units: number;
  classes: ClassSummary[];
  premium_vs_district: number | null;
  grade: Grade | null;
  area_range: [number, number];
  types: Record<string, number>;
}
export interface Developer extends Profile {
  launch: Launch | null;
  key: string;
  name: string;
  units: number;
  premium_vs_district: number | null;
  premium_basis: number;
  compounds: { key: string; name: string; district: string; units: number; premium_vs_district: number | null; grade: Grade | null }[];
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
export interface GradeBacktest {
  grade: Grade;
  count: number;
  median_abs_error: number;
  within_10pct: number;
  within_20pct: number;
  range_low_pct: number;
  range_high_pct: number;
  calibrated: boolean;
}
export interface Overview {
  total_records: number;
  total_eligible: number;
  total_resale: number;
  valued_count: number;
  positioned_count: number;
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
    valued_count: number;
    last_seen_at: string | null;
    status: string;
  }[];
  scope: Scope;
  backtest: {
    trained_on: number;
    evaluated: number;
    median_abs_error: number | null;
    within_10pct: number | null;
    within_20pct: number | null;
    grades: GradeBacktest[];
    naive_baseline: { evaluated: number; median_abs_error: number | null; model_median_abs_error: number | null };
  };
  effects: {
    type: Record<string, number>;
    finishing: Record<string, number>;
    delivery: Record<string, number>;
    plan: Record<string, number>;
    area_doubling: Record<string, number>;
    discount_rate: number;
    shrinkage: number;
  };
  payment_terms: Partial<Record<Terms, number>>;
  plan_median_discount: number | null;
  launch: {
    units: number;
    compared: number;
    unmatched: number;
    compounds: number;
    median_spread: number | null;
    support: { units: number; median_residual: number | null };
  };
  discount_rate: number;
  verdicts: Partial<Record<Verdict, number>>;
  developer_premiums: { key: string; name: string; premium: number; units: number }[];
}
export interface Catalog {
  districts: { key: string; name: string; units: number }[];
  compounds: { key: string; name: string; district: string; developer: string | null; units: number }[];
  developers: { key: string; name: string; units: number }[];
  property_types: { value: string; class: PropertyClass; count: number }[];
}
export interface Evaluation {
  inputs: {
    property_type: string;
    class: PropertyClass | null;
    area_m2: number;
    price: number;
    compound: Ref | null;
    developer: Ref | null;
    district: string | null;
    finishing_class: string;
    delivery: Delivery;
    price_per_m2: number;
  };
  payment: Payment;
  valuation: Valuation;
  notes: string[];
  breakdown: Breakdown | null;
  comparables: Comparable[];
  unknowns: string[];
}

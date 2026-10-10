import type { ReactNode } from "react";
import { Banknote, BedDouble, CalendarClock, Coins, Grid2x2, KeyRound, Ruler, Tag, Wallet } from "lucide-react";
import { compact, date, money, number, quarterly } from "../lib";
import { getLanguage, t } from "../locale";
import type { UnitFull } from "../types";

type Tile = { key: string; icon: typeof Tag; label: string; value: ReactNode; feature?: boolean };

/** A figure with its unit set small: «EGP 6.8M» in English, «٦٫٨ مليون ج.م» in Arabic. */
function Figure({ value, unit, before = false }: { value: string; unit: string; before?: boolean }) {
  const small = <small>{unit}</small>;
  return (
    <>
      {before && small}
      {value}
      {!before && small}
    </>
  );
}

const egp = (value: number) =>
  getLanguage() === "ar" ? (
    <Figure value={compact(value)} unit={t("EGP")} />
  ) : (
    // en-GB writes compact figures as «6.8m»; a figure this large reads better as «6.8M».
    <Figure value={compact(value).toUpperCase()} unit={t("EGP")} before />
  );

function rooms(bedrooms: number | null, bathrooms: number | null): Tile | null {
  const beds = bedrooms === 0 ? t("Studio") : number(bedrooms);
  const icon = BedDouble;
  if (bedrooms != null && bathrooms != null)
    return { key: "rooms", icon, label: t("Bedrooms · bathrooms"), value: `${beds} · ${number(bathrooms)}` };
  if (bedrooms != null) return { key: "rooms", icon, label: t("Bedrooms"), value: beds };
  if (bathrooms != null) return { key: "rooms", icon, label: t("Bathrooms"), value: number(bathrooms) };
  return null;
}

function delivery(unit: UnitFull): Tile | null {
  const { bucket, date: when, years } = unit.delivery;
  const value =
    bucket === "ready" ? t("Ready") : when ? date(when, "month") : years != null ? t("In {n} years", { n: number(years, 1) }) : null;
  return value ? { key: "delivery", icon: KeyRound, label: t("Delivery"), value } : null;
}

/** The unit's main figures, one tile each, before the detail. A figure the listing does not publish has no tile. */
export function Glance({ unit }: { unit: UnitFull }) {
  const { payment } = unit;
  const plan = payment.terms === "plan" && payment.remaining != null;
  const tiles: (Tile | null)[] = [
    { key: "price", icon: Tag, label: t("Total price"), value: egp(unit.price) },
    plan && payment.cash_equivalent != null
      ? { key: "today", icon: Coins, label: t("Worth in today’s money"), value: egp(payment.cash_equivalent), feature: true }
      : null,
    plan ? { key: "paid", icon: Wallet, label: t("Paid at signing"), value: egp(unit.price - payment.remaining!) } : null,
    plan
      ? {
          key: "left",
          icon: CalendarClock,
          label:
            payment.years != null
              ? quarterly(payment) != null
                ? t("Left: ≈ {amount} a quarter for {n} years", {
                    amount: money(quarterly(payment), true),
                    n: number(payment.years, 1),
                    count: payment.years,
                  })
                : t("Left, over {n} years", { n: number(payment.years, 1), count: payment.years })
              : t("Still owed"),
          value: egp(payment.remaining!),
        }
      : null,
    payment.terms === "cash" ? { key: "payment", icon: Banknote, label: t("Payment"), value: t("Cash") } : null,
    payment.terms === "partial"
      ? { key: "payment", icon: CalendarClock, label: t("Term not published"), value: t("Installments") }
      : null,
    { key: "area", icon: Ruler, label: t("Area"), value: <Figure value={number(unit.area_m2)} unit={t("m²")} /> },
    { key: "ppm", icon: Grid2x2, label: t("Price per m²"), value: egp(unit.price_per_m2) },
    rooms(unit.bedrooms, unit.bathrooms),
    delivery(unit),
  ];
  return (
    <section className="glance" aria-label={t("At a glance")}>
      <dl className="glance-grid">
        {tiles
          .filter((tile): tile is Tile => tile != null)
          .map(({ key, icon: Icon, label, value, feature }) => (
            <div key={key} className={`glance-tile${feature ? " is-feature" : ""}`}>
              <span className="glance-icon" aria-hidden="true">
                <Icon size={18} />
              </span>
              <dt>{label}</dt>
              <dd className="num">{value}</dd>
            </div>
          ))}
      </dl>
    </section>
  );
}

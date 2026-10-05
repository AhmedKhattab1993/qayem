import { money, number, percent, signed, titleCase, tone, year } from "../lib";
import { t } from "../locale";
import type { Unit } from "../types";

/** This resale unit against the developer's current price for a similar unit in the same compound. */
export function DeveloperPrice({ unit }: { unit: Pick<Unit, "launch" | "payment" | "price" | "finishing_class"> }) {
  const launch = unit.launch;
  if (!launch) return null;
  const cheaper = launch.gap < 0;
  return (
    <div className="launch">
      <div className="launch-lead">
        <div className={`launch-headline ${tone(launch.gap)}`}>
          <strong className="num">{signed(launch.gap)}</strong>
          <p>
            {t(
              cheaper
                ? "This unit costs this much less than a similar unit the developer is selling now, both as listed and in today’s money."
                : "This unit costs this much more than a similar unit the developer is selling now, on the less favourable of listed price and today’s money.",
            )}
          </p>
        </div>
        {launch.since_contract && (
          <div className="launch-since">
            <strong className="num">
              {signed(launch.since_contract.change)}
            </strong>
            <p>
              {t(
                launch.since_contract.annual != null
                  ? "The developer’s list price per m² since the seller signed in {year}: {contract} then, {today} now ({annual} a year). This unit is sold at its {year} contract price."
                  : "The developer’s list price per m² since the seller signed in {year}: {contract} then, {today} now. This unit is sold at its {year} contract price.",
                {
                  year: year(launch.since_contract.year),
                  contract: money(launch.since_contract.contract_ppm),
                  today: money(launch.headline_ppm),
                  annual: signed(launch.since_contract.annual, 1),
                },
              )}
            </p>
          </div>
        )}
      </div>
      <dl className="facts facts-single">
        <div>
          <dt>{t("Developer’s price for this size")}</dt>
          <dd className="num">{money(launch.developer_price)}</dd>
        </div>
        <div>
          <dt>{t("This unit, as listed")}</dt>
          <dd className="num">
            {money(unit.price)}
            <small className={`muted ${tone(launch.headline_gap)}`}> · {signed(launch.headline_gap)}</small>
          </dd>
        </div>
        <div>
          <dt>{t("Developer’s plan")}</dt>
          <dd className="num">
            {launch.plan_years
              ? t("{down} down, {n} years", {
                  down: percent(launch.down_share),
                  n: number(launch.plan_years, 1),
                })
              : t("Cash")}
          </dd>
        </div>
        <div>
          <dt>{t("Developer’s finishing")}</dt>
          <dd className="num">
            {titleCase(
              launch.finishing === "unknown" ? null : launch.finishing,
            )}
            {!launch.same_finishing && unit.finishing_class !== "unknown" && (
              <small className="muted">
                {" "}
                ·{" "}
                {t("this unit: {finishing}", {
                  finishing: titleCase(unit.finishing_class),
                })}
              </small>
            )}
          </dd>
        </div>
        <div>
          <dt>{t("Developer’s delivery")}</dt>
          <dd className="num">{year(launch.delivery_year)}</dd>
        </div>
        <div>
          <dt>{t("Developer’s price in today’s money")}</dt>
          <dd className="num">{money(launch.developer_cash)}</dd>
        </div>
        <div>
          <dt>{t("This unit in today’s money")}</dt>
          <dd className="num">
            {money(unit.payment.cash_equivalent)}
            <small className={`muted ${tone(launch.cash_gap)}`}> · {signed(launch.cash_gap)}</small>
          </dd>
        </div>
      </dl>
      {!launch.same_finishing && (
        <p className="notice notice-soft">{t("The developer’s units have a different finishing, so this comparison does not count towards the opportunity.")}</p>
      )}
      <p className="fineprint">
        {t(
          "From {n} of the developer’s current units in this compound, {size} m², listed on Nawy. In today’s money, remaining installments on both sides are discounted at the same rate; the headline is the less favourable of the two gaps. Developer prices are list prices; negotiated discounts are not visible, and a resale unit often delivers sooner.",
          {
            n: number(launch.units),
            size:
              launch.area_range[0] === launch.area_range[1]
                ? number(launch.area_range[0])
                : `${number(launch.area_range[0])}–${number(launch.area_range[1])}`,
          },
        )}
      </p>
    </div>
  );
}

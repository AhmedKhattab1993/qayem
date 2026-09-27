import { Clock } from "lucide-react";
import { year, classLabel, money, number, percent, signed, titleCase, sep } from "../lib";
import { t } from "../locale";
import type { ClassSummary, Launch, Overview, Profile } from "../types";
import { GradeBadge } from "./Valuation";

/** Reference fair value per class: a finished, ready unit of typical size. */
export function ClassCards({ classes, premiumLabel = "vs district" }: { classes: ClassSummary[]; premiumLabel?: string }) {
  return (
    <div className="class-cards">
      {classes.map((item) => (
        <article key={item.class}>
          <div className="class-head">
            <span className="eyebrow no-rule">{classLabel(item.class)}</span>
            <GradeBadge grade={item.grade} />
          </div>
          <strong className="num">
            {item.reference_ppm ? money(item.reference_ppm, true) : "—"}
            <small> / {t("m²")}</small>
          </strong>
          <span className="muted">{t("Fair cash value, finished and ready, typical size")}</span>
          <dl>
            {item.premium_vs_district != null && (
              <div>
                <dt>{t(premiumLabel)}</dt>
                <dd className={`num ${item.premium_vs_district >= 0 ? "is-up" : "is-down"}`}>
                  {signed(item.premium_vs_district)}
                </dd>
              </div>
            )}
            <div>
              <dt>{t("Median asking / m²")}</dt>
              <dd className="num">{money(item.median_asking_ppm, true)}</dd>
            </div>
            <div>
              <dt>{t("Median cash-equivalent / m²")}</dt>
              <dd className="num">{money(item.median_cash_ppm, true)}</dd>
            </div>
            <div>
              <dt>{t("Listings")}</dt>
              <dd className="num">{number(item.units)}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

export function ProfileFacts({ profile }: { profile: Profile }) {
  const finishing = Object.entries(profile.finishing).filter(([level]) => level !== "unknown");
  const finishedTotal = finishing.reduce((sum, [, count]) => sum + count, 0);
  const verdicts = profile.verdicts;
  const positioned = (verdicts.below ?? 0) + (verdicts.within ?? 0) + (verdicts.above ?? 0);
  const rows: [string, string][] = [
    ["Ready to move in", `${percent(profile.ready_share)}${profile.delivery_known ? "" : ""}`],
    ["Median wait for the rest", profile.median_years_to_delivery ? t("{n} years", { n: number(profile.median_years_to_delivery, 1) }) : "—"],
    ["Latest promised delivery", year(profile.latest_delivery_year)],
    ["Listed on installment plans", percent(profile.plan_share)],
    ["Median share still owed", percent(profile.median_remaining_share)],
    ["Median plan length", profile.median_plan_years ? t("{n} years", { n: number(profile.median_plan_years, 1) }) : "—"],
    ["Headline above cash value by", percent(profile.median_plan_discount)],
    [
      "Finishing mix",
      finishedTotal
        ? finishing
            .slice(0, 3)
            .map(([level, count]) => `${titleCase(level)} ${percent(count / finishedTotal)}`)
            .join(sep())
        : "—",
    ],
    [
      "Priced below / within / above range",
      positioned
        ? `${percent((verdicts.below ?? 0) / positioned)}${sep()}${percent((verdicts.within ?? 0) / positioned)}${sep()}${percent((verdicts.above ?? 0) / positioned)}`
        : "—",
    ],
  ];
  return (
    <dl className="facts facts-single">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{t(label)}</dt>
          <dd className="num">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function HistoryPending({ overview }: { overview: Overview | null }) {
  if (!overview || overview.history_ready) return null;
  return (
    <p className="notice notice-soft">
      <Clock size={17} />
      <span>
        {t(
          overview.observation_days === 1
            ? "Price trends, time on market and delivery-date changes appear after eight weeks of observation. Qayem has observed this market for {n} day."
            : "Price trends, time on market and delivery-date changes appear after eight weeks of observation. Qayem has observed this market for {n} days.",
          { n: number(overview.observation_days) },
        )}
      </span>
    </p>
  );
}

/** The developer's current launch price for comparable units, against the resale market. */
export function LaunchPanel({ launch, scope }: { launch: Launch | null; scope: "compound" | "developer" }) {
  if (!launch || launch.median_spread == null)
    return (
      <p className="muted">
        {t(
          scope === "compound"
            ? "No current developer launch units could be matched to this compound."
            : "No current launch units from this developer could be matched to a resale compound.",
        )}
      </p>
    );
  const spread = launch.median_spread;
  return (
    <div className="launch">
      <div className={`launch-headline ${spread >= 0 ? "is-up" : "is-down"}`}>
        <strong className="num">{signed(spread)}</strong>
        <p>
          {t(
            spread >= 0
              ? "Buying new from the developer costs this much more than the resale market pays for the same unit, in today’s money."
              : "Buying new from the developer costs this much less than the resale market pays for the same unit, in today’s money.",
          )}
        </p>
      </div>
      <dl className="facts facts-single">
        <div>
          <dt>{t("Launch headline / m²")}</dt>
          <dd className="num">{money(launch.median_headline_ppm, true)}</dd>
        </div>
        <div>
          <dt>{t("Launch cash-equivalent / m²")}</dt>
          <dd className="num">{money(launch.median_cash_ppm, true)}</dd>
        </div>
        <div>
          <dt>{t("Typical launch plan")}</dt>
          <dd className="num">
            {t("{down} down, {n} years", { down: percent(launch.median_down_share), n: number(launch.median_plan_years, 1) })}
          </dd>
        </div>
        <div>
          <dt>{t("Latest launch delivery")}</dt>
          <dd className="num">{year(launch.latest_delivery_year)}</dd>
        </div>
        <div>
          <dt>{t("Launch units compared")}</dt>
          <dd className="num">{number(launch.units)}</dd>
        </div>
      </dl>
      {launch.phases.length > 0 && (
        <p className="muted" dir="auto">
          {t("Phases")}: {launch.phases.join(sep())}
        </p>
      )}
      <p className="fineprint">
        {t(
          "Launch units are priced against the model’s resale value for the same compound, unit type, finishing, delivery date, plan length and size. Launch prices are list prices; negotiated developer discounts are not visible.",
        )}
      </p>
    </div>
  );
}

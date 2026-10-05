import { Clock } from "lucide-react";
import { year, classLabel, money, number, percent, signed, titleCase, sep, tone } from "../lib";
import { t } from "../locale";
import type { ClassSummary, Launch, Overview, Profile } from "../types";
import { NameList } from "./Names";

/** Observed prices per class: what resale units were contracted at, what they cost in today’s money,
 * and what the developer asks today for the same class. */
export function ClassCards({ classes }: { classes: ClassSummary[] }) {
  return (
    <div className="class-cards">
      {classes.map((item) => (
        <article key={item.class}>
          <div className="class-head">
            <span className="eyebrow no-rule">{classLabel(item.class)}</span>
            <span className="muted num">{t("{n} listings", { n: number(item.units), count: item.units })}</span>
          </div>
          <strong className="num">
            {money(item.median_asking_ppm, true)}
            <small> / {t("m²")}</small>
          </strong>
          <span className="muted">
            {item.median_contract_year
              ? t("Median resale contract price, signed around {year}", { year: year(item.median_contract_year) })
              : t("Median resale asking price")}
          </span>
          <dl>
            <div>
              <dt>{t("Resale in today’s money / m²")}</dt>
              <dd className="num">{money(item.median_cash_ppm, true)}</dd>
            </div>
            <div>
              <dt>{t("Developer today / m²")}</dt>
              <dd className="num">{item.developer_ppm ? money(item.developer_ppm, true) : t("Not selling")}</dd>
            </div>
            {item.median_gap != null && (
              <div>
                <dt>{t("Resale vs developer")}</dt>
                <dd className={`num ${tone(item.median_gap)}`}>{signed(item.median_gap)}</dd>
              </div>
            )}
          </dl>
        </article>
      ))}
    </div>
  );
}

export function ProfileFacts({ profile }: { profile: Profile }) {
  const finishing = Object.entries(profile.finishing).filter(([level]) => level !== "unknown");
  const finishedTotal = finishing.reduce((sum, [, count]) => sum + count, 0);
  const levels = profile.opportunities;
  const rated = Object.entries(levels).reduce((sum, [level, count]) => (level === "unrated" ? sum : sum + (count ?? 0)), 0);
  const rows: [string, string][] = [
    ["Ready to move in", `${percent(profile.ready_share)}${profile.delivery_known ? "" : ""}`],
    ["Median wait for the rest", profile.median_years_to_delivery ? t("{n} years", { n: number(profile.median_years_to_delivery, 1), count: profile.median_years_to_delivery }) : "—"],
    ["Latest promised delivery", year(profile.latest_delivery_year)],
    ["Listed on installment plans", percent(profile.plan_share)],
    ["Median share still owed", percent(profile.median_remaining_share)],
    ["Median plan length", profile.median_plan_years ? t("{n} years", { n: number(profile.median_plan_years, 1), count: profile.median_plan_years }) : "—"],
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
      "Strong or good opportunities",
      rated
        ? t("{n} of {rated} compared", { n: number((levels.strong ?? 0) + (levels.good ?? 0)), rated: number(rated) })
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
          { n: number(overview.observation_days), count: overview.observation_days },
        )}
      </span>
    </p>
  );
}

/** The developer's current units here against the resale units: the median like-for-like gap. */
export function LaunchPanel({ launch, scope }: { launch: Launch | null; scope: "compound" | "developer" }) {
  if (!launch)
    return (
      <p className="muted">
        {t(
          scope === "compound"
            ? "The developer is not selling units in this compound on Nawy now."
            : "None of this developer’s current units on Nawy could be matched to a resale compound.",
        )}
      </p>
    );
  const gap = launch.median_gap;
  return (
    <div className="launch">
      <div className="launch-lead">
        {gap != null ? (
          <div className={`launch-headline ${tone(gap)}`}>
            <strong className="num">{signed(gap)}</strong>
            <p>
              {t(
                gap < 0
                  ? "The typical resale unit here costs this much less than a similar unit the developer sells today, on the less favourable of listed price and today’s money."
                  : "The typical resale unit here costs this much more than a similar unit the developer sells today, on the less favourable of listed price and today’s money.",
              )}
            </p>
          </div>
        ) : (
          <p className="muted">{t("No resale unit here matches the developer’s units in type, size and finishing yet.")}</p>
        )}
        {launch.median_since_contract != null && (
          <div className="launch-since">
            <strong className="num">{signed(launch.median_since_contract, 1)}</strong>
            <p>{t("A year: how the developer’s list price per m² has moved since the typical seller here signed.")}</p>
          </div>
        )}
      </div>
      <dl className="facts facts-single">
        <div>
          <dt>{t("Developer today / m², as listed")}</dt>
          <dd className="num">{money(launch.median_headline_ppm, true)}</dd>
        </div>
        <div>
          <dt>{t("Developer today / m², today’s money")}</dt>
          <dd className="num">{money(launch.median_cash_ppm, true)}</dd>
        </div>
        <div>
          <dt>{t("Typical developer plan")}</dt>
          <dd className="num">
            {launch.median_plan_years
              ? t("{down} down, {n} years", { down: percent(launch.median_down_share), n: number(launch.median_plan_years, 1) })
              : t("Cash")}
          </dd>
        </div>
        <div>
          <dt>{t("Latest developer delivery")}</dt>
          <dd className="num">{year(launch.latest_delivery_year)}</dd>
        </div>
        <div>
          <dt>{t("Developer units / resale units compared")}</dt>
          <dd className="num">
            {number(launch.units)} / {number(launch.compared)}
          </dd>
        </div>
      </dl>
      {launch.phases.length > 0 && (
        <p className="muted">
          {t("Phases")}: <NameList items={launch.phases} />
        </p>
      )}
      <p className="fineprint">
        {t(
          "Developer prices are its current units on Nawy. Each resale unit is compared with the developer’s units of the same type, finishing and similar size. Developer prices are list prices; negotiated discounts are not visible.",
        )}
      </p>
    </div>
  );
}

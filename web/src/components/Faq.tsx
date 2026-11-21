import { money, nameOf, number, percent, place } from "../lib";
import { t } from "../locale";
import type { ClassSummary, Compound, District } from "../types";

/** The questions buyers search for, answered from the live numbers. The server publishes the same
 * questions and answers as structured data for search engines (src/qayem/seo.py). */
type Item = [string, string];

const classPlural: Record<string, string> = { apartment: "apartments", chalet: "chalets", house: "villas and houses" };
const primary = (classes: ClassSummary[]) => [...classes].sort((a, b) => b.units - a.units)[0];
const gapText = (gap: number, against: string) =>
  Math.abs(gap) < 0.005
    ? t("priced like {against}", { against })
    : t(gap < 0 ? "{gap} cheaper than {against}" : "{gap} dearer than {against}", { gap: percent(Math.abs(gap)), against });

export function compoundFaq(compound: Compound): Item[] {
  const name = nameOf(compound)!;
  const developer = nameOf(compound.developer) ?? t("the developer");
  const items: Item[] = [];
  const main = primary(compound.classes);
  if (main?.median_asking_ppm)
    items.push([
      t("What does a square metre cost on the resale market in {name}?", { name }),
      t("Resale {kind} in {name} have a median contract price of {ppm} per m² ({cash} in today’s money, plans discounted), from {n} listings now.", {
        kind: t(classPlural[main.class] ?? "units"),
        name,
        ppm: money(main.median_asking_ppm, true),
        cash: money(main.median_cash_ppm, true),
        n: number(main.units),
      }),
    ]);
  if (compound.launch?.median_gap != null)
    items.push([
      t("Is resale in {name} cheaper than buying from {developer} today?", { name, developer }),
      t("The typical resale unit in {name} is {gap}, on the less favourable of listed price and today’s money, across {n} units of the same type, finishing and size.", {
        name,
        gap: gapText(compound.launch.median_gap, t("a similar unit {developer} sells today", { developer })),
        n: number(compound.launch.compared),
      }),
    ]);
  const rated = Object.entries(compound.opportunities).reduce((sum, [level, n]) => (level === "unrated" ? sum : sum + (n ?? 0)), 0);
  if (rated)
    items.push([
      t("How many real resale opportunities are there in {name} now?", { name }),
      t("{n} of {rated} compared units are clearly cheaper than what can be bought today (the developer’s price and similar listed units).", {
        n: number(compound.good_count),
        rated: number(rated),
      }),
    ]);
  const history = compound.history;
  if (history && compound.units)
    items.push([
      t("How fast do units sell in {name}?", { name }),
      t("{n} listings left the resale market in {name} in the last 30 days ({share} of the stock). Leaving can mean sold or withdrawn.", {
        n: number(history.delisted_30d),
        name,
        share: percent(history.turnover_30d, 1),
      }),
    ]);
  if (compound.ready_share != null)
    items.push([
      t("Are resale units in {name} ready to move in?", { name }),
      t("{share} of the resale units listed in {name} are ready to move in.", { share: percent(compound.ready_share), name }),
    ]);
  return items;
}

export function districtFaq(district: District): Item[] {
  const name = place(district.name)!;
  const items: Item[] = [];
  const main = primary(district.classes);
  if (main?.median_asking_ppm)
    items.push([
      t("What does a square metre cost on the resale market in {name}?", { name }),
      t("Resale {kind} in {name} have a median contract price of {ppm} per m², from {n} listings in {compounds} compounds.", {
        kind: t(classPlural[main.class] ?? "units"),
        name,
        ppm: money(main.median_asking_ppm, true),
        n: number(main.units),
        compounds: number(district.compound_count),
      }),
    ]);
  const below = (district.compounds ?? []).filter((c) => c.median_gap != null).sort((a, b) => a.median_gap! - b.median_gap!).slice(0, 3);
  if (below.length)
    items.push([
      t("Which compounds in {name} are cheapest on resale against the developer?", { name }),
      t("Furthest below the developer’s price today: {list}.", {
        list: below.map((c) => `${nameOf(c)} (${gapText(c.median_gap!, t("the developer"))})`).join(t(", ")),
      }),
    ]);
  const good = (district.opportunities.strong ?? 0) + (district.opportunities.good ?? 0);
  const rated = Object.entries(district.opportunities).reduce((sum, [level, n]) => (level === "unrated" ? sum : sum + (n ?? 0)), 0);
  if (rated)
    items.push([
      t("How many resale opportunities are there in {name} now?", { name }),
      t("{n} of {rated} compared units in {name} are clearly cheaper than the developer’s price and similar units.", {
        n: number(good),
        rated: number(rated),
        name,
      }),
    ]);
  if (district.history)
    items.push([
      t("How fast do resale units sell in {name}?", { name }),
      t("{n} listings left in the last 30 days ({share} of the stock).", {
        n: number(district.history.delisted_30d),
        share: percent(district.history.turnover_30d, 1),
      }),
    ]);
  return items;
}

export function Faq({ items }: { items: Item[] }) {
  if (!items.length) return null;
  return (
    <section className="section-tight faq" aria-labelledby="faq-heading">
      <span className="eyebrow">{t("Questions")}</span>
      <h2 className="display section-title" id="faq-heading">
        {t("What buyers ask")}
      </h2>
      <dl>
        {items.map(([question, answer]) => (
          <div key={question}>
            <dt>{question}</dt>
            <dd>{answer}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

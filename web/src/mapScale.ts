/** Colours for the price map, shared by the map layers, its legend and the summary card. */
import type { GuideRow, PropertyClass } from "./types";

export type Measure = "price" | "gap";

/** The lapis ramp: dearer is deeper. */
export const PRICE_COLOURS = ["#dfe6ff", "#b3c2ff", "#7f97ff", "#3f61ee", "#1b3fd0", "#0d1c66"];
/** Resale cheaper than new (turquoise) through the same (stone) to dearer (carnelian). */
export const GAP_COLOURS = ["#076e68", "#3bb5ab", "#a8e0da", "#e6e3d8", "#f6b8a0", "#e8562b", "#a53413"];
export const GAP_BREAKS = [-0.2, -0.1, -0.03, 0.03, 0.1, 0.2];
export const NO_DATA = "#d3d5de";

export const rowFor = (classes: GuideRow[] | undefined, headline: GuideRow | null | undefined, cls: PropertyClass | "headline") =>
  cls === "headline" ? (headline ?? null) : (classes?.find((row) => row.class === cls) ?? null);

/** Quantile breaks for the prices on screen, rounded to a readable step. */
export function priceBreaks(values: number[]) {
  const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (sorted.length < 2) return sorted.length ? [sorted[0]] : [];
  const bins = PRICE_COLOURS.length;
  const breaks: number[] = [];
  for (let i = 1; i < bins; i++) {
    const value = sorted[Math.min(sorted.length - 1, Math.floor((i / bins) * sorted.length))];
    const step = value >= 100_000 ? 10_000 : 5_000;
    const rounded = Math.round(value / step) * step;
    if (!breaks.length || rounded > breaks[breaks.length - 1]) breaks.push(rounded);
  }
  return breaks;
}

export function colourFor(value: number | null | undefined, measure: Measure, breaks: number[]) {
  if (value == null) return NO_DATA;
  const [colours, cuts] = measure === "price" ? [PRICE_COLOURS, breaks] : [GAP_COLOURS, GAP_BREAKS];
  let index = 0;
  while (index < cuts.length && value >= cuts[index]) index++;
  return colours[Math.min(index, colours.length - 1)];
}

export const valueOf = (row: GuideRow | null, measure: Measure) => (row ? (measure === "price" ? row.median_ppm : row.resale_vs_new) : null);

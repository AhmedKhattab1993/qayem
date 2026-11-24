# Qayem brand: the square metre

Adopted 2026-11-24, replacing "The Scale" (dark green, brass, a balance). It follows the strategy of
2026-11-22: Qayem is Egypt's property price guide, not a tool that weighs single listings. The system
lives in `web/src/styles/base.css` (tokens) and `web/src/components/Brand.tsx` (the mark).

## The idea

Everything Qayem publishes is one thing: **a price for one square metre, in one place, on one date**.
So the square is the unit of the brand. The mark is built from squares, the hero is a mosaic of square
tiles, corners stay crisp, and sections are separated by rules, not by shadows.

The test for any new screen: does it give the number, the place, the date and the source before
anything else?

## The mark

The ق of قيّم drawn in square Kufic, the lettering of Cairo's stone inscriptions, on a 48-unit grid
with 5-unit strokes.

- Its **eye** is a single square: one square metre.
- Its **two dots** are the two prices the guide always reads together, resale and new. They are gold.
- It sits on a lapis tile (`rx` 5 of 48). On lapis grounds the tile is white and the letter lapis.
- Wordmark: «قيّم» in Alexandria ExtraBold in Arabic, "Qayem" in English. One at a time, never both.
- Files: `web/public/favicon.svg`, `web/public/apple-touch-icon.png`, `web/public/og-default.png`.
  The two PNGs are rendered from `docs/brand/*.html` by `node web/tests/render-brand.mjs
  "$PWD/docs/brand/og-card.html" "$PWD/docs/brand/touch-icon.html"`.

Do not rotate it, outline it, round it further, recolour the dots, or set it on a photo.

## Colour

The stones of an Egyptian pectoral, each with one job. A colour is never used for a second meaning.

| Token | Hex | Job |
|---|---|---|
| `--lapis` | `#1b3fd0` | The brand: the hero, primary buttons, links, the current page |
| `--lapis-deep`, `--lapis-night` | `#132a8f`, `#0a1445` | Dearest steps of the price ramp, the footer |
| `--lapis-soft`, `--lapis-tint` | `#e4eaff`, `#f1f4ff` | Selected and hovered surfaces |
| `--turq` | `#076e68` | Cheaper: resale below new, below the guide, high confidence |
| `--carn` | `#b23815` | Dearer: resale above new, above the guide, errors |
| `--gold` | `#f6b21b` | Attention: the mark's dots, the main action on lapis, medium confidence |
| `--paper`, `--surface` | `#f7f6f1`, `#ffffff` | Limestone page, white cards and page heads |
| `--ink` … `--ink-4` | `#0b1020` … `#656b83` | Basalt text, from headings to captions |

**The price ramp** (cheapest to dearest): `#dfe6ff #b3c2ff #7f97ff #3f61ee #1b3fd0 #0d1c66`. It colours
the map (`web/src/mapScale.ts`), the hero mosaic and the rule at the top of the footer. Resale against
new uses the diverging turquoise–stone–carnelian scale in the same file.

Text on lapis is white; body text on paper is ink. All pairs used for text pass WCAG AA.

## Type

- **Alexandria** (variable, Arabic and Latin, designed in Egypt): headings, figures that are the
  answer, the wordmark. Weights 600–800; Latin headings are set tight (−0.025em to −0.04em), Arabic
  never tracked.
- **Readex Pro** (variable, Arabic and Latin): text, labels, tables.
- Figures use tabular numerals (`.num`). No italics in either script: emphasis is the lapis colour.

## Shape and motion

- Radii: 3, 6 and 10 px. Nothing is a pill.
- Rules: a 2 px ink line opens a table or a list; hairlines separate rows.
- The grid: a 48 px square module drawn in faint lines behind the hero, the methodology head and the
  index card.
- A label (`.eyebrow`) is led by an 8 px lapis square; confidence tags by a 7 px square.
- Motion is short and functional: a page fades up in 0.5 s, tiles lift 3 px on hover, the loading
  state counts four squares. `prefers-reduced-motion` turns all of it off.

## The signature components

- **Mosaic** (home hero): the busiest districts as square tiles shaded by price per m².
- **Range bar** (`RangeBar` in `Guide.tsx`): the middle half of asking prices on a shared scale, the
  median marked. On the home board and in every segment table.
- **Answer block** (`.guide-answer`): the first sentence of a guide page, behind a lapis rule.
- **Diverging bars**: cheaper to one side in turquoise, dearer to the other in carnelian.

## Voice

The number first, then the place, the date and the source. Plain words a buyer uses («سعر المتر»,
"asking price"), never "fair value". Say what a figure is not: these are asking prices, not sales.
The line: **«سعر المتر، في أي مكان في مصر.»** / "The price of a square metre, anywhere in Egypt."

## Structure of the site

Built from the buyer's four questions (STRATEGY.md, section 3), not from the database's tables.

| Where | What |
|---|---|
| Header | Price map · Price guide · Qayem Index · Articles, then search, watchlist, compare, currency, language and one action: **Check a price** |
| Price guide | One section with three doors (tabs): Districts, Compounds, Developers |
| Home | Hero (search and the mosaic) → four questions → the price board → resale against the developer → the index and articles → how the guide is made → check a price |
| Phones | Tab bar: Map, Guide, **Check**, Index, Saved. The menu button lists every page in the footer's four groups |
| Footer | Prices · Tools · Read · About Qayem |

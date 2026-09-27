# Description-extraction benchmark (2026-09-27)

Goal: cheapest reliable `codex exec` setup (gpt-6 models only) for filling
missing listing fields from descriptions.

## Data

- **dev** (`sample.jsonl`, 150 listings: 90 OpenSooq, 40 AqarExit, 20 Semsar):
  used for tuning prompt, model, effort, format and batch size.
- **test** (`sample_test.jsonl`, 200 listings: 160 OpenSooq incl. 40 with
  payment wording, 40 AqarExit missing plan length): held out, only used to
  confirm finalists.
- Gold (`gold.json`, `gold_test.json`): two independent labelers (gpt-6-astra
  high + Claude) under the same spec; 96-98% cell agreement; every
  disagreement adjudicated by hand (`adjudicated*.json`). Genuinely ambiguous
  cells are "optional" (null or either value accepted). Astra's own scores are
  biased upward because it is one of the two labelers.
- "applied" = only cells missing in the database, i.e. what production fills.

## Findings

1. **Per-call overhead dominates one-listing calls.** Default `codex exec`
   sends ~11.9k input tokens before the prompt. Replacing the instructions
   (`-c model_instructions_file=...`), disabling all optional features and
   `-c web_search="disabled"` brings it to ~2.5k.
2. **Batching improves accuracy, not only cost.** One listing per call was the
   worst setting (19 errors vs 6 at batch 10 on the same model) at 8x the
   input tokens. gpt-6-sol is flat from batch 10 to 40.
3. **Prompt spec matters more than model effort.** spec_v2 (explicit rules for
   resale, multi-unit, "starting from"/"up to", districts vs compounds,
   landmark companies, title/description conflicts) cut errors 3-4x.
   Reasoning effort changed little for gpt-6-luna at low/medium.
4. **Sparse output** (only stated fields) cuts output tokens ~45-75% with no
   accuracy loss. Evidence quotes help weak models, not gpt-6-sol.
5. **gpt-6-luna is not reliable enough**: 20-27 errors/150 at low/medium; at
   high effort 1 error on dev but 13/200 on test (compound = "ساكن وعايش",
   contract total as price), and 7x gpt-6-sol's output tokens.
6. Run-to-run noise is about ±3 errors per 200 listings (3.5% of non-null cells
   differ between identical runs); two-run agreement filtering removed 1 error
   for 2x cost — not worth it.
7. Batch calls can silently return fewer listings (one call returned 1 of 10):
   production must verify ids and retry missing ones.

## Held-out test results (13 core fields, 200 listings)

| setup | errors | precision | recall | applied errors / P | tokens per listing (in / uncached / out+reasoning) |
|---|---|---|---|---|---|
| **gpt-6-sol low, v2, sparse, batch 40** | 6 (rep: 9) | 99.0% | 97.2% | 3 / 98.3% | 224 / 110 / 43 |
| gpt-6-sol low, v2, sparse, batch 20 | 7 | 98.9% | 96.5% | 4 / 97.7% | 368 / 197 / 48 |
| gpt-6-sol medium, v2, sparse, batch 10 | 4 | 99.4% | 98.0% | 2 / 98.9% | 655 / 266 / 148 |
| gpt-6-luna high, v2, evidence, sparse, batch 5 | 13 | 97.9% | 95.7% | 5 / 97.1% | 1232 / 332 / 333 |

The three "applied" errors of the recommended setup are two cross-script
spellings of the right compound (`SMART CITY - TMG` = سمارت سيتي,
`el masyaf` = المصيف) and one borderline down payment.

## Recommendation

gpt-6-sol, reasoning effort low, `spec_v2.md` as model instructions, sparse
JSON schema without evidence, 40 listings per call, lean flags. Use medium
effort at batch 10 only if the extra ~3x tokens are worth ~2 fewer errors per
200 listings (within noise).

Reproduce: `python bench.py run gpt-6-sol low v2 40 --sparse --fieldset core`
then `python bench.py score runs/<tag> [--applied] [--fields] [--errors]`
(`BENCH_SET=test` for the held-out set).

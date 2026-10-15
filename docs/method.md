---
description: How jev-codebook turns a codebook into Jev questions, how decisions and the review band work, what the reliability statistics mean, and how to calibrate thresholds honestly.
---

# Method

## From codebook to questions

Each code becomes one yes/no (`noul`) question in multi mode. The instructions are fixed and direct, `Does this response express the code '<label>'?`, because Jev reads literally: a negated or two-part instruction ("Does it praise the light but not the price?") is the most common way to get wrong answers. Your `definition` and `include_examples` become the `true` criterion, your `exclude_examples` the `false` criterion. Good definitions describe what a response *says*, in one sentence, without "not" or "unless"; if you need an exclusion, put it in `exclude_examples` as a concrete sentence.

All codes about one response go in one request so the model judges them in parallel over the same small state. Beyond 40 codes the request is chunked; the cache key and `request_id` are per chunk.

Single mode is for mutually exclusive codes (one choice over codes plus `none_of_these`). Multi-mode probabilities are independent judgments, not a distribution: p(code A) and p(code B) can both be 0.9, and p(A) + p(not A) is not 1.

## Decisions and the review band

Assignment happens in code from `threshold` (per code) and `review_band` (codebook-wide):

| p for a code | multi mode |
| --- | --- |
| p >= threshold | assigned |
| low <= p < high | row flagged `review` |
| p < low | ignored |

With the defaults (threshold 0.7, band [0.4, 0.7)) an item is either confidently in, confidently out, or in the queue. If `tune` lowers a threshold to 0.55, items between 0.55 and 0.7 are assigned *and* flagged, which is the intended behavior: assigned, but worth a look.

In single mode the chosen option is assigned when its probability clears that code's threshold; the row is flagged when the winning probability is under the band's upper bound (the model did not clearly prefer one option, `none_of_these` included).

## Reliability statistics

`agreement` treats the model as a second coder and compares it to your human file over the ids both contain, per code:

- **Percent agreement**: share of items where both say the same. Inflated by rare codes (agreeing on "absent" is easy), hence the next two.
- **Cohen's kappa**: agreement corrected for chance using each coder's own marginal rates. Verified against the classic 2x2 table (20/5/10/15 gives 0.4).
- **Krippendorff's alpha (nominal, two coders)**: chance correction from the pooled distribution with the small-sample `(n - 1)` correction, computed from the coincidence matrix. Close to kappa on large samples; reported because many qualitative-research venues ask for it.
- **Precision, recall, F1** with **Wilson 95% intervals** on precision (over items the model assigned) and recall (over items the human assigned). With 8 human-positive items a recall of 0.875 has an interval of roughly [0.53, 0.98]; the interval is the honest part of the number.

None of these is a benchmark of Jev. They are what the tool shows *you* on *your* sample, with the codebook *you* wrote.

## Calibrating thresholds without fooling yourself

`tune` shuffles the matched ids with a fixed seed (default 42), keeps 60% for tuning and 40% as holdout, sweeps thresholds 0.05..0.95 per code on the tuning rows only (maximizing F1, ties toward the current threshold), then reports holdout metrics at the current and the tuned thresholds. Only the holdout numbers tell you what to expect on new data; the tuning F1 is optimistic by construction. If the holdout row count per code is tiny, the Wilson intervals will say so.

Practical sequence: code a pilot of 150-300 responses, have a human code them blind, run `agreement`, fix the codebook where kappa is poor (usually a vague definition), re-code (the cache makes re-runs of unchanged text free, but a changed definition changes the questions and therefore the key), then `tune`, then code the full set with the tuned codebook and work the review queue.

## Limits

- Text should be in English for best accuracy; other languages work with lower accuracy.
- Keep responses reasonably short. Long interview transcripts should be split into excerpts before coding.
- The model does not count, compare numbers or dates reliably; codes like "mentions more than two problems" belong in code, not in the codebook.
- Adversarial or instruction-like text inside a response can sway the judgment; the review band is the mitigation.

## Evaluation input preflight / Prévalidation / Validación previa

EN: Coded imports now reject duplicate/empty IDs or headers, nonfinite/out-of-range probabilities and nonbinary assignments. Human per-code columns require explicit yes/no labels; blanks or unknown words are not silently counted as negatives. A blank `codes` list still explicitly means no selected code. Tune/holdout needs at least two distinct IDs and keeps both splits nonempty. These guards prevent malformed inputs from inflating an agreement calculation; tiny or biased samples still cannot establish general quality.

FR : Les imports codés refusent désormais ID/en-têtes dupliqués ou vides, probabilités non finies/hors limites et annotations non binaires. Les colonnes humaines exigent un oui/non explicite ; blancs ou mots inconnus ne deviennent plus des négatifs. Une liste `codes` vide signifie toujours explicitement aucun code. Tune/holdout exige deux ID distincts et garde les deux parties non vides. Ces gardes empêchent une entrée mal formée de fausser l’accord ; un échantillon minuscule ou biaisé ne prouve toujours pas une qualité générale.

ES: Importaciones codificadas rechazan ID/cabeceras duplicados o vacíos, probabilidades no finitas/fuera de rango y anotaciones no binarias. Columnas humanas exigen sí/no explícito; blancos o palabras desconocidas no cuentan como negativos. Una lista `codes` vacía sigue significando ningún código. Tune/holdout exige dos ID distintos y mantiene ambas partes no vacías. Evita cálculos de acuerdo sobre entradas incorrectas; muestras pequeñas o sesgadas no establecen calidad general.

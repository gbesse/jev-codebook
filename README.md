# jev-codebook

**Apply a qualitative codebook to open-ended survey answers, reviews or interview excerpts with Jev, and get per-code probabilities, a review queue, frequency tables with confidence intervals and inter-rater reliability against your human coders.**

[![Tests](https://github.com/gbesse/jev-codebook/actions/workflows/test.yml/badge.svg)](https://github.com/gbesse/jev-codebook/actions/workflows/test.yml) ![MIT](https://img.shields.io/badge/license-MIT-blue) ![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![Public alpha](https://img.shields.io/badge/status-public%20alpha-orange)

Jev (TypeSafe AI's "System One" model) does not generate text: you send a state and typed questions, it returns probabilities. That fits qualitative coding well: each code becomes one yes/no question with your definition and examples as criteria, and every decision (assign, review, ignore) stays in code with thresholds you can tune on your own labeled data. Runtime is Python 3.11+ standard library only.

## Quick start (offline, 30 seconds, no key)

```sh
git clone https://github.com/gbesse/jev-codebook.git
cd jev-codebook
python -m examples.offline_demo
```

The demo codes 40 synthetic responses about a fictional desk lamp with a 6-code codebook, using a fake provider whose probabilities come from `examples/fixtures.json`. It prints the coded table, the review queue, the agreement table against a synthetic "human" file and a threshold tuning pass. **All numbers in the demo are synthetic; they show the mechanics, not Jev's accuracy.**

The same flow through the CLI:

```sh
pip install -e .            # or: export PYTHONPATH=src
jev-codebook validate examples/codebook.json
jev-codebook estimate examples/responses.csv --codebook examples/codebook.json
jev-codebook code examples/responses.csv --codebook examples/codebook.json --out coded.csv --review review.csv --cache .jev-cache.json --fake examples/fixtures.json
jev-codebook agreement coded.csv examples/human.csv --codebook examples/codebook.json
jev-codebook tune coded.csv examples/human.csv --codebook examples/codebook.json --write-codebook tuned.json
jev-codebook report coded.csv --codebook examples/codebook.json
```

## Call real Jev

```sh
export TYPESAFE_API_KEY=...   # requests are paid and go to https://api.typesafe.ai/v1/systemone
jev-codebook estimate responses.csv --codebook codebook.json
jev-codebook code responses.csv --codebook codebook.json --out coded.csv --review review.csv --cache .jev-cache.json
```

Drop `--fake` and the client pins `jev-1.13.0`, checks that the returned model matches, retries only on 429/529 and network errors (bounded, jittered, honoring `Retry-After`), refuses redirects, and never prints the key. `--concurrency` (default 8) and `--rate-limit` (default 1,000 requests/min, under the published 1,200) bound the load. `--cache` stores validated answers by sha256 of the exact request, so re-running after editing thresholds or resuming an interrupted batch costs nothing; errors are never cached. `--out` is also the resume journal: ids already present are skipped.

The official SDKs (`typesafe-sdk` on PyPI, `@typesafe-ai/sdk` on npm) are an alternative to the built-in client if you already use them; this repository ships its own so you install nothing.

### Cost, as an estimate

Price list on 21 Sept 2026: USD 0.042 per million input tokens, output free. The response text alone is small: 10,000 answers of ~150 tokens are ~1.5M tokens, about USD 0.06. The codebook questions travel with every request, and for the 6-code example with definitions and examples they weigh ~800 tokens per request, so the same 10,000 answers come to roughly 8M tokens, about USD 0.35. `jev-codebook estimate` prints the number for your files (chars/4 heuristic). Both figures are estimates from the published price, not a bill.

## Input and output

- Responses: CSV (default) or JSONL (`.jsonl`/`.ndjson`) with an `id` and a `text` column (`--id-column`, `--text-column`). Blank texts are skipped and counted; duplicate ids are an error.
- Codebook: JSON, see `examples/codebook.json`:

```json
{
  "name": "orbit-lamp-feedback", "version": "1.0", "language": "en", "mode": "multi",
  "review_band": [0.4, 0.7],
  "codes": [
    { "id": "price_concern", "label": "Price concern",
      "definition": "The response says the lamp is expensive, overpriced or questions whether it is worth the money.",
      "include_examples": ["Too expensive for a lamp."], "exclude_examples": ["Worth every cent."],
      "threshold": 0.7 }
  ]
}
```

- Coded CSV: `id, text, <code>... (0/1), p_<code>... , review (0/1), request_id`. `request_id` is the first 12 hex chars of the cache key of each request (joined with `+` when a response needed several).
- Human labels: `id` plus either one 0/1 column per code or a `codes` column with `;`-separated ids.

## Library use

```python
from jev_codebook import JevClient, FakeJev, load_codebook, code_responses
from jev_codebook.cache import ExactInputCache
from jev_codebook.datafiles import read_responses

codebook = load_codebook("codebook.json")
responses = read_responses("responses.csv").responses
provider = JevClient()                      # reads TYPESAFE_API_KEY; or FakeJev.from_file("fixtures.json")
summary = code_responses(responses, codebook, provider, cache=ExactInputCache(".jev-cache.json"), concurrency=8)
for row in summary.rows:
    print(row.id, row.assigned, row.probabilities, row.review)
print(summary.input_tokens, summary.estimated_cost_usd)
```

`jev_codebook.stats` exposes `wilson_interval`, `cohen_kappa`, `krippendorff_alpha_nominal`, `percent_agreement` and `binary_metrics`; `jev_codebook.agreement` exposes `compute_agreement`, `tune_thresholds` and `split_ids`.

## How it decides

- State is `{"response": "<text>"}` and nothing else. Ids, timestamps and metadata are left out on purpose: Jev's accuracy drops with irrelevant state.
- **Multi mode** (a response can carry several codes): one `noul` question per code, all in **one request per response** (fan-out), chunked at 40 codes per request. Instructions: `Does this response express the code '<label>'?`. Criteria: `true: { what: <definition>, examples: <include_examples> }`, `false: { what: "The response does not express '<label>': it is about something else, or only mentions a related topic without expressing it.", examples: <exclude_examples> }`.
- **Single mode** (exactly one code or none): one `choice` question `Which single code best describes what this response expresses?` over the codes plus `none_of_these`.
- Assignment (code-owned): multi mode assigns a code when `p >= threshold` (default 0.7 per code); the row is flagged `review` when any code's `p` falls in `review_band` `[0.4, 0.7)`. Single mode assigns the chosen option when its probability clears that code's threshold and flags `review` when the winning probability is below the band's upper bound.
- `agreement` computes per code: percent agreement, Cohen's kappa, Krippendorff's alpha (nominal, two coders), precision, recall and F1 with Wilson 95% intervals, over the ids present in both files.
- `tune` splits the matched ids 60/40 at random with a fixed seed (`--seed 42`), picks each code's threshold by F1 on the 60% tuning split only (candidates 0.05 to 0.95), and reports holdout metrics at the current and tuned thresholds. The holdout labels never enter the choice; a test enforces it.
- `report` prints frequencies with Wilson 95% intervals, a co-occurrence matrix and the rows closest to their decision boundary.

Thresholds and the review band are illustrative defaults. Calibrate them on your own labeled sample with `tune`; they are not guarantees. Details in [docs/method.md](docs/method.md).

## Boundaries

- It does not write, merge or discover codes; it applies the codebook you wrote. Codebook quality drives results: direct definitions, no negations, concrete examples.
- Jev reads instructions literally, cannot count, compares numbers and dates poorly, and is weakest on long irrelevant context and adversarial text (see the model notes linked below). Keep responses short and codes explicit; do arithmetic in code.
- p(A) and p(not A) do not sum to 1 across questions, so multi-mode probabilities are independent judgments, not a distribution over codes. Use single mode when codes are mutually exclusive.
- English gives the best accuracy; other languages work with lower accuracy. `language` in the codebook is informational.
- No live benchmark is claimed. The fixture probabilities are synthetic. Whatever accuracy you get is what `agreement` shows on your own human-coded sample.
- `--fake` is for tests and demos only; the review queue is the intended human-in-the-loop step, not an optional extra.

## Validation

```sh
pip install -r requirements-dev.txt          # editable install, no other dependencies
python -m compileall -q src tests
python -m unittest discover -s tests
python -m examples.offline_demo
```

CI (`.github/workflows/test.yml`) runs exactly these on Python 3.11 and 3.13. Tests cover codebook validation errors, question construction, chunking beyond 40 codes, CSV round trips, resume, cache hits, kappa/Wilson/alpha against textbook values, tune/holdout separation, the fake provider path, client validation on malformed responses and retries on 429/529. Nothing in CI calls the API.

Opt-in live check (2 paid requests with one synthetic sentence, only when the key is set): `TYPESAFE_API_KEY=... python scripts/live_smoke.py`.

## Related projects

- [Question Forge](https://github.com/gbesse/question-forge): write and test Jev questions before putting them in a codebook.
- [DecisionPacks](https://github.com/gbesse/decisionpacks): versioned decision rules over Jev answers, if the coded output feeds a downstream workflow.
- [Autonomy Meter](https://github.com/gbesse/autonomy-meter): measuring how much of a decision pipeline can run without review.

Independent project; not affiliated with TypeSafe AI. API reference: https://docs.typesafe.ai/api. Model notes: https://docs.typesafe.ai/model-jaggedness/jev-1.13.

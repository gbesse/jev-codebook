# AI change log

This file records the purpose and technical decisions of agent-authored changes.

## 2026-09-21 — v0.1.0, initial release

Purpose: qualitative coding at scale with Jev (launch wave 3, repository 6 of the shared spec).

Key decisions:
- Stdlib-only runtime. `urllib.request` with explicit timeout and a redirect-refusing opener; retries only on 429/529/network, bounded with jittered exponential backoff and `Retry-After`; strict validation of `model`, answer types, probability ranges and choice keys. Errors are never cached or swallowed.
- State is the response text alone (`{"response": text}`); ids and metadata are excluded because irrelevant state lowers Jev accuracy. Multi mode fans out one noul per code in one request, chunked at 40 codes; single mode is one choice plus `none_of_these`.
- All decisions (assign, review) are code-owned from per-code thresholds and a review band, so re-deciding after `tune` needs no new requests. `--out` doubles as the resume journal; the exact-input cache is a JSON file written atomically.
- Statistics (Wilson, Cohen's kappa, Krippendorff's alpha nominal via coincidence matrix, precision/recall/F1) implemented by hand and tested against textbook values (kappa 0.4 on the 20/5/10/15 table, Wilson 0/10 upper 0.2775, alpha 0.64 hand example).
- `tune` uses a seeded random 60/40 split; a test flips every holdout label and asserts the chosen thresholds do not move.
- `FakeJev` implements the same `ask` contract with synthetic probabilities keyed by exact response text; the demo and all tests are offline.

Verified locally (Python 3.11.3): `python -m compileall -q src tests`, `python -m unittest discover -s tests` (72 tests), `python -m examples.offline_demo`, editable install and `jev-codebook --version`. Not verified: any live Jev call (`scripts/live_smoke.py` was written but not run), Python 3.13 (CI only).

# Purpose: Offline demonstration: code 40 synthetic responses with the fake provider, print the coded table, the review queue and agreement against synthetic human labels.
"""Run with ``python -m examples.offline_demo`` from the repository root. No key, no network.

The probabilities come from ``examples/fixtures.json`` and are synthetic;
they show the mechanics of the tool, not Jev's accuracy.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A fresh clone has not installed the package; putting src/ on the path lets the 30-second quick start run as-is.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from jev_codebook.agreement import compute_agreement, tune_thresholds  # noqa: E402
from jev_codebook.cache import ExactInputCache  # noqa: E402
from jev_codebook.cli import main  # noqa: E402
from jev_codebook.client import FakeJev  # noqa: E402
from jev_codebook.codebook import load_codebook  # noqa: E402
from jev_codebook.coder import code_responses, estimate_run  # noqa: E402
from jev_codebook.datafiles import read_coded, read_human_labels, read_responses  # noqa: E402
from jev_codebook.stats import fmt  # noqa: E402

EXAMPLES = ROOT / "examples"


def run() -> int:
    codebook = load_codebook(str(EXAMPLES / "codebook.json"))
    data = read_responses(str(EXAMPLES / "responses.csv"))
    provider = FakeJev.from_file(str(EXAMPLES / "fixtures.json"))
    estimate = estimate_run(data.responses, codebook)
    print(f"codebook '{codebook.name}' v{codebook.version}: {len(codebook.codes)} codes, mode {codebook.mode}")
    print(f"{len(data.responses)} responses ({data.skipped_blank} blank skipped); estimate: {estimate.requests} requests, ~{estimate.input_tokens:,} tokens, ~USD {estimate.estimated_cost_usd:.4f} (published price list)")

    with tempfile.TemporaryDirectory(prefix="jev-codebook-demo-") as tmp:
        cache = ExactInputCache(os.path.join(tmp, "cache.json"))
        summary = code_responses(data.responses, codebook, provider, cache=cache, concurrency=4)
        # Second pass through the same cache proves that re-runs are free.
        again = code_responses(data.responses, codebook, provider, cache=cache, concurrency=4)
        print(f"first pass: {summary.live_requests} live requests (fake provider, synthetic probabilities); second pass: {again.live_requests} live, {again.cached_requests} cached")

        print("\ncoded table (1 = assigned; p = synthetic probability):")
        ids = codebook.code_ids
        print(f"{'id':<5}{'review':<7}" + "".join(f"{c[:12]:>14}" for c in ids) + "  text")
        for row in summary.rows:
            cells = "".join(f"{row.assigned[c]} ({row.probabilities[c]:.2f})".rjust(14) for c in ids)
            print(f"{row.id:<5}{'*' if row.review else '':<7}{cells}  {row.text[:48]}")

        review = [r for r in summary.rows if r.review]
        print(f"\nreview queue ({len(review)} rows inside the band {list(codebook.review_band)}):")
        for row in review:
            borderline = ", ".join(f"{c}={row.probabilities[c]:.2f}" for c in ids if codebook.review_band[0] <= row.probabilities[c] < codebook.review_band[1])
            print(f"  {row.id}: {borderline}  | {row.text[:60]}")

        # Round-trip through the CLI so the demo exercises the same path a user runs.
        out = os.path.join(tmp, "coded.csv")
        sys.stdout.flush()  # keep the CLI's stderr notes in reading order
        rc = main(["code", str(EXAMPLES / "responses.csv"), "--codebook", str(EXAMPLES / "codebook.json"), "--out", out, "--fake", str(EXAMPLES / "fixtures.json"), "--concurrency", "4"])
        if rc != 0:
            raise SystemExit("cli code failed")
        coded = read_coded(out)
        human = read_human_labels(str(EXAMPLES / "human.csv"), ids)
        agreement = compute_agreement(coded, human, codebook)
        print(f"\nagreement vs synthetic human labels ({agreement.n_matched} matched, exact-match rate {fmt(agreement.exact_match_rate)}):")
        print(f"{'code':<20}{'agree%':>8}{'kappa':>7}{'alpha':>7}{'prec':>6}{'[95% CI]':>15}{'recall':>8}{'[95% CI]':>15}{'F1':>6}")
        for code, m in agreement.per_code.items():
            print(f"{code:<20}{fmt(m.accuracy * 100, 1):>8}{fmt(m.kappa):>7}{fmt(m.alpha):>7}{fmt(m.precision, 2):>6}{'[' + fmt(m.precision_ci[0], 2) + ', ' + fmt(m.precision_ci[1], 2) + ']':>15}{fmt(m.recall, 2):>8}{'[' + fmt(m.recall_ci[0], 2) + ', ' + fmt(m.recall_ci[1], 2) + ']':>15}{fmt(m.f1, 2):>6}")

        tuned = tune_thresholds(coded, human, codebook, seed=42)
        print(f"\ntune (seed 42, {tuned.n_tune} tuning / {tuned.n_holdout} holdout rows): thresholds chosen on the tuning split only")
        for t in tuned.per_code:
            print(f"  {t.code:<20} {t.current_threshold:.2f} -> {t.tuned_threshold:.2f}   holdout F1 {fmt(t.holdout_current.f1, 2)} -> {fmt(t.holdout_tuned.f1, 2)}")
    print("\nAll numbers above are synthetic (fake provider). Set TYPESAFE_API_KEY and drop --fake to code with Jev.")
    return 0


if __name__ == "__main__":
    sys.exit(run())

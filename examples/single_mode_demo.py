"""Run a fictional, offline single-label support triage example.

The probabilities are synthetic fixtures, not measured Jev output.
Run ``python -m examples.single_mode_demo`` from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from jev_codebook.client import FakeJev  # noqa: E402
from jev_codebook.codebook import load_codebook  # noqa: E402
from jev_codebook.coder import code_responses  # noqa: E402
from jev_codebook.datafiles import read_responses  # noqa: E402

EXAMPLES = ROOT / "examples"


def run() -> int:
    codebook = load_codebook(str(EXAMPLES / "support_codebook.json"))
    responses = read_responses(str(EXAMPLES / "support_responses.csv")).responses
    provider = FakeJev.from_file(str(EXAMPLES / "support_fixtures.json"))
    summary = code_responses(responses, codebook, provider)
    print("Fictional support triage (synthetic probabilities; no API calls)")
    print("id  chosen          assigned        review  text")
    for row in summary.rows:
        assigned = next((name for name, value in row.assigned.items() if value), "none")
        print(f"{row.id:<4}{row.choice:<16}{assigned:<16}{'yes' if row.review else 'no':<8}{row.text}")
    print("Uncertain choices stay unassigned for human review; none_of_these is a valid abstain.")
    return 0


if __name__ == "__main__":
    sys.exit(run())

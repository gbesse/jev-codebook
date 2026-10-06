"""Export a synthetic single-label human-review queue without an API key."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jev_codebook.client import FakeJev  # noqa: E402
from jev_codebook.codebook import load_codebook  # noqa: E402
from jev_codebook.coder import code_responses  # noqa: E402
from jev_codebook.datafiles import read_responses  # noqa: E402

HERE = ROOT / "examples"


def run() -> int:
    codebook = load_codebook(str(HERE / "support_codebook.json"))
    responses = read_responses(str(HERE / "support_responses.csv")).responses
    provider = FakeJev.from_file(str(HERE / "support_fixtures.json"))
    rows = code_responses(responses, codebook, provider).rows
    writer = csv.DictWriter(sys.stdout, fieldnames=["id", "text", "candidate", "probability", "review"])
    writer.writeheader()
    for row in rows:
        if not row.review:
            continue
        candidate = max(row.probabilities, key=row.probabilities.get)
        writer.writerow({
            "id": row.id,
            "text": row.text,
            "candidate": candidate,
            "probability": f"{row.probabilities[candidate]:.2f}",
            "review": "true",
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

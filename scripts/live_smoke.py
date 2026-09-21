# Purpose: Opt-in live check against api.typesafe.ai: at most 2 paid requests with synthetic text when TYPESAFE_API_KEY is set.
"""Run: ``TYPESAFE_API_KEY=... PYTHONPATH=src python scripts/live_smoke.py``

Sends one multi-mode request (3 nouls) and one single-mode request (1 choice)
about one synthetic sentence, prints answers, usage and estimated cost, and
exits non-zero on any error. Without a key it prints a note and exits 0 so CI
never calls the API by accident.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jev_codebook.client import JevClient, JevError  # noqa: E402
from jev_codebook.codebook import Codebook, build_questions, build_state, validate_codebook  # noqa: E402

TEXT = "The lamp gives a warm, even light, but the hinge loosened after three weeks."
CODEBOOK = {
    "name": "smoke",
    "version": "0",
    "mode": "multi",
    "codes": [
        {"id": "light_quality", "label": "Light quality", "definition": "The response comments on brightness, evenness, color temperature or flicker of the light."},
        {"id": "durability_issue", "label": "Durability issue", "definition": "The response reports a part that broke, loosened or stopped working."},
        {"id": "price_concern", "label": "Price concern", "definition": "The response says the product is expensive or not worth the money."},
    ],
}


def main() -> int:
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY not set; live smoke skipped (nothing was sent).")
        return 0
    try:
        client = JevClient(timeout_seconds=30, max_retries=2)
        multi: Codebook = validate_codebook(CODEBOOK)
        single = Codebook(multi.name, multi.version, multi.codes, multi.language, "single", multi.review_band)
        total_tokens = 0
        for label, cb in (("multi (3 nouls)", multi), ("single (1 choice)", single)):
            questions = build_questions(cb)
            response = client.ask(build_state(TEXT), questions)
            total_tokens += response.input_tokens
            print(f"== {label}: model {response.model}, usage {json.dumps(response.usage)}, est. USD {response.estimated_cost_usd:.6f}")
            print(json.dumps(response.answers, indent=2))
        print(f"total: 2 requests, {total_tokens} input tokens, estimated USD {total_tokens * 0.042 / 1e6:.6f} (published price list)")
        return 0
    except JevError as err:
        print(f"live smoke failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

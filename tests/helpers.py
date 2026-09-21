# Purpose: Shared builders for tests (small codebooks, in-memory fixtures, fake HTTP transports).
from __future__ import annotations

import urllib.request
from typing import Any

from jev_codebook.codebook import Codebook, validate_codebook


def small_codebook(mode: str = "multi", n: int = 3, threshold: float = 0.7) -> Codebook:
    return validate_codebook(
        {
            "name": "test",
            "version": "1",
            "mode": mode,
            "review_band": [0.4, 0.7],
            "codes": [
                {
                    "id": f"code{i}",
                    "label": f"Code {i}",
                    "definition": f"Definition of code {i}.",
                    "include_examples": [f"example {i}"],
                    "exclude_examples": [f"counter {i}"],
                    "threshold": threshold,
                }
                for i in range(1, n + 1)
            ],
        }
    )


class ScriptedTransport:
    """Return scripted (status, headers, body) tuples in order; records every request."""

    def __init__(self, steps: list[Any]):
        self.steps = list(steps)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float):
        self.requests.append(request)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def ok_body(model: str, answers: dict[str, Any], tokens: int = 100) -> bytes:
    import json

    return json.dumps({"model": model, "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 0}}).encode()

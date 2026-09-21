# Purpose: Public package surface for jev-codebook (codebook loading, coding, statistics, reports).
"""jev-codebook: apply a qualitative codebook to open text with Jev.

The package is stdlib-only at runtime. Everything network-related lives in
``client``; every other module is pure computation so it can be unit-tested
without a key and reused from notebooks.
"""

from .client import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    FakeJev,
    JevBudgetError,
    JevClient,
    JevError,
    JevHTTPError,
    JevResponse,
    JevResponseError,
    RateLimiter,
    canonical_json,
    estimate_cost_usd,
    estimate_tokens,
    request_key,
)
from .codebook import Code, Codebook, CodebookError, build_questions, chunk_codes, load_codebook, validate_codebook
from .coder import CodedRow, CodingSummary, code_responses, decide_row

__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
    "Code",
    "Codebook",
    "CodebookError",
    "CodedRow",
    "CodingSummary",
    "FakeJev",
    "JevBudgetError",
    "JevClient",
    "JevError",
    "JevHTTPError",
    "JevResponse",
    "JevResponseError",
    "RateLimiter",
    "build_questions",
    "canonical_json",
    "chunk_codes",
    "code_responses",
    "decide_row",
    "estimate_cost_usd",
    "estimate_tokens",
    "load_codebook",
    "request_key",
    "validate_codebook",
]

__version__ = "0.1.0"

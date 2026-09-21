# Purpose: Run a codebook over responses with bounded concurrency, caching and code-owned decision rules.
"""Coding engine.

The model only returns probabilities. Every decision (assign / review) is
made here, in code, from documented thresholds, so a researcher can re-run
`tune` and re-decide without paying for new requests.
"""

from __future__ import annotations

from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .cache import ExactInputCache
from .client import JevResponse, estimate_cost_usd, estimate_tokens, request_key
from .codebook import MAX_CODES_PER_REQUEST, NONE_OPTION, Codebook, build_questions, build_state, chunk_codes
from .datafiles import Response


class Provider(Protocol):
    model: str

    def ask(self, state: Any, questions: dict[str, Any]) -> JevResponse: ...


@dataclass
class CodedRow:
    id: str
    text: str
    probabilities: dict[str, float]
    assigned: dict[str, int]
    review: bool
    request_id: str
    input_tokens: int = 0
    live_requests: int = 0
    cached_requests: int = 0
    choice: str | None = None


@dataclass
class CodingSummary:
    rows: list[CodedRow] = field(default_factory=list)
    live_requests: int = 0
    cached_requests: int = 0
    input_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return estimate_cost_usd(self.input_tokens)


def decide_row(codebook: Codebook, probabilities: dict[str, float], choice: str | None = None) -> tuple[dict[str, int], bool]:
    """Turn probabilities into 0/1 assignments and a review flag.

    Multi mode: a code is assigned when p >= its threshold; the row goes to
    review when any code sits inside the review band [low, high). Single
    mode: the chosen option is assigned when its probability clears that
    code's threshold; the row goes to review when the winning probability is
    below the band's upper bound, i.e. the model did not clearly prefer one
    option (including 'none').
    """
    low, high = codebook.review_band
    if codebook.mode == "multi":
        assigned = {c.id: int(probabilities.get(c.id, 0.0) >= c.threshold) for c in codebook.codes}
        review = any(low <= probabilities.get(c.id, 0.0) < high for c in codebook.codes)
        return assigned, review
    assigned = {c.id: 0 for c in codebook.codes}
    if choice is None:
        raise ValueError("single mode needs the chosen option")
    if choice == NONE_OPTION:
        winning = 1.0 - sum(probabilities.get(c.id, 0.0) for c in codebook.codes)
    else:
        winning = probabilities.get(choice, 0.0)
        if winning >= codebook.code(choice).threshold:
            assigned[choice] = 1
    return assigned, winning < high


def code_one(response: Response, codebook: Codebook, provider: Provider, cache: ExactInputCache | None = None, max_codes_per_request: int = MAX_CODES_PER_REQUEST) -> CodedRow:
    """Code one response: one fan-out request per chunk of codes (multi) or one choice request (single)."""
    state = build_state(response.text)
    chunks = chunk_codes(codebook.codes, max_codes_per_request) if codebook.mode == "multi" else [list(codebook.codes)]
    probabilities: dict[str, float] = {}
    choice: str | None = None
    keys: list[str] = []
    tokens = live = cached = 0
    for chunk in chunks:
        questions = build_questions(codebook, chunk)
        key = request_key(provider.model, state, questions)
        result = cache.get(key) if cache is not None else None
        if result is None:
            result = provider.ask(state, questions)
            live += 1
            if cache is not None:
                cache.put(key, result)
        else:
            cached += 1
        tokens += result.input_tokens
        keys.append(key[:12])
        if codebook.mode == "multi":
            for code in chunk:
                probabilities[code.id] = float(result.answers[code.id]["noul"])
        else:
            answer = result.answers["code"]
            choice = str(answer["choice"])
            probabilities = {c.id: float(answer["probabilities"].get(c.id, 0.0)) for c in codebook.codes}
    assigned, review = decide_row(codebook, probabilities, choice)
    return CodedRow(response.id, response.text, probabilities, assigned, review, "+".join(keys), tokens, live, cached, choice)


def code_responses(
    responses: list[Response],
    codebook: Codebook,
    provider: Provider,
    *,
    cache: ExactInputCache | None = None,
    concurrency: int = 8,
    on_row: Callable[[CodedRow], None] | None = None,
    max_codes_per_request: int = MAX_CODES_PER_REQUEST,
) -> CodingSummary:
    """Code many responses with a thread pool; the first error cancels the rest and propagates.

    ``on_row`` runs on the calling thread as rows complete, so a CSV writer
    or progress printer needs no locking. Rows are returned in input order.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    summary = CodingSummary()
    done_rows: dict[str, CodedRow] = {}
    futures: dict = {}
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(code_one, r, codebook, provider, cache, max_codes_per_request): r for r in responses}
            pending = set(futures)
            while pending:
                finished, pending = wait(pending, return_when=FIRST_EXCEPTION)
                for fut in finished:
                    row = fut.result()  # re-raises the worker's exception
                    done_rows[row.id] = row
                    summary.live_requests += row.live_requests
                    summary.cached_requests += row.cached_requests
                    summary.input_tokens += row.input_tokens
                    if on_row is not None:
                        on_row(row)
    except BaseException:
        for fut in futures:
            fut.cancel()
        raise
    finally:
        if cache is not None:
            cache.save()
    summary.rows = [done_rows[r.id] for r in responses if r.id in done_rows]
    return summary


@dataclass
class Estimate:
    responses: int
    requests: int
    input_tokens: int
    skipped_blank: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return estimate_cost_usd(self.input_tokens)


def estimate_run(responses: list[Response], codebook: Codebook, max_codes_per_request: int = MAX_CODES_PER_REQUEST) -> Estimate:
    """Token/request/cost preview without any call: per request, state plus questions are all billed as input."""
    chunks = chunk_codes(codebook.codes, max_codes_per_request) if codebook.mode == "multi" else [list(codebook.codes)]
    question_tokens = [estimate_tokens(build_questions(codebook, chunk)) for chunk in chunks]
    total = 0
    for r in responses:
        state_tokens = estimate_tokens(build_state(r.text))
        total += sum(state_tokens + q for q in question_tokens)
    return Estimate(len(responses), len(responses) * len(chunks), total)

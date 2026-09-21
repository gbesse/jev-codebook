# Purpose: Minimal stdlib-only Jev (TypeSafe System One) client, response validation, fake provider, token budget and rate limiter.
"""Jev client for jev-codebook.

Design notes (why, not what):

* ``urllib.request`` with an explicit timeout on every call: a stuck socket
  would otherwise freeze a batch run silently.
* Retries only on 429 / 529 / network errors, bounded and jittered, honoring
  ``Retry-After``. Other 4xx are caller bugs (bad key, bad payload) and
  retrying them would only burn quota.
* The response is validated strictly against the questions we sent. Jev is a
  typed API; if the shape drifts we want a loud failure, never a coerced value
  that silently changes a coding result.
* ``FakeJev`` implements the same ``ask`` contract so tests and the demo make
  no network call; its probabilities are synthetic and labeled as such.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.13.0"
# Published price list, 21 Sept 2026: USD 0.042 per million input tokens, output free.
USD_PER_MILLION_INPUT_TOKENS = 0.042
DEFAULT_STATE_TOKEN_BUDGET = 24_000
RETRYABLE_STATUSES = frozenset({429, 529})


class JevError(Exception):
    """Base class for every error raised by this client."""


class JevHTTPError(JevError):
    """Non-retryable or exhausted HTTP failure; ``status`` is the HTTP code (0 for network errors)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Jev HTTP {status}: {message}" if status else f"Jev network error: {message}")
        self.status = status


class JevResponseError(JevError):
    """The provider returned a body that does not match the questions we sent."""


class JevBudgetError(JevError):
    """The estimated token size of a request exceeds the configured budget."""


def canonical_json(value: Any) -> str:
    """Serialize deterministically so identical inputs always hash identically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def estimate_tokens(value: Any) -> int:
    """Rough token estimate (chars / 4). Used for budgets and cost previews only."""
    text = value if isinstance(value, str) else canonical_json(value)
    return math.ceil(len(text) / 4)


def estimate_cost_usd(input_tokens: int) -> float:
    """Estimated cost from the published price list; not a bill."""
    return input_tokens * USD_PER_MILLION_INPUT_TOKENS / 1e6


def request_key(model: str, state: Any, questions: dict[str, Any]) -> str:
    """Exact-input cache key: sha256 of the canonical request."""
    payload = canonical_json({"model": model, "state": state, "questions": questions})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class JevResponse:
    """Validated answers for one request plus what it cost."""

    model: str
    answers: dict[str, Any]
    usage: dict[str, int]
    cached: bool = False
    key: str = ""

    @property
    def input_tokens(self) -> int:
        return int(self.usage.get("input_tokens", 0))

    @property
    def estimated_cost_usd(self) -> float:
        return estimate_cost_usd(self.input_tokens)


def _number_in_unit(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= value <= 1.0


def validate_response(payload: Any, model: str, questions: dict[str, Any]) -> JevResponse:
    """Check the provider body against the request; raise JevResponseError on any mismatch.

    Strictness is deliberate: a coding pipeline that silently accepted a wrong
    model or an out-of-range probability would produce plausible-looking but
    wrong tables.
    """
    if not isinstance(payload, dict):
        raise JevResponseError("response body is not a JSON object")
    if payload.get("model") != model:
        raise JevResponseError(f"model mismatch: requested {model!r}, got {payload.get('model')!r}")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise JevResponseError("response has no 'answers' object")
    for qid, question in questions.items():
        answer = answers.get(qid)
        if not isinstance(answer, dict):
            raise JevResponseError(f"missing answer for question {qid!r}")
        qtype = question["type"]
        if answer.get("type") != qtype:
            raise JevResponseError(f"answer {qid!r} has type {answer.get('type')!r}, expected {qtype!r}")
        if qtype == "noul":
            if not _number_in_unit(answer.get("noul")):
                raise JevResponseError(f"answer {qid!r}: 'noul' must be a number in [0,1]")
        elif qtype == "choice":
            options = question["criteria"]
            if answer.get("choice") not in options:
                raise JevResponseError(f"answer {qid!r}: choice {answer.get('choice')!r} is not one of the criteria")
            probs = answer.get("probabilities")
            if not isinstance(probs, dict) or not probs:
                raise JevResponseError(f"answer {qid!r}: missing 'probabilities'")
            for option, p in probs.items():
                if option not in options or not _number_in_unit(p):
                    raise JevResponseError(f"answer {qid!r}: bad probability for option {option!r}")
            if not _number_in_unit(answer.get("confidence")):
                raise JevResponseError(f"answer {qid!r}: 'confidence' must be a number in [0,1]")
        elif qtype == "score":
            levels = question["criteria"]
            score = answer.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= len(levels) - 1:
                raise JevResponseError(f"answer {qid!r}: score out of range")
            probs = answer.get("probabilities")
            if not isinstance(probs, dict) or any(not _number_in_unit(p) for p in probs.values()):
                raise JevResponseError(f"answer {qid!r}: bad score probabilities")
            if not _number_in_unit(answer.get("confidence")):
                raise JevResponseError(f"answer {qid!r}: 'confidence' must be a number in [0,1]")
        else:
            raise JevResponseError(f"unsupported question type {qtype!r}")
    usage = payload.get("usage")
    if not isinstance(usage, dict) or not isinstance(usage.get("input_tokens"), int):
        raise JevResponseError("response has no usable 'usage.input_tokens'")
    return JevResponse(model=model, answers=answers, usage=dict(usage))


class RateLimiter:
    """Sliding-window limiter shared by worker threads.

    Kept under the published 1,200 requests/min so a burst from eight threads
    does not turn into a wall of 429s that we would then retry.
    """

    def __init__(self, max_per_minute: int = 1000, *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        if max_per_minute < 1:
            raise ValueError("max_per_minute must be >= 1")
        self.max_per_minute = max_per_minute
        self._clock = clock
        self._sleep = sleep
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                while self._events and now - self._events[0] >= 60.0:
                    self._events.popleft()
                if len(self._events) < self.max_per_minute:
                    self._events.append(now)
                    return
                wait = 60.0 - (now - self._events[0])
            self._sleep(max(wait, 0.01))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: following one could send the bearer key to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib signature
        return None


def _default_transport(request: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """Perform the HTTP call; returns (status, headers, body) and maps HTTPError to the same tuple.

    Kept as a plain function so tests can inject a transport and exercise the
    retry logic without opening sockets.
    """
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        body = err.read() if hasattr(err, "read") else b""
        return err.code, {k.lower(): v for k, v in (err.headers.items() if err.headers else [])}, body


Transport = Callable[[urllib.request.Request, float], tuple[int, dict[str, str], bytes]]


class JevClient:
    """Thin client for ``POST /v1/systemone`` with strict validation."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        state_token_budget: int = DEFAULT_STATE_TOKEN_BUDGET,
        rate_limiter: RateLimiter | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ):
        key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise JevError("Set TYPESAFE_API_KEY (or pass api_key=) before calling Jev")
        if not (endpoint.startswith("https://") or endpoint.startswith("http://127.0.0.1") or endpoint.startswith("http://localhost")):
            raise JevError("endpoint must use https:// (plain http is allowed only for 127.0.0.1/localhost in tests)")
        if timeout_seconds <= 0:
            raise JevError("timeout_seconds must be positive")
        self._api_key = key.strip()
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.state_token_budget = state_token_budget
        self.rate_limiter = rate_limiter
        self._transport = transport or _default_transport
        self._sleep = sleep
        self._rng = rng or random.Random()
        self.total_input_tokens = 0
        self.total_requests = 0
        self._lock = threading.Lock()

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***") if self._api_key else text

    def check_budget(self, state: Any) -> int:
        """Refuse oversized state up front: Jev accuracy drops with large state and the API caps it at 32k."""
        tokens = estimate_tokens(state)
        if tokens > self.state_token_budget:
            raise JevBudgetError(f"state estimated at {tokens} tokens exceeds the budget of {self.state_token_budget}")
        return tokens

    def ask(self, state: Any, questions: dict[str, Any]) -> JevResponse:
        if not questions:
            raise JevError("ask() needs at least one question")
        self.check_budget(state)
        body = canonical_json({"model": self.model, "state": state, "questions": questions}).encode("utf-8")
        attempt = 0
        while True:
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            request = urllib.request.Request(
                self.endpoint,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "jev-codebook/0.1.0",
                },
            )
            try:
                status, headers, raw = self._transport(request, self.timeout_seconds)
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                if attempt >= self.max_retries:
                    raise JevHTTPError(0, self._redact(str(err))) from None
                self._backoff(attempt, None)
                attempt += 1
                continue
            if status in RETRYABLE_STATUSES:
                if attempt >= self.max_retries:
                    raise JevHTTPError(status, self._redact(_short(raw)) or "rate limited / overloaded, retries exhausted")
                self._backoff(attempt, headers.get("retry-after"))
                attempt += 1
                continue
            if status != 200:
                raise JevHTTPError(status, self._redact(_short(raw)) or "request failed")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as err:
                raise JevResponseError(f"response is not valid JSON: {err}") from None
            response = validate_response(payload, self.model, questions)
            with self._lock:
                self.total_requests += 1
                self.total_input_tokens += response.input_tokens
            return response

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        """Exponential backoff with jitter; a numeric Retry-After header wins when present."""
        delay = min(0.5 * (2**attempt), 8.0) + self._rng.uniform(0, 0.25)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        self._sleep(delay)


def _short(raw: bytes, limit: int = 300) -> str:
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:  # pragma: no cover - defensive
        return ""
    return text[:limit]


@dataclass
class FakeJev:
    """Offline stand-in for JevClient with the same ``ask`` contract.

    Fixture format (JSON)::

        {
          "default_probability": 0.05,
          "responses": {
            "<exact response text>": { "<question id>": 0.9, "code": "praise" }
          }
        }

    A noul question takes a float. A choice question takes either the option
    name (mass 0.9 on it, remainder spread evenly) or a full probability map.
    Anything not listed falls back to ``default_probability`` (noul) or the
    last option (choice). All numbers are synthetic; they are not Jev output.
    """

    fixtures: dict[str, Any] = field(default_factory=dict)
    model: str = DEFAULT_MODEL
    state_key: str = "response"
    tokens_per_call: int | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_file(cls, path: str) -> "FakeJev":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("responses", {}), dict):
            raise JevError(f"fixtures file {path} must be an object with a 'responses' map")
        return cls(fixtures=data)

    def ask(self, state: Any, questions: dict[str, Any]) -> JevResponse:
        if not questions:
            raise JevError("ask() needs at least one question")
        text = state.get(self.state_key) if isinstance(state, dict) else state
        entry = self.fixtures.get("responses", {}).get(text, {})
        default_p = float(self.fixtures.get("default_probability", 0.05))
        answers: dict[str, Any] = {}
        for qid, question in questions.items():
            qtype = question["type"]
            value = entry.get(qid)
            if qtype == "noul":
                answers[qid] = {"type": "noul", "noul": float(value) if value is not None else default_p}
            elif qtype == "choice":
                options = list(question["criteria"].keys())
                answers[qid] = _fake_choice(options, value)
            else:
                raise JevError(f"FakeJev does not model question type {qtype!r}")
        tokens = self.tokens_per_call if self.tokens_per_call is not None else estimate_tokens({"state": state, "questions": questions})
        payload = {"model": self.model, "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 0}}
        with self._lock:
            self.calls.append({"state": state, "questions": questions})
        return validate_response(payload, self.model, questions)


def _fake_choice(options: list[str], value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        probs = {opt: float(value.get(opt, 0.0)) for opt in options}
    else:
        chosen = value if isinstance(value, str) and value in options else options[-1]
        rest = (1.0 - 0.9) / max(1, len(options) - 1)
        probs = {opt: (0.9 if opt == chosen else rest) for opt in options}
    choice = max(options, key=lambda o: (probs[o], -options.index(o)))
    # Same idea as the documented confidence: 1.0 when all mass sits on one option.
    ordered = sorted(probs.values(), reverse=True)
    confidence = round(ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0), 6)
    return {"type": "choice", "choice": choice, "probabilities": probs, "confidence": max(0.0, min(1.0, confidence))}

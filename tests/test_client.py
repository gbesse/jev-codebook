# Purpose: Client behavior without sockets: key/endpoint checks, retries on 429/529, response validation, redaction, budget, limiter, fake provider.
import json
import unittest
import urllib.error

from helpers import ScriptedTransport, ok_body
from jev_codebook.client import (
    DEFAULT_MODEL,
    FakeJev,
    JevBudgetError,
    JevClient,
    JevError,
    JevHTTPError,
    JevResponseError,
    RateLimiter,
    estimate_cost_usd,
    estimate_tokens,
    request_key,
    validate_response,
)

Q = {"yes": {"type": "noul", "instructions": "Is it?", "criteria": {"true": "yes", "false": "no"}}}
CHOICE_Q = {"pick": {"type": "choice", "instructions": "Which?", "criteria": {"a": "A", "b": "B"}}}


def client(steps, **kw):
    transport = ScriptedTransport(steps)
    sleeps = []
    c = JevClient("sk-test-key", transport=transport, sleep=sleeps.append, **kw)
    return c, transport, sleeps


class ConstructionTests(unittest.TestCase):
    def test_requires_key(self):
        import os
        old = os.environ.pop("TYPESAFE_API_KEY", None)
        try:
            with self.assertRaisesRegex(JevError, "TYPESAFE_API_KEY"):
                JevClient()
            with self.assertRaises(JevError):
                JevClient("   ")
        finally:
            if old is not None:
                os.environ["TYPESAFE_API_KEY"] = old

    def test_endpoint_must_be_https_except_loopback(self):
        with self.assertRaises(JevError):
            JevClient("k", endpoint="http://api.typesafe.ai/v1/systemone")
        JevClient("k", endpoint="http://127.0.0.1:9/x")
        JevClient("k", endpoint="http://localhost:9/x")


class RequestTests(unittest.TestCase):
    def test_success_sends_bearer_and_pinned_model(self):
        c, transport, _ = client([(200, {}, ok_body(DEFAULT_MODEL, {"yes": {"type": "noul", "noul": 0.8}}, 42))])
        r = c.ask({"response": "hi"}, Q)
        self.assertEqual(r.answers["yes"]["noul"], 0.8)
        self.assertEqual(r.input_tokens, 42)
        self.assertAlmostEqual(r.estimated_cost_usd, estimate_cost_usd(42))
        req = transport.requests[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer sk-test-key")
        self.assertEqual(json.loads(req.data)["model"], DEFAULT_MODEL)
        self.assertEqual(c.total_requests, 1)

    def test_retries_on_429_then_succeeds_and_honors_retry_after(self):
        c, transport, sleeps = client([
            (429, {"retry-after": "3"}, b"slow down"),
            (200, {}, ok_body(DEFAULT_MODEL, {"yes": {"type": "noul", "noul": 0.1}})),
        ])
        c.ask("x", Q)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertGreaterEqual(sleeps[0], 3.0)

    def test_retries_on_529_and_network_error(self):
        c, transport, sleeps = client([
            (529, {}, b"overloaded"),
            urllib.error.URLError("boom"),
            (200, {}, ok_body(DEFAULT_MODEL, {"yes": {"type": "noul", "noul": 0.1}})),
        ], max_retries=2)
        c.ask("x", Q)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(len(sleeps), 2)

    def test_retries_are_bounded(self):
        c, transport, _ = client([(429, {}, b""), (429, {}, b""), (429, {}, b"")], max_retries=2)
        with self.assertRaises(JevHTTPError) as ctx:
            c.ask("x", Q)
        self.assertEqual(ctx.exception.status, 429)
        self.assertEqual(len(transport.requests), 3)

    def test_other_4xx_not_retried(self):
        c, transport, _ = client([(422, {}, b"bad question")])
        with self.assertRaises(JevHTTPError) as ctx:
            c.ask("x", Q)
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(len(transport.requests), 1)

    def test_key_redacted_from_errors(self):
        c, _, _ = client([(401, {}, b"invalid key sk-test-key")])
        with self.assertRaises(JevHTTPError) as ctx:
            c.ask("x", Q)
        self.assertNotIn("sk-test-key", str(ctx.exception))

    def test_budget_refuses_large_state(self):
        c, transport, _ = client([], state_token_budget=10)
        with self.assertRaises(JevBudgetError):
            c.ask("a" * 100, Q)
        self.assertEqual(transport.requests, [])

    def test_invalid_json_body(self):
        c, _, _ = client([(200, {}, b"<html>")])
        with self.assertRaises(JevResponseError):
            c.ask("x", Q)


class ValidationTests(unittest.TestCase):
    def good(self):
        return {"model": DEFAULT_MODEL, "answers": {"yes": {"type": "noul", "noul": 0.5}}, "usage": {"input_tokens": 1, "output_tokens": 0}}

    def test_model_mismatch(self):
        p = self.good(); p["model"] = "jev-latest"
        with self.assertRaisesRegex(JevResponseError, "model mismatch"):
            validate_response(p, DEFAULT_MODEL, Q)

    def test_missing_or_mistyped_answer(self):
        p = self.good(); p["answers"] = {}
        with self.assertRaisesRegex(JevResponseError, "missing answer"):
            validate_response(p, DEFAULT_MODEL, Q)
        p = self.good(); p["answers"]["yes"]["type"] = "choice"
        with self.assertRaises(JevResponseError):
            validate_response(p, DEFAULT_MODEL, Q)

    def test_noul_out_of_range(self):
        for bad in (1.5, -0.1, "0.5", True, None):
            p = self.good(); p["answers"]["yes"]["noul"] = bad
            with self.assertRaises(JevResponseError):
                validate_response(p, DEFAULT_MODEL, Q)

    def test_choice_checks(self):
        ans = {"type": "choice", "choice": "a", "probabilities": {"a": 0.7, "b": 0.3}, "confidence": 0.4}
        p = {"model": DEFAULT_MODEL, "answers": {"pick": ans}, "usage": {"input_tokens": 1}}
        validate_response(p, DEFAULT_MODEL, CHOICE_Q)
        for mutate in (
            lambda a: a.update(choice="zzz"),
            lambda a: a["probabilities"].update(c=0.1),
            lambda a: a["probabilities"].update(a=2),
            lambda a: a.update(confidence=None),
        ):
            bad = json.loads(json.dumps(p)); mutate(bad["answers"]["pick"])
            with self.assertRaises(JevResponseError):
                validate_response(bad, DEFAULT_MODEL, CHOICE_Q)

    def test_usage_required(self):
        p = self.good(); del p["usage"]
        with self.assertRaises(JevResponseError):
            validate_response(p, DEFAULT_MODEL, Q)


class HelpersTests(unittest.TestCase):
    def test_request_key_is_stable_and_order_independent(self):
        k1 = request_key("m", {"b": 1, "a": 2}, Q)
        k2 = request_key("m", {"a": 2, "b": 1}, Q)
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 64)
        self.assertNotEqual(k1, request_key("m", {"a": 3, "b": 1}, Q))

    def test_token_estimate(self):
        self.assertEqual(estimate_tokens("abcd" * 10), 10)
        self.assertEqual(estimate_tokens("abcde"), 2)

    def test_rate_limiter_blocks_over_limit(self):
        now = [0.0]
        sleeps = []

        def sleep(s):
            sleeps.append(s)
            now[0] += s

        rl = RateLimiter(2, clock=lambda: now[0], sleep=sleep)
        rl.acquire(); rl.acquire()
        rl.acquire()  # third call must wait for the window to slide
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 60.0)


class FakeJevTests(unittest.TestCase):
    def test_fixture_lookup_and_default(self):
        fake = FakeJev({"default_probability": 0.2, "responses": {"hello": {"yes": 0.9}}})
        self.assertEqual(fake.ask({"response": "hello"}, Q).answers["yes"]["noul"], 0.9)
        self.assertEqual(fake.ask({"response": "other"}, Q).answers["yes"]["noul"], 0.2)
        self.assertEqual(len(fake.calls), 2)

    def test_choice_by_name_and_by_map(self):
        fake = FakeJev({"responses": {"t1": {"pick": "a"}, "t2": {"pick": {"a": 0.25, "b": 0.75}}}})
        a1 = fake.ask({"response": "t1"}, CHOICE_Q).answers["pick"]
        self.assertEqual(a1["choice"], "a")
        self.assertAlmostEqual(a1["probabilities"]["a"], 0.9)
        a2 = fake.ask({"response": "t2"}, CHOICE_Q).answers["pick"]
        self.assertEqual(a2["choice"], "b")
        self.assertAlmostEqual(a2["confidence"], 0.5)
        # Unlisted text falls back to the last option (none_of_these in single mode).
        self.assertEqual(fake.ask({"response": "?"}, CHOICE_Q).answers["pick"]["choice"], "b")


if __name__ == "__main__":
    unittest.main()

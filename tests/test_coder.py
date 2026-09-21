# Purpose: Coding engine: decisions, review band, cache hits, chunking beyond 40 codes, error propagation, estimates.
import os
import tempfile
import unittest

from helpers import small_codebook
from jev_codebook.cache import ExactInputCache
from jev_codebook.client import FakeJev, JevError
from jev_codebook.coder import code_one, code_responses, decide_row, estimate_run
from jev_codebook.datafiles import Response


class DecideTests(unittest.TestCase):
    def test_multi_assign_and_review(self):
        cb = small_codebook("multi", 3)
        assigned, review = decide_row(cb, {"code1": 0.95, "code2": 0.1, "code3": 0.5})
        self.assertEqual(assigned, {"code1": 1, "code2": 0, "code3": 0})
        self.assertTrue(review)
        assigned, review = decide_row(cb, {"code1": 0.7, "code2": 0.39, "code3": 0.0})
        self.assertEqual(assigned["code1"], 1)  # threshold is inclusive
        self.assertFalse(review)

    def test_single_mode(self):
        cb = small_codebook("single", 2)
        assigned, review = decide_row(cb, {"code1": 0.9, "code2": 0.05}, choice="code1")
        self.assertEqual(assigned, {"code1": 1, "code2": 0})
        self.assertFalse(review)
        assigned, review = decide_row(cb, {"code1": 0.6, "code2": 0.3}, choice="code1")
        self.assertEqual(assigned["code1"], 0)  # below its threshold
        self.assertTrue(review)
        assigned, review = decide_row(cb, {"code1": 0.02, "code2": 0.03}, choice="none_of_these")
        self.assertEqual(sum(assigned.values()), 0)
        self.assertFalse(review)
        with self.assertRaises(ValueError):
            decide_row(cb, {})


class CodeTests(unittest.TestCase):
    def test_multi_mode_fake_path(self):
        cb = small_codebook("multi", 3)
        fake = FakeJev({"responses": {"great": {"code1": 0.9, "code2": 0.5}}})
        row = code_one(Response("1", "great"), cb, fake)
        self.assertEqual(row.probabilities, {"code1": 0.9, "code2": 0.5, "code3": 0.05})
        self.assertEqual(row.assigned, {"code1": 1, "code2": 0, "code3": 0})
        self.assertTrue(row.review)
        self.assertEqual(row.live_requests, 1)
        self.assertEqual(len(row.request_id), 12)
        self.assertEqual(fake.calls[0]["state"], {"response": "great"})
        self.assertEqual(list(fake.calls[0]["questions"]), ["code1", "code2", "code3"])

    def test_single_mode_fake_path(self):
        cb = small_codebook("single", 2)
        fake = FakeJev({"responses": {"t": {"code": "code2"}}})
        row = code_one(Response("1", "t"), cb, fake)
        self.assertEqual(row.choice, "code2")
        self.assertEqual(row.assigned, {"code1": 0, "code2": 1})
        self.assertEqual(len(fake.calls), 1)

    def test_chunking_makes_two_requests_per_response(self):
        cb = small_codebook("multi", 45)
        fake = FakeJev({"responses": {"t": {"code45": 0.99}}})
        row = code_one(Response("1", "t"), cb, fake)
        self.assertEqual(row.live_requests, 2)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(len(fake.calls[0]["questions"]), 40)
        self.assertEqual(len(fake.calls[1]["questions"]), 5)
        self.assertEqual(row.assigned["code45"], 1)
        self.assertEqual(row.request_id.count("+"), 1)

    def test_cache_hit_skips_provider(self):
        cb = small_codebook("multi", 2)
        fake = FakeJev({"responses": {"t": {"code1": 0.8}}})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cache.json")
            cache = ExactInputCache(path)
            first = code_responses([Response("1", "t")], cb, fake, cache=cache)
            self.assertEqual((first.live_requests, first.cached_requests), (1, 0))
            self.assertTrue(os.path.exists(path))
            reloaded = ExactInputCache(path)
            second = code_responses([Response("1", "t")], cb, fake, cache=reloaded)
            self.assertEqual((second.live_requests, second.cached_requests), (0, 1))
            self.assertEqual(second.rows[0].probabilities, first.rows[0].probabilities)
            self.assertEqual(len(fake.calls), 1)
            # A different codebook version changes the questions, therefore the key.
            other = small_codebook("multi", 2, threshold=0.5)
            self.assertEqual(code_responses([Response("1", "t")], other, fake, cache=reloaded).cached_requests, 1)

    def test_rows_in_input_order_and_callback(self):
        cb = small_codebook("multi", 1)
        fake = FakeJev({})
        seen = []
        responses = [Response(str(i), f"text {i}") for i in range(20)]
        summary = code_responses(responses, cb, fake, concurrency=4, on_row=lambda r: seen.append(r.id))
        self.assertEqual([r.id for r in summary.rows], [r.id for r in responses])
        self.assertEqual(sorted(seen, key=int), [r.id for r in responses])
        self.assertEqual(summary.live_requests, 20)

    def test_provider_error_propagates(self):
        cb = small_codebook("multi", 1)

        class Broken:
            model = "jev-1.13.0"

            def ask(self, state, questions):
                raise JevError("down")

        with self.assertRaisesRegex(JevError, "down"):
            code_responses([Response("1", "t"), Response("2", "u")], cb, Broken(), concurrency=2)

    def test_estimate_counts(self):
        cb = small_codebook("multi", 45)
        est = estimate_run([Response("1", "abcd" * 25), Response("2", "x")], cb)
        self.assertEqual(est.responses, 2)
        self.assertEqual(est.requests, 4)
        self.assertGreater(est.input_tokens, 0)
        self.assertAlmostEqual(est.estimated_cost_usd, est.input_tokens * 0.042 / 1e6)


if __name__ == "__main__":
    unittest.main()

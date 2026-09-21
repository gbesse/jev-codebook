# Purpose: End-to-end CLI runs on the example dataset with the fake provider: validate, estimate, code (resume, cache, review), agreement, tune, report.
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from jev_codebook.cli import main
from jev_codebook.datafiles import read_coded

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jev-codebook-cli-")
        self.codebook = str(EXAMPLES / "codebook.json")
        self.responses = str(EXAMPLES / "responses.csv")
        self.fixtures = str(EXAMPLES / "fixtures.json")
        self.human = str(EXAMPLES / "human.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_validate(self):
        rc, out, _ = run("validate", self.codebook)
        self.assertEqual(rc, 0)
        self.assertIn("6 codes", out)
        bad = self.path("bad.json")
        with open(bad, "w") as fh:
            json.dump({"name": "x"}, fh)
        rc, _, err = run("validate", bad)
        self.assertEqual(rc, 1)
        self.assertIn("invalid codebook", err)

    def test_estimate_json(self):
        rc, out, _ = run("estimate", self.responses, "--codebook", self.codebook, "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["responses"], 40)
        self.assertEqual(data["requests"], 40)
        self.assertEqual(data["skipped_blank"], 1)
        self.assertAlmostEqual(data["estimated_cost_usd"], data["input_tokens"] * 0.042 / 1e6)

    def test_code_review_cache_and_resume(self):
        out, review, cache = self.path("coded.csv"), self.path("review.csv"), self.path("cache.json")
        rc, text, _ = run("code", self.responses, "--codebook", self.codebook, "--out", out, "--review", review, "--cache", cache, "--fake", self.fixtures, "--concurrency", "3")
        self.assertEqual(rc, 0)
        self.assertIn("coded 40 responses", text)
        self.assertIn("40 live, 0 cached", text)
        coded = read_coded(out)
        self.assertEqual(len(coded.records), 40)
        self.assertEqual(len(read_coded(review).records), sum(1 for r in coded.records if r.review))
        self.assertTrue(os.path.exists(cache))
        # Resume: drop the last 5 rows and run again; only those are coded and the cache serves them.
        with open(out) as fh:
            lines = fh.readlines()
        with open(out, "w") as fh:
            fh.writelines(lines[:-5])
        rc, text, err = run("code", self.responses, "--codebook", self.codebook, "--out", out, "--cache", cache, "--fake", self.fixtures)
        self.assertEqual(rc, 0)
        self.assertIn("resuming: 35 ids", err)
        self.assertIn("coded 5 responses", text)
        self.assertIn("0 live, 5 cached", text)
        self.assertEqual(len(read_coded(out).records), 40)
        rc, text, _ = run("code", self.responses, "--codebook", self.codebook, "--out", out, "--fake", self.fixtures)
        self.assertEqual(rc, 0)
        self.assertIn("nothing to code", text)
        rc, _, err = run("code", self.responses, "--codebook", self.codebook, "--out", out, "--fake", self.fixtures, "--no-resume")
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)

    def test_agreement_tune_report(self):
        out = self.path("coded.csv")
        self.assertEqual(run("code", self.responses, "--codebook", self.codebook, "--out", out, "--fake", self.fixtures)[0], 0)
        rc, text, _ = run("agreement", out, self.human, "--codebook", self.codebook, "--json")
        self.assertEqual(rc, 0)
        data = json.loads(text)
        self.assertEqual(data["n_matched"], 40)
        self.assertEqual(set(data["per_code"]), {"light_quality", "price_concern", "setup_difficulty", "feature_request", "durability_issue", "support_experience"})
        self.assertIn("cohen_kappa", data["per_code"]["light_quality"])
        rc, text, _ = run("agreement", out, self.human, "--codebook", self.codebook)
        self.assertEqual(rc, 0)
        self.assertIn("kappa", text)

        tuned_path = self.path("tuned.json")
        rc, text, _ = run("tune", out, self.human, "--codebook", self.codebook, "--write-codebook", tuned_path, "--json")
        self.assertEqual(rc, 0)
        data = json.loads(text)
        self.assertEqual(data["n_tune"] + data["n_holdout"], 40)
        with open(tuned_path) as fh:
            tuned = json.load(fh)
        self.assertEqual({c["id"]: c["threshold"] for c in tuned["codes"]}, {t["code"]: t["tuned_threshold"] for t in data["per_code"]})
        self.assertEqual(run("validate", tuned_path)[0], 0)

        rc, text, _ = run("report", out, "--codebook", self.codebook, "--json", "--top", "3")
        self.assertEqual(rc, 0)
        data = json.loads(text)
        self.assertEqual(data["n"], 40)
        self.assertEqual(len(data["top_uncertain"]), 3)
        self.assertEqual(data["cooccurrence"]["durability_issue"]["support_experience"], data["cooccurrence"]["support_experience"]["durability_issue"])
        rc, text, _ = run("report", out)
        self.assertEqual(rc, 0)
        self.assertIn("co-occurrence", text)

    def test_code_mismatch_is_an_error(self):
        out = self.path("coded.csv")
        with open(out, "w") as fh:
            fh.write("id,text,a,p_a,review,request_id\n1,x,1,0.9,0,\n")
        rc, _, err = run("agreement", out, self.human, "--codebook", self.codebook)
        self.assertEqual(rc, 1)
        self.assertIn("differ from the codebook", err)


if __name__ == "__main__":
    unittest.main()

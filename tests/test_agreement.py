# Purpose: Agreement alignment and the tune/holdout separation guarantee.
import unittest

from helpers import small_codebook
from jev_codebook.agreement import compute_agreement, split_ids, tune_thresholds
from jev_codebook.datafiles import CodedFile, CodedRecord
from jev_codebook.stats import binary_metrics


def make_coded(n=50):
    # p_code1 rises with the index so a threshold sweep has something to find.
    records = []
    for i in range(n):
        p1 = round(i / (n - 1), 3)
        records.append(CodedRecord(f"id{i}", f"text {i}", {"code1": int(p1 >= 0.7), "code2": 0}, {"code1": p1, "code2": 0.1}, False))
    return CodedFile(["code1", "code2"], records)


def human_from(coded, cut=0.5):
    return {r.id: {"code1": int(r.probabilities["code1"] >= cut), "code2": 0} for r in coded.records}


class AgreementTests(unittest.TestCase):
    def test_matches_binary_metrics_and_reports_unmatched(self):
        cb = small_codebook("multi", 2)
        coded = make_coded(20)
        human = human_from(coded, 0.5)
        human.pop("id0")
        human["ghost"] = {"code1": 1, "code2": 0}
        report = compute_agreement(coded, human, cb)
        self.assertEqual(report.n_matched, 19)
        self.assertEqual(report.unmatched_coded, 1)
        self.assertEqual(report.unmatched_human, 1)
        pred = [r.assigned["code1"] for r in coded.records if r.id in human]
        truth = [human[r.id]["code1"] for r in coded.records if r.id in human]
        self.assertEqual(report.per_code["code1"], binary_metrics(pred, truth))
        self.assertLess(report.exact_match_rate, 1.0)

    def test_use_thresholds_re_decides_from_probabilities(self):
        cb = small_codebook("multi", 2, threshold=0.5)
        coded = make_coded(20)
        report = compute_agreement(coded, human_from(coded, 0.5), cb, use_thresholds=True)
        self.assertEqual(report.per_code["code1"].fn, 0)
        self.assertEqual(report.per_code["code1"].fp, 0)


class TuneTests(unittest.TestCase):
    def test_split_is_seeded_disjoint_and_order_independent(self):
        ids = [f"id{i}" for i in range(30)]
        a, b = split_ids(ids, seed=1)
        a2, b2 = split_ids(list(reversed(ids)), seed=1)
        self.assertEqual((a, b), (a2, b2))
        self.assertEqual(len(a), 18)
        self.assertEqual(set(a) | set(b), set(ids))
        self.assertFalse(set(a) & set(b))
        self.assertNotEqual(split_ids(ids, seed=2)[0], a)

    def test_tuned_threshold_tracks_tuning_labels(self):
        cb = small_codebook("multi", 2, threshold=0.7)
        coded = make_coded(60)
        report = tune_thresholds(coded, human_from(coded, 0.5), cb, seed=3)
        t = report.per_code[0]
        self.assertEqual(t.code, "code1")
        self.assertAlmostEqual(t.tuned_threshold, 0.5)
        self.assertGreaterEqual(t.holdout_tuned.f1, t.holdout_current.f1)
        self.assertEqual(report.n_tune + report.n_holdout, 60)
        self.assertEqual(report.thresholds["code1"], 0.5)

    def test_holdout_labels_never_influence_thresholds(self):
        cb = small_codebook("multi", 2, threshold=0.7)
        coded = make_coded(60)
        human = human_from(coded, 0.5)
        baseline = tune_thresholds(coded, human, cb, seed=7)
        _, holdout_ids = split_ids([r.id for r in coded.records], seed=7)
        corrupted = dict(human)
        for rid in holdout_ids:  # flip every holdout label
            corrupted[rid] = {"code1": 1 - human[rid]["code1"], "code2": 1}
        changed = tune_thresholds(coded, corrupted, cb, seed=7)
        self.assertEqual(changed.thresholds, baseline.thresholds)
        self.assertEqual([t.tune_f1_at_tuned for t in changed.per_code], [t.tune_f1_at_tuned for t in baseline.per_code])
        # ...but holdout metrics do move, proving they were computed on the flipped rows.
        self.assertNotEqual(changed.per_code[0].holdout_tuned.f1, baseline.per_code[0].holdout_tuned.f1)


if __name__ == "__main__":
    unittest.main()

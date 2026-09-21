# Purpose: Check the stdlib statistics against textbook values (Wilson, Cohen's kappa, Krippendorff's alpha).
import math
import unittest

from jev_codebook.stats import binary_metrics, cohen_kappa, krippendorff_alpha_nominal, percent_agreement, wilson_interval


class WilsonTests(unittest.TestCase):
    def test_zero_successes_of_ten(self):
        # Classic reference value: 0/10 gives an upper bound of 0.2775 at 95%.
        low, high = wilson_interval(0, 10)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 0.2775, places=4)

    def test_half_of_twenty(self):
        low, high = wilson_interval(10, 20)
        self.assertAlmostEqual(low, 0.2993, places=4)
        self.assertAlmostEqual(high, 0.7007, places=4)

    def test_all_successes_is_bounded_by_one(self):
        low, high = wilson_interval(10, 10)
        self.assertAlmostEqual(high, 1.0)
        self.assertAlmostEqual(low, 0.7225, places=4)

    def test_empty_sample(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 0.0))

    def test_rejects_impossible_counts(self):
        with self.assertRaises(ValueError):
            wilson_interval(5, 4)


class KappaTests(unittest.TestCase):
    def textbook_2x2(self):
        # Textbook table: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> p_o 0.7, p_e 0.5, kappa 0.4.
        a = [1] * 20 + [1] * 5 + [0] * 10 + [0] * 15
        b = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
        return a, b

    def test_textbook_value(self):
        a, b = self.textbook_2x2()
        self.assertAlmostEqual(percent_agreement(a, b), 0.7)
        self.assertAlmostEqual(cohen_kappa(a, b), 0.4)

    def test_perfect_and_chance(self):
        self.assertAlmostEqual(cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]), 1.0)
        # Both coders always say yes: p_e == 1, kappa undefined.
        self.assertTrue(math.isnan(cohen_kappa([1, 1], [1, 1])))

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            cohen_kappa([1], [1, 0])


class AlphaTests(unittest.TestCase):
    def test_hand_computed_example(self):
        # a = [a,a,b,b,a], b = [a,b,b,b,a]: n = 10 values, disagreements sum 2, sum n_c n_k (c != k) = 2*5*5 = 50
        # alpha = 1 - 9 * 2 / 50 = 0.64
        self.assertAlmostEqual(krippendorff_alpha_nominal("aabba", "abbba"), 0.64)

    def test_textbook_2x2_table(self):
        # Same table as the kappa test: totals yes 55, no 45; disagreements 15 units -> 30 mismatched pairs
        # alpha = 1 - 99 * 30 / (2 * 55 * 45) = 0.4
        a = [1] * 20 + [1] * 5 + [0] * 10 + [0] * 15
        b = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
        self.assertAlmostEqual(krippendorff_alpha_nominal(a, b), 0.4)

    def test_perfect(self):
        self.assertAlmostEqual(krippendorff_alpha_nominal([1, 0, 1], [1, 0, 1]), 1.0)


class BinaryMetricsTests(unittest.TestCase):
    def test_counts_and_intervals(self):
        pred = [1, 1, 1, 0, 0, 0]
        truth = [1, 1, 0, 1, 0, 0]
        m = binary_metrics(pred, truth)
        self.assertEqual((m.tp, m.fp, m.fn, m.tn), (2, 1, 1, 2))
        self.assertAlmostEqual(m.precision, 2 / 3)
        self.assertAlmostEqual(m.recall, 2 / 3)
        self.assertAlmostEqual(m.f1, 2 / 3)
        self.assertEqual(m.precision_ci, wilson_interval(2, 3))
        self.assertAlmostEqual(m.accuracy, 4 / 6)

    def test_no_positives_anywhere(self):
        m = binary_metrics([0, 0], [0, 0])
        self.assertTrue(math.isnan(m.precision))
        self.assertTrue(math.isnan(m.f1))
        self.assertEqual(m.precision_ci, (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()

# Purpose: Stdlib implementations of Wilson intervals, Cohen's kappa, percent agreement, precision/recall/F1 and Krippendorff's alpha (nominal, two coders).
"""Reliability statistics.

Implemented by hand so the package stays dependency-free; each function is
unit-tested against textbook values (see tests/test_stats.py). Formulas:

* Wilson score interval (Wilson 1927) for a binomial proportion.
* Cohen's kappa = (p_o - p_e) / (1 - p_e) on the two coders' marginals.
* Krippendorff's alpha, nominal metric, computed from the coincidence matrix:
  alpha = 1 - (n - 1) * sum_{c != k} o_ck / sum_{c != k} n_c n_k
  where n is the number of pairable values (2 x units for two complete coders).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Hashable, Sequence

Z95 = 1.959963984540054


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for successes/n; (0, 0) when n == 0 so tables never divide by zero."""
    if n <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > n:
        raise ValueError("successes must be within [0, n]")
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def percent_agreement(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    _check_pair(a, b)
    if not a:
        return float("nan")
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """Cohen's kappa for two coders over nominal labels; nan when undefined (p_e == 1)."""
    _check_pair(a, b)
    n = len(a)
    if n == 0:
        return float("nan")
    po = percent_agreement(a, b)
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[label] * cb[label] for label in set(ca) | set(cb)) / (n * n)
    if pe == 1.0:
        return float("nan")
    return (po - pe) / (1 - pe)


def krippendorff_alpha_nominal(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """Krippendorff's alpha (nominal) for two coders with no missing values.

    Uses the coincidence matrix so the result matches published examples
    exactly, including the (n - 1) small-sample correction that separates
    alpha from Scott's pi.
    """
    _check_pair(a, b)
    if not a:
        return float("nan")
    n_values = 2 * len(a)
    totals: Counter = Counter(a) + Counter(b)
    disagreements = sum(2 for x, y in zip(a, b) if x != y)  # each disagreeing unit adds o_ck and o_kc
    expected = sum(totals[c] * totals[k] for c in totals for k in totals if c != k)
    if expected == 0:
        return float("nan")
    return 1 - (n_values - 1) * disagreements / expected


@dataclass(frozen=True)
class BinaryMetrics:
    n: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    precision_ci: tuple[float, float]
    recall: float
    recall_ci: tuple[float, float]
    f1: float
    accuracy: float
    kappa: float
    alpha: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": self.precision,
            "precision_ci95": list(self.precision_ci),
            "recall": self.recall,
            "recall_ci95": list(self.recall_ci),
            "f1": self.f1,
            "percent_agreement": self.accuracy,
            "cohen_kappa": self.kappa,
            "krippendorff_alpha": self.alpha,
        }


def binary_metrics(pred: Sequence[int], truth: Sequence[int]) -> BinaryMetrics:
    """Precision/recall/F1 with Wilson intervals plus the two agreement coefficients for one code.

    Wilson intervals on precision (over predicted positives) and recall (over
    true positives) tell the researcher how much the small denominators are
    worth, which a bare point estimate hides.
    """
    _check_pair(pred, truth)
    tp = sum(1 for p, t in zip(pred, truth) if p and t)
    fp = sum(1 for p, t in zip(pred, truth) if p and not t)
    fn = sum(1 for p, t in zip(pred, truth) if not p and t)
    tn = len(pred) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = (2 * precision * recall / (precision + recall)) if (tp + fp and tp + fn and precision + recall) else (0.0 if (tp + fp or tp + fn) else float("nan"))
    return BinaryMetrics(
        n=len(pred),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        precision_ci=wilson_interval(tp, tp + fp),
        recall=recall,
        recall_ci=wilson_interval(tp, tp + fn),
        f1=f1,
        accuracy=percent_agreement(pred, truth),
        kappa=cohen_kappa(pred, truth),
        alpha=krippendorff_alpha_nominal(pred, truth),
    )


def _check_pair(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError(f"sequences must have the same length ({len(a)} vs {len(b)})")


def fmt(value: float, digits: int = 3) -> str:
    """Format a statistic for tables; nan prints as '-' rather than crashing a report."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:.{digits}f}"

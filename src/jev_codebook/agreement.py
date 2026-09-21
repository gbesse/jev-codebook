# Purpose: Inter-rater agreement against human labels and threshold tuning with a fixed-seed tune/holdout split.
"""Agreement and tuning.

Why a split at all: choosing the threshold that maximizes F1 on the same
rows you then report is optimistic by construction. The tuning split picks,
the holdout split reports, and the holdout labels never enter the choice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .codebook import Codebook
from .datafiles import CodedFile, CodedRecord
from .stats import BinaryMetrics, binary_metrics, percent_agreement

DEFAULT_CANDIDATES = tuple(round(0.05 * i, 2) for i in range(1, 20))  # 0.05 .. 0.95


@dataclass
class AgreementReport:
    n_matched: int
    unmatched_coded: int
    unmatched_human: int
    per_code: dict[str, BinaryMetrics]
    exact_match_rate: float

    def as_dict(self) -> dict:
        return {
            "n_matched": self.n_matched,
            "unmatched_coded": self.unmatched_coded,
            "unmatched_human": self.unmatched_human,
            "exact_match_rate": self.exact_match_rate,
            "per_code": {code: m.as_dict() for code, m in self.per_code.items()},
        }


def align(coded: CodedFile, human: dict[str, dict[str, int]]) -> tuple[list[CodedRecord], int, int]:
    """Keep the ids present on both sides, in coded-file order; report what was dropped."""
    matched = [r for r in coded.records if r.id in human]
    unmatched_coded = len(coded.records) - len(matched)
    unmatched_human = len(set(human) - coded.ids)
    return matched, unmatched_coded, unmatched_human


def assignments_at(records: list[CodedRecord], code: str, threshold: float | None) -> list[int]:
    """0/1 per record: the stored decision when threshold is None, else re-decided from p_<code>."""
    if threshold is None:
        return [int(r.assigned.get(code, 0)) for r in records]
    return [int(r.probabilities.get(code, 0.0) >= threshold) for r in records]


def compute_agreement(coded: CodedFile, human: dict[str, dict[str, int]], codebook: Codebook, *, use_thresholds: bool = False) -> AgreementReport:
    """Per-code metrics over the matched ids.

    ``use_thresholds=True`` re-decides from probabilities with the codebook's
    thresholds (useful after `tune`); the default trusts the file's 0/1 columns.
    """
    matched, dropped_coded, dropped_human = align(coded, human)
    per_code: dict[str, BinaryMetrics] = {}
    for code in codebook.codes:
        threshold = code.threshold if use_thresholds else None
        pred = assignments_at(matched, code.id, threshold)
        truth = [int(human[r.id].get(code.id, 0)) for r in matched]
        per_code[code.id] = binary_metrics(pred, truth)
    exact = percent_agreement(
        [tuple(assignments_at([r], c.id, c.threshold if use_thresholds else None)[0] for c in codebook.codes) for r in matched],
        [tuple(int(human[r.id].get(c.id, 0)) for c in codebook.codes) for r in matched],
    )
    return AgreementReport(len(matched), dropped_coded, dropped_human, per_code, exact)


@dataclass
class CodeTuning:
    code: str
    current_threshold: float
    tuned_threshold: float
    tune_f1_at_tuned: float
    holdout_current: BinaryMetrics
    holdout_tuned: BinaryMetrics

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "current_threshold": self.current_threshold,
            "tuned_threshold": self.tuned_threshold,
            "tune_f1_at_tuned": self.tune_f1_at_tuned,
            "holdout_at_current": self.holdout_current.as_dict(),
            "holdout_at_tuned": self.holdout_tuned.as_dict(),
        }


@dataclass
class TuneReport:
    seed: int
    n_tune: int
    n_holdout: int
    per_code: list[CodeTuning] = field(default_factory=list)

    @property
    def thresholds(self) -> dict[str, float]:
        return {t.code: t.tuned_threshold for t in self.per_code}

    def as_dict(self) -> dict:
        return {"seed": self.seed, "n_tune": self.n_tune, "n_holdout": self.n_holdout, "per_code": [t.as_dict() for t in self.per_code]}


def split_ids(ids: list[str], seed: int = 42, tune_fraction: float = 0.6) -> tuple[list[str], list[str]]:
    """Random split with a fixed seed so two runs on the same file give the same holdout."""
    if not 0 < tune_fraction < 1:
        raise ValueError("tune_fraction must be in (0, 1)")
    shuffled = sorted(ids)  # sort first so the split does not depend on file order
    random.Random(seed).shuffle(shuffled)
    cut = int(round(len(shuffled) * tune_fraction))
    return shuffled[:cut], shuffled[cut:]


def choose_threshold(records: list[CodedRecord], truth: dict[str, dict[str, int]], code: str, current: float, candidates=DEFAULT_CANDIDATES) -> tuple[float, float]:
    """Pick the candidate maximizing F1 on the given (tuning) records; ties go to the value nearest the current threshold."""
    labels = [int(truth[r.id].get(code, 0)) for r in records]
    best_t, best_f1 = current, float("-inf")
    for t in candidates:
        m = binary_metrics(assignments_at(records, code, t), labels)
        f1 = m.f1 if m.f1 == m.f1 else -1.0  # nan -> worst
        if f1 > best_f1 + 1e-12 or (abs(f1 - best_f1) <= 1e-12 and abs(t - current) < abs(best_t - current)):
            best_t, best_f1 = t, f1
    return best_t, best_f1


def tune_thresholds(coded: CodedFile, human: dict[str, dict[str, int]], codebook: Codebook, *, seed: int = 42, tune_fraction: float = 0.6, candidates=DEFAULT_CANDIDATES) -> TuneReport:
    """Choose thresholds on the tuning split only; report holdout metrics at current and tuned thresholds."""
    matched, _, _ = align(coded, human)
    tune_ids, holdout_ids = split_ids([r.id for r in matched], seed, tune_fraction)
    tune_set, hold_set = set(tune_ids), set(holdout_ids)
    tune_records = [r for r in matched if r.id in tune_set]
    holdout_records = [r for r in matched if r.id in hold_set]
    report = TuneReport(seed, len(tune_records), len(holdout_records))
    for code in codebook.codes:
        tuned, tune_f1 = choose_threshold(tune_records, human, code.id, code.threshold, candidates)
        holdout_truth = [int(human[r.id].get(code.id, 0)) for r in holdout_records]
        report.per_code.append(
            CodeTuning(
                code.id,
                code.threshold,
                tuned,
                tune_f1,
                binary_metrics(assignments_at(holdout_records, code.id, code.threshold), holdout_truth),
                binary_metrics(assignments_at(holdout_records, code.id, tuned), holdout_truth),
            )
        )
    return report

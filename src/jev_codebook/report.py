# Purpose: Descriptive report over a coded CSV: frequencies with Wilson intervals, co-occurrence, most uncertain rows.
"""Reporting helpers (pure functions over CodedFile)."""

from __future__ import annotations

from dataclasses import dataclass

from .datafiles import CodedFile, CodedRecord
from .stats import wilson_interval


@dataclass(frozen=True)
class Frequency:
    code: str
    count: int
    n: int
    proportion: float
    ci95: tuple[float, float]


def frequencies(coded: CodedFile) -> list[Frequency]:
    """Share of responses carrying each code, with a Wilson interval: a frequency without its interval invites over-reading small samples."""
    n = len(coded.records)
    out = []
    for code in coded.code_ids:
        count = sum(r.assigned.get(code, 0) for r in coded.records)
        out.append(Frequency(code, count, n, count / n if n else float("nan"), wilson_interval(count, n)))
    return out


def cooccurrence(coded: CodedFile) -> dict[str, dict[str, int]]:
    """Symmetric matrix: rows carrying both codes (diagonal = code count)."""
    matrix = {a: {b: 0 for b in coded.code_ids} for a in coded.code_ids}
    for r in coded.records:
        present = [c for c in coded.code_ids if r.assigned.get(c, 0)]
        for a in present:
            for b in present:
                matrix[a][b] += 1
    return matrix


def uncertainty(record: CodedRecord, thresholds: dict[str, float] | None) -> float:
    """Distance from the nearest decision boundary; smaller means more uncertain."""
    return min(abs(record.probabilities.get(c, 0.0) - (thresholds or {}).get(c, 0.5)) for c in record.probabilities) if record.probabilities else 1.0


def top_uncertain(coded: CodedFile, thresholds: dict[str, float] | None = None, limit: int = 10) -> list[tuple[CodedRecord, float]]:
    scored = [(r, uncertainty(r, thresholds)) for r in coded.records]
    scored.sort(key=lambda pair: (pair[1], pair[0].id))
    return scored[:limit]

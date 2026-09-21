# Purpose: Read response files (CSV/JSONL), read and write coded CSVs and human label files, support resume.
"""File formats.

Coded CSV columns: ``id, text, <code>..., p_<code>..., review, request_id``.
Human label CSV: ``id`` plus either one 0/1 column per code or a ``codes``
column with ``;``-separated code ids. Both layouts are accepted because
research teams export from very different tools.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

REVIEW_COLUMN = "review"
REQUEST_COLUMN = "request_id"


class DataError(ValueError):
    """Input file problem (missing column, duplicate id, unparsable row)."""


@dataclass(frozen=True)
class Response:
    id: str
    text: str


@dataclass
class ReadResult:
    responses: list[Response]
    skipped_blank: int = 0


def read_responses(path: str, *, id_column: str = "id", text_column: str = "text") -> ReadResult:
    """Read CSV (by default) or JSONL (``.jsonl``/``.ndjson``) with an id and a text column.

    Blank texts are skipped and counted rather than coded: an empty answer has
    nothing for the model to judge, and coding it would only inflate 'none'.
    Duplicate ids are an error because resume and agreement key on them.
    """
    rows: Iterable[dict[str, Any]]
    lower = path.lower()
    if lower.endswith((".jsonl", ".ndjson")):
        rows = _read_jsonl(path)
    else:
        rows = _read_csv(path)
    responses: list[Response] = []
    seen: set[str] = set()
    skipped = 0
    for index, row in enumerate(rows, start=1):
        if id_column not in row or text_column not in row:
            raise DataError(f"{path}: row {index} lacks column {id_column!r} or {text_column!r} (columns: {sorted(row)})")
        rid = str(row[id_column]).strip()
        text = str(row[text_column] if row[text_column] is not None else "").strip()
        if not rid:
            raise DataError(f"{path}: row {index} has an empty id")
        if rid in seen:
            raise DataError(f"{path}: duplicate id {rid!r} at row {index}")
        seen.add(rid)
        if not text:
            skipped += 1
            continue
        responses.append(Response(rid, text))
    return ReadResult(responses, skipped)


def _read_csv(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise DataError(f"{path}: empty CSV")
        return [dict(row) for row in reader]


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as err:
                raise DataError(f"{path}: line {number} is not valid JSON: {err}") from None
            if not isinstance(obj, dict):
                raise DataError(f"{path}: line {number} is not a JSON object")
            rows.append(obj)
    return rows


def coded_columns(code_ids: list[str]) -> list[str]:
    return ["id", "text", *code_ids, *[f"p_{c}" for c in code_ids], REVIEW_COLUMN, REQUEST_COLUMN]


@dataclass
class CodedRecord:
    """One row of a coded CSV, independent of how it was produced."""

    id: str
    text: str
    assigned: dict[str, int]
    probabilities: dict[str, float]
    review: bool
    request_id: str = ""
    extra: dict[str, str] = field(default_factory=dict)


class CodedWriter:
    """Append-only CSV writer; header is written once when the file is new or empty.

    Rows are flushed as they complete so an interrupted run keeps its
    progress and ``--out`` doubles as the resume journal.
    """

    def __init__(self, path: str, code_ids: list[str]):
        self.path = path
        self.code_ids = list(code_ids)
        exists = os.path.exists(path) and os.path.getsize(path) > 0
        if exists:
            existing = read_coded(path)
            if existing.code_ids != self.code_ids:
                raise DataError(f"{path} was coded with codes {existing.code_ids}, not {self.code_ids}; use a new --out file")
        self._fh = open(path, "a", encoding="utf-8", newline="")
        self._writer = csv.writer(self._fh)
        if not exists:
            self._writer.writerow(coded_columns(self.code_ids))
            self._fh.flush()

    def write(self, record: CodedRecord) -> None:
        row = [record.id, record.text]
        row += [int(record.assigned.get(c, 0)) for c in self.code_ids]
        row += [f"{float(record.probabilities.get(c, 0.0)):.4f}" for c in self.code_ids]
        row += [int(bool(record.review)), record.request_id]
        self._writer.writerow(row)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "CodedWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@dataclass
class CodedFile:
    code_ids: list[str]
    records: list[CodedRecord]

    @property
    def ids(self) -> set[str]:
        return {r.id for r in self.records}


def read_coded(path: str) -> CodedFile:
    """Parse a coded CSV; code ids are inferred from the ``p_<code>`` columns."""
    rows = _read_csv(path)
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh), [])
    code_ids = [h[2:] for h in header if h.startswith("p_")]
    missing = [c for c in code_ids if c not in header]
    if not code_ids or missing:
        raise DataError(f"{path}: not a coded CSV (need <code> and p_<code> columns; missing {missing})")
    records = []
    for index, row in enumerate(rows, start=2):
        try:
            records.append(
                CodedRecord(
                    id=str(row["id"]).strip(),
                    text=row.get("text", "") or "",
                    assigned={c: int(float(row[c])) for c in code_ids},
                    probabilities={c: float(row[f"p_{c}"]) for c in code_ids},
                    review=_truthy(row.get(REVIEW_COLUMN, "0")),
                    request_id=row.get(REQUEST_COLUMN, "") or "",
                )
            )
        except (KeyError, ValueError) as err:
            raise DataError(f"{path}: line {index}: {err}") from None
    return CodedFile(code_ids, records)


def read_human_labels(path: str, code_ids: list[str]) -> dict[str, dict[str, int]]:
    """Read human labels as {id: {code: 0/1}} from either per-code columns or a ``codes`` column."""
    rows = _read_csv(path)
    labels: dict[str, dict[str, int]] = {}
    for index, row in enumerate(rows, start=2):
        rid = str(row.get("id", "")).strip()
        if not rid:
            raise DataError(f"{path}: line {index} has no id")
        if rid in labels:
            raise DataError(f"{path}: duplicate id {rid!r} at line {index}")
        if "codes" in row and not all(c in row for c in code_ids):
            chosen = {c.strip() for c in (row["codes"] or "").split(";") if c.strip()}
            unknown = chosen - set(code_ids)
            if unknown:
                raise DataError(f"{path}: line {index} uses unknown codes {sorted(unknown)}")
            labels[rid] = {c: int(c in chosen) for c in code_ids}
        else:
            missing = [c for c in code_ids if c not in row]
            if missing:
                raise DataError(f"{path}: missing label columns {missing} (or a 'codes' column)")
            labels[rid] = {c: int(_truthy(row[c])) for c in code_ids}
    return labels


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "x"}

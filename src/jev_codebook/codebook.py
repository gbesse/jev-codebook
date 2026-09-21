# Purpose: Codebook schema, validation, question construction and chunking (pure, no network).
"""Codebook model.

The codebook is the researcher's contract with the model. Validation is
strict and reports every problem at once, because a silently accepted typo
(``treshold``) would change every coded row without anyone noticing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_CODES_PER_REQUEST = 40
NONE_OPTION = "none_of_these"
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DEFAULT_THRESHOLD = 0.7
DEFAULT_REVIEW_BAND = (0.4, 0.7)


class CodebookError(ValueError):
    """Raised with a list of every validation problem found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid codebook:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class Code:
    id: str
    label: str
    definition: str
    include_examples: tuple[str, ...] = ()
    exclude_examples: tuple[str, ...] = ()
    threshold: float = DEFAULT_THRESHOLD


@dataclass(frozen=True)
class Codebook:
    name: str
    version: str
    codes: tuple[Code, ...]
    language: str = "en"
    mode: str = "multi"
    review_band: tuple[float, float] = DEFAULT_REVIEW_BAND
    source: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def code_ids(self) -> list[str]:
        return [c.id for c in self.codes]

    def code(self, code_id: str) -> Code:
        for c in self.codes:
            if c.id == code_id:
                return c
        raise KeyError(code_id)

    def with_thresholds(self, thresholds: dict[str, float]) -> "Codebook":
        """Return a copy with replaced per-code thresholds (used by `tune`)."""
        codes = tuple(
            Code(c.id, c.label, c.definition, c.include_examples, c.exclude_examples, float(thresholds.get(c.id, c.threshold)))
            for c in self.codes
        )
        return Codebook(self.name, self.version, codes, self.language, self.mode, self.review_band, self.source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "language": self.language,
            "mode": self.mode,
            "codes": [
                {
                    "id": c.id,
                    "label": c.label,
                    "definition": c.definition,
                    "include_examples": list(c.include_examples),
                    "exclude_examples": list(c.exclude_examples),
                    "threshold": c.threshold,
                }
                for c in self.codes
            ],
            "review_band": list(self.review_band),
        }


def _is_prob(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0


def _str_list(value: Any, where: str, problems: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        problems.append(f"{where} must be a list of non-empty strings")
        return ()
    return tuple(x.strip() for x in value)


def validate_codebook(data: Any) -> Codebook:
    """Validate a parsed JSON codebook; raise CodebookError listing every problem."""
    problems: list[str] = []
    if not isinstance(data, dict):
        raise CodebookError(["codebook must be a JSON object"])
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("'name' must be a non-empty string")
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        problems.append("'version' must be a non-empty string")
    language = data.get("language", "en")
    if not isinstance(language, str) or not language.strip():
        problems.append("'language' must be a string (e.g. 'en')")
    mode = data.get("mode", "multi")
    if mode not in ("multi", "single"):
        problems.append("'mode' must be 'multi' or 'single'")
    band_raw = data.get("review_band", list(DEFAULT_REVIEW_BAND))
    band = DEFAULT_REVIEW_BAND
    if not (isinstance(band_raw, list) and len(band_raw) == 2 and all(_is_prob(x) for x in band_raw) and band_raw[0] < band_raw[1]):
        problems.append("'review_band' must be [low, high] with 0 <= low < high <= 1")
    else:
        band = (float(band_raw[0]), float(band_raw[1]))
    codes_raw = data.get("codes")
    codes: list[Code] = []
    if not isinstance(codes_raw, list) or not codes_raw:
        problems.append("'codes' must be a non-empty list")
        codes_raw = []
    seen: set[str] = set()
    for index, raw in enumerate(codes_raw):
        where = f"codes[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{where} must be an object")
            continue
        cid = raw.get("id")
        if not isinstance(cid, str) or not _ID_RE.match(cid):
            problems.append(f"{where}.id must match ^[a-z][a-z0-9_]{{0,63}}$ (got {cid!r})")
        elif cid == NONE_OPTION:
            problems.append(f"{where}.id '{NONE_OPTION}' is reserved for single mode")
        elif cid in seen:
            problems.append(f"{where}.id {cid!r} is duplicated")
        else:
            seen.add(cid)
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            problems.append(f"{where}.label must be a non-empty string")
        definition = raw.get("definition")
        if not isinstance(definition, str) or not definition.strip():
            problems.append(f"{where}.definition must be a non-empty string")
        include = _str_list(raw.get("include_examples"), f"{where}.include_examples", problems)
        exclude = _str_list(raw.get("exclude_examples"), f"{where}.exclude_examples", problems)
        threshold = raw.get("threshold", DEFAULT_THRESHOLD)
        if not _is_prob(threshold) or threshold == 0:
            problems.append(f"{where}.threshold must be a number in (0, 1]")
            threshold = DEFAULT_THRESHOLD
        unknown = set(raw) - {"id", "label", "definition", "include_examples", "exclude_examples", "threshold", "notes"}
        if unknown:
            problems.append(f"{where} has unknown fields: {sorted(unknown)}")
        codes.append(Code(str(cid), str(label).strip() if isinstance(label, str) else "", str(definition).strip() if isinstance(definition, str) else "", include, exclude, float(threshold)))
    unknown_top = set(data) - {"name", "version", "language", "mode", "codes", "review_band", "description", "_comment"}
    if unknown_top:
        problems.append(f"unknown top-level fields: {sorted(unknown_top)}")
    if problems:
        raise CodebookError(problems)
    return Codebook(name.strip(), version.strip(), tuple(codes), language.strip(), mode, band, dict(data))


def load_codebook(path: str) -> Codebook:
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as err:
            raise CodebookError([f"{path} is not valid JSON: {err}"]) from None
    return validate_codebook(data)


def chunk_codes(codes: list[Code] | tuple[Code, ...], max_per_request: int = MAX_CODES_PER_REQUEST) -> list[list[Code]]:
    """Split codes into request-sized groups (fan-out cap per request)."""
    if max_per_request < 1:
        raise ValueError("max_per_request must be >= 1")
    codes = list(codes)
    return [codes[i : i + max_per_request] for i in range(0, len(codes), max_per_request)] or [[]]


def build_state(text: str) -> dict[str, str]:
    """State is the response text alone: ids, timestamps and metadata are irrelevant to the judgment and hurt accuracy."""
    return {"response": text}


def build_questions(codebook: Codebook, codes: list[Code] | tuple[Code, ...] | None = None) -> dict[str, Any]:
    """Build the typed questions for one request.

    Multi mode: one noul per code, independent, so a response can carry
    several codes. Single mode: one choice over all codes plus
    ``none_of_these`` so the model is never forced to pick a code.
    """
    chosen = list(codes if codes is not None else codebook.codes)
    if codebook.mode == "multi":
        return {c.id: _noul_question(c) for c in chosen}
    criteria: dict[str, Any] = {
        c.id: {"what": c.definition, "examples": list(c.include_examples)} for c in chosen
    }
    criteria[NONE_OPTION] = "The response expresses none of the listed codes."
    return {
        "code": {
            "type": "choice",
            "instructions": "Which single code best describes what this response expresses?",
            "criteria": criteria,
        }
    }


def _noul_question(code: Code) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": f"Does this response express the code '{code.label}'?",
        "criteria": {
            "true": {"what": code.definition, "examples": list(code.include_examples)},
            "false": {
                "what": f"The response does not express '{code.label}': it is about something else, or only mentions a related topic without expressing it.",
                "examples": list(code.exclude_examples),
            },
        },
    }

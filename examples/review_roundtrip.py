"""Synthetic human-review round trip; no network or model calls."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_codebook.client import FakeJev
from jev_codebook.codebook import load_codebook
from jev_codebook.coder import code_responses
from jev_codebook.datafiles import CodedFile, CodedRecord, read_responses
from jev_codebook.review import export_review_queue, apply_review_decisions
import json

book = load_codebook(str(ROOT / "examples/support_codebook.json"))
source = read_responses(str(ROOT / "examples/support_responses.csv")).responses
rows = code_responses(
    source, book, FakeJev.from_file(str(ROOT / "examples/support_fixtures.json"))
).rows
coded = CodedFile(
    book.code_ids,
    [
        CodedRecord(r.id, r.text, r.assigned, r.probabilities, r.review, r.request_id)
        for r in rows
    ],
)
queue = export_review_queue(coded, book)
assert len(queue["decisions"]) == 1
# This is an explicit synthetic human annotation, not the model's suggested label.
queue["decisions"][0]["codes"] = ["feature"]
reviewed, audit = apply_review_decisions(coded, book, queue)
assert sum(r.review for r in reviewed.records) == 0
assert reviewed.records[3].assigned["feature"] == 1
assert reviewed.records[3].probabilities == coded.records[3].probabilities
assert coded.records[3].review is True
print(
    json.dumps(
        {
            "source": {
                "fr": "Annotation humaine simulée, aucun appel Jev.",
                "en": "Simulated human annotation, no Jev call.",
                "es": "Anotación humana simulada, sin llamadas Jev.",
            },
            "pending_before": sum(r.review for r in coded.records),
            "pending_after": sum(r.review for r in reviewed.records),
            "reviewed_rows": len(audit["changes"]),
            "probabilities_preserved": True,
        },
        ensure_ascii=False,
    )
)

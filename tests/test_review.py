import contextlib
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from jev_codebook.codebook import Code, Codebook
from jev_codebook.datafiles import CodedFile, CodedRecord
from jev_codebook.review import (
    ReviewError,
    apply_review_decisions,
    export_review_queue,
    main,
)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.book = Codebook(
            "test",
            "1",
            (Code("bug", "Bug", "bug"), Code("billing", "Billing", "billing")),
            mode="single",
        )
        self.coded = CodedFile(
            ["bug", "billing"],
            [
                CodedRecord(
                    "pending",
                    "Texte utilisateur original, avec accents é",
                    {"bug": 0, "billing": 0},
                    {"bug": 0.6, "billing": 0.4},
                    True,
                    "old-request",
                ),
                CodedRecord(
                    "accepted",
                    "Original accepted",
                    {"bug": 1, "billing": 0},
                    {"bug": 0.9, "billing": 0.1},
                    False,
                    "accepted-request",
                ),
            ],
        )

    def decision(self, codes):
        queue = export_review_queue(self.coded, self.book, include_text=True)
        queue["decisions"][0]["codes"] = codes
        return queue

    def test_explicit_labels_resolve_only_pending_rows_without_mutating_model_data(
        self,
    ):
        result, audit = apply_review_decisions(
            self.coded, self.book, self.decision(["billing"])
        )
        self.assertEqual(result.records[0].assigned, {"bug": 0, "billing": 1})
        self.assertFalse(result.records[0].review)
        self.assertEqual(result.records[0].text, self.coded.records[0].text)
        self.assertEqual(
            result.records[0].probabilities, self.coded.records[0].probabilities
        )
        self.assertEqual(result.records[1], self.coded.records[1])
        self.assertTrue(self.coded.records[0].review)
        self.assertEqual(audit["changes"][0]["origin"], "human_review")
        self.assertNotIn("Texte utilisateur", json.dumps(audit))

    def test_empty_selection_is_explicit_abstention_but_null_is_unreviewed(self):
        result, _ = apply_review_decisions(self.coded, self.book, self.decision([]))
        self.assertEqual(result.records[0].assigned, {"bug": 0, "billing": 0})
        with self.assertRaises(ReviewError):
            apply_review_decisions(
                self.coded, self.book, export_review_queue(self.coded, self.book)
            )

    def test_stale_text_probabilities_and_codebook_are_rejected(self):
        queue = self.decision(["bug"])
        for attr, value in [
            ("text", "changed"),
            ("probabilities", {"bug": 0.7, "billing": 0.3}),
            ("request_id", "new-request"),
        ]:
            changed = copy.deepcopy(self.coded)
            setattr(changed.records[0], attr, value)
            with self.assertRaises(ReviewError):
                apply_review_decisions(changed, self.book, queue)
        changed_book = Codebook("test", "2", self.book.codes, mode="single")
        with self.assertRaises(ReviewError):
            apply_review_decisions(self.coded, changed_book, queue)

    def test_unknown_duplicate_and_single_mode_conflicts_are_rejected(self):
        for codes in [["unknown"], ["bug", "bug"], ["bug", "billing"]]:
            with self.assertRaises(ReviewError):
                apply_review_decisions(self.coded, self.book, self.decision(codes))
        queue = self.decision(["bug"])
        queue["decisions"].append(copy.deepcopy(queue["decisions"][0]))
        with self.assertRaises(ReviewError):
            apply_review_decisions(self.coded, self.book, queue)

    def test_multi_mode_accepts_multiple_labels_and_invalid_batch_is_atomic(self):
        book = Codebook("test", "1", self.book.codes, mode="multi")
        queue = export_review_queue(self.coded, book)
        queue["decisions"][0]["codes"] = ["bug", "billing"]
        result, _ = apply_review_decisions(self.coded, book, queue)
        self.assertEqual(result.records[0].assigned, {"bug": 1, "billing": 1})
        queue["decisions"].append({"id": "unknown", "codes": []})
        with self.assertRaises(ReviewError):
            apply_review_decisions(self.coded, book, queue)
        self.assertTrue(self.coded.records[0].review)
        self.assertEqual(self.coded.records[0].assigned, {"bug": 0, "billing": 0})

    def test_export_omits_text_unless_requested_and_preserves_original_language(self):
        self.assertNotIn(
            "text", export_review_queue(self.coded, self.book)["decisions"][0]
        )
        self.assertEqual(
            export_review_queue(self.coded, self.book, include_text=True)["decisions"][
                0
            ]["text"],
            self.coded.records[0].text,
        )

    def test_csv_cli_round_trip_preserves_extra_columns_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, book = base / "source.csv", base / "book.json"
            book.write_text(json.dumps(self.book.to_dict()), encoding="utf-8")
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "id",
                        "text",
                        "bug",
                        "billing",
                        "p_bug",
                        "p_billing",
                        "review",
                        "request_id",
                        "user_note",
                    ]
                )
                writer.writerow(
                    [
                        "pending",
                        self.coded.records[0].text,
                        0,
                        0,
                        ".6000",
                        ".4000",
                        1,
                        "old-request",
                        "User metadata unchanged",
                    ]
                )
            for lang in ("fr", "en", "es"):
                queue, out, audit = (
                    base / (lang + ".json"),
                    base / (lang + ".csv"),
                    base / (lang + "-audit.json"),
                )
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(
                        main(
                            [
                                "export",
                                str(source),
                                "--codebook",
                                str(book),
                                "--out",
                                str(queue),
                                "--lang",
                                lang,
                            ]
                        ),
                        0,
                    )
                    d = json.loads(queue.read_text())
                    d["decisions"][0]["codes"] = ["billing"]
                    queue.write_text(json.dumps(d), encoding="utf-8")
                    args = [
                        "apply",
                        str(source),
                        "--codebook",
                        str(book),
                        "--decisions",
                        str(queue),
                        "--out",
                        str(out),
                        "--audit",
                        str(audit),
                        "--lang",
                        lang,
                    ]
                    self.assertEqual(main(args), 0)
                    self.assertEqual(main(args), 1)
                with out.open(newline="", encoding="utf-8") as stream:
                    row = next(csv.DictReader(stream))
                self.assertEqual(row["billing"], "1")
                self.assertEqual(row["review"], "0")
                self.assertEqual(row["p_bug"], ".6000")
                self.assertEqual(row["user_note"], "User metadata unchanged")
                self.assertEqual(row["text"], self.coded.records[0].text)
                self.assertEqual(out.stat().st_mode & 0o777, 0o600)
                self.assertEqual(audit.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()

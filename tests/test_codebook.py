# Purpose: Codebook validation errors, question construction and chunking beyond 40 codes.
import json
import os
import tempfile
import unittest

from helpers import small_codebook
from jev_codebook.codebook import MAX_CODES_PER_REQUEST, NONE_OPTION, CodebookError, build_questions, chunk_codes, load_codebook, validate_codebook


def base():
    return {
        "name": "cb",
        "version": "1",
        "mode": "multi",
        "codes": [{"id": "praise", "label": "Praise", "definition": "Says something positive.", "threshold": 0.7}],
        "review_band": [0.4, 0.7],
    }


class ValidationTests(unittest.TestCase):
    def assert_problem(self, data, fragment):
        with self.assertRaises(CodebookError) as ctx:
            validate_codebook(data)
        self.assertTrue(any(fragment in p for p in ctx.exception.problems), ctx.exception.problems)

    def test_valid(self):
        cb = validate_codebook(base())
        self.assertEqual(cb.code_ids, ["praise"])
        self.assertEqual(cb.review_band, (0.4, 0.7))
        self.assertEqual(cb.language, "en")

    def test_missing_name_and_codes(self):
        self.assert_problem({"version": "1", "codes": []}, "'name'")
        self.assert_problem({"name": "x", "version": "1", "codes": []}, "'codes'")

    def test_bad_mode(self):
        d = base(); d["mode"] = "both"
        self.assert_problem(d, "'mode'")

    def test_duplicate_and_reserved_ids(self):
        d = base(); d["codes"].append(dict(d["codes"][0]))
        self.assert_problem(d, "duplicated")
        d = base(); d["codes"][0]["id"] = NONE_OPTION
        self.assert_problem(d, "reserved")
        d = base(); d["codes"][0]["id"] = "Bad Id"
        self.assert_problem(d, "codes[0].id")

    def test_threshold_and_band(self):
        d = base(); d["codes"][0]["threshold"] = 1.5
        self.assert_problem(d, "threshold")
        d = base(); d["review_band"] = [0.8, 0.2]
        self.assert_problem(d, "review_band")

    def test_unknown_fields_are_reported(self):
        d = base(); d["codes"][0]["treshold"] = 0.5
        self.assert_problem(d, "unknown fields")
        d = base(); d["thresholds"] = {}
        self.assert_problem(d, "unknown top-level")

    def test_all_problems_reported_at_once(self):
        d = base(); d["mode"] = "x"; d["codes"][0]["label"] = ""
        with self.assertRaises(CodebookError) as ctx:
            validate_codebook(d)
        self.assertGreaterEqual(len(ctx.exception.problems), 2)

    def test_load_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cb.json")
            with open(path, "w") as fh:
                fh.write("{not json")
            with self.assertRaises(CodebookError):
                load_codebook(path)
            with open(path, "w") as fh:
                json.dump(base(), fh)
            self.assertEqual(load_codebook(path).name, "cb")

    def test_roundtrip_and_thresholds(self):
        cb = validate_codebook(base())
        tuned = cb.with_thresholds({"praise": 0.55})
        self.assertEqual(tuned.code("praise").threshold, 0.55)
        self.assertEqual(validate_codebook(tuned.to_dict()).code("praise").threshold, 0.55)


class QuestionTests(unittest.TestCase):
    def test_multi_mode_one_noul_per_code(self):
        cb = small_codebook("multi", 3)
        q = build_questions(cb)
        self.assertEqual(list(q), ["code1", "code2", "code3"])
        one = q["code1"]
        self.assertEqual(one["type"], "noul")
        self.assertEqual(one["instructions"], "Does this response express the code 'Code 1'?")
        self.assertEqual(one["criteria"]["true"], {"what": "Definition of code 1.", "examples": ["example 1"]})
        self.assertEqual(one["criteria"]["false"]["examples"], ["counter 1"])
        self.assertIn("does not express 'Code 1'", one["criteria"]["false"]["what"])

    def test_single_mode_choice_with_none(self):
        cb = small_codebook("single", 2)
        q = build_questions(cb)
        self.assertEqual(list(q), ["code"])
        self.assertEqual(q["code"]["type"], "choice")
        self.assertEqual(list(q["code"]["criteria"]), ["code1", "code2", NONE_OPTION])
        self.assertEqual(q["code"]["criteria"]["code1"]["what"], "Definition of code 1.")

    def test_chunking_beyond_cap(self):
        cb = small_codebook("multi", 45)
        chunks = chunk_codes(cb.codes)
        self.assertEqual([len(c) for c in chunks], [MAX_CODES_PER_REQUEST, 5])
        self.assertEqual(chunks[1][0].id, "code41")
        self.assertEqual(len(build_questions(cb, chunks[0])), 40)
        with self.assertRaises(ValueError):
            chunk_codes(cb.codes, 0)


if __name__ == "__main__":
    unittest.main()

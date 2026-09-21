# Purpose: Input parsing (CSV/JSONL), coded CSV round trip, human label layouts, resume behavior.
import csv
import json
import os
import tempfile
import unittest

from jev_codebook.datafiles import CodedRecord, CodedWriter, DataError, read_coded, read_human_labels, read_responses


class ReadResponsesTests(unittest.TestCase):
    def write(self, tmp, name, rows, header=("id", "text")):
        path = os.path.join(tmp, name)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(header); w.writerows(rows)
        return path

    def test_csv_and_blank_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "r.csv", [("1", "a"), ("2", "  "), ("3", "c, with \"quotes\"")])
            res = read_responses(path)
            self.assertEqual([r.id for r in res.responses], ["1", "3"])
            self.assertEqual(res.responses[1].text, 'c, with "quotes"')
            self.assertEqual(res.skipped_blank, 1)

    def test_custom_columns_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "r.csv", [("1", "a")], header=("ref", "answer"))
            self.assertEqual(read_responses(path, id_column="ref", text_column="answer").responses[0].text, "a")
            with self.assertRaisesRegex(DataError, "lacks column"):
                read_responses(path)

    def test_duplicate_and_empty_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(DataError, "duplicate id"):
                read_responses(self.write(tmp, "d.csv", [("1", "a"), ("1", "b")]))
            with self.assertRaisesRegex(DataError, "empty id"):
                read_responses(self.write(tmp, "e.csv", [("", "a")]))

    def test_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.jsonl")
            with open(path, "w") as fh:
                fh.write(json.dumps({"id": 7, "text": "seven"}) + "\n\n" + json.dumps({"id": "8", "text": "eight"}) + "\n")
            self.assertEqual([r.id for r in read_responses(path).responses], ["7", "8"])
            with open(path, "a") as fh:
                fh.write("not json\n")
            with self.assertRaises(DataError):
                read_responses(path)


class CodedRoundTripTests(unittest.TestCase):
    def test_write_then_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "coded.csv")
            with CodedWriter(path, ["a", "b"]) as w:
                w.write(CodedRecord("1", "hello, world", {"a": 1, "b": 0}, {"a": 0.91234, "b": 0.1}, True, "abc"))
                w.write(CodedRecord("2", "x", {"a": 0, "b": 1}, {"a": 0.2, "b": 0.8}, False, "def"))
            coded = read_coded(path)
            self.assertEqual(coded.code_ids, ["a", "b"])
            self.assertEqual(coded.records[0].text, "hello, world")
            self.assertEqual(coded.records[0].assigned, {"a": 1, "b": 0})
            self.assertAlmostEqual(coded.records[0].probabilities["a"], 0.9123)
            self.assertTrue(coded.records[0].review)
            self.assertFalse(coded.records[1].review)
            self.assertEqual(coded.ids, {"1", "2"})
            # Appending keeps the header once and refuses a different code set.
            with CodedWriter(path, ["a", "b"]) as w:
                w.write(CodedRecord("3", "y", {"a": 0, "b": 0}, {"a": 0.0, "b": 0.0}, False, ""))
            self.assertEqual(len(read_coded(path).records), 3)
            with self.assertRaisesRegex(DataError, "coded with codes"):
                CodedWriter(path, ["a"])

    def test_not_a_coded_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.csv")
            with open(path, "w") as fh:
                fh.write("id,text\n1,a\n")
            with self.assertRaises(DataError):
                read_coded(path)


class HumanLabelTests(unittest.TestCase):
    def test_column_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.csv")
            with open(path, "w") as fh:
                fh.write("id,a,b\n1,1,0\n2,yes,TRUE\n")
            labels = read_human_labels(path, ["a", "b"])
            self.assertEqual(labels, {"1": {"a": 1, "b": 0}, "2": {"a": 1, "b": 1}})
            with self.assertRaisesRegex(DataError, "missing label columns"):
                read_human_labels(path, ["a", "c"])

    def test_codes_column_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.csv")
            with open(path, "w") as fh:
                fh.write("id,codes\n1,a;b\n2,\n3,zzz\n")
            with self.assertRaisesRegex(DataError, "unknown codes"):
                read_human_labels(path, ["a", "b"])
            with open(path, "w") as fh:
                fh.write("id,codes\n1,a;b\n2,\n")
            self.assertEqual(read_human_labels(path, ["a", "b"]), {"1": {"a": 1, "b": 1}, "2": {"a": 0, "b": 0}})


if __name__ == "__main__":
    unittest.main()

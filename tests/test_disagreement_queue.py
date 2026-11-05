import unittest
from jev_codebook.datafiles import CodedFile,CodedRecord
from jev_codebook.report import disagreement_queue
class DisagreementTests(unittest.TestCase):
 def fixture(self):return CodedFile(['a','b'],[CodedRecord('x','synthetic',{'a':1,'b':0},{'a':.9,'b':.1},False)])
 def test_partial_human_labels_not_negative(self):
  x=disagreement_queue(self.fixture(),{'x':{'a':0}})[0];self.assertEqual(x['disagreements'],['a']);self.assertEqual(x['unjudged_codes'],['b'])
 def test_unknown_record(self):
  with self.assertRaises(ValueError):disagreement_queue(self.fixture(),{'other':{'a':1}})
 def test_empty_human(self):self.assertEqual(disagreement_queue(self.fixture(),{})[0]['human_codes_compared'],0)

import unittest,copy,math
from jev_codebook.prevalence import assignment_prevalence_bounds
class Prevalence(unittest.TestCase):
 def test_pending_assignments_do_not_become_negative(self):
  x=assignment_prevalence_bounds([{'id':'a','review':False,'assigned':{'x':1}},{'id':'b','review':True,'assigned':{'x':0}}],['x'])['codes'][0];self.assertEqual(x['fraction_bounds'],[.5,1]);self.assertEqual(x['known_negative_assignments'],0)
 def test_omitted_code_is_unknown(self):
  x=assignment_prevalence_bounds([{'id':'a','review':False,'assigned':{}}],['x']);self.assertEqual(x['codes'][0]['unknown_assignments'],1)
 def test_duplicate_id(self):
  with self.assertRaises(ValueError):assignment_prevalence_bounds([{'id':'a','review':False,'assigned':{}}]*2,['x'])

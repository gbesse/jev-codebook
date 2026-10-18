import threading
from concurrent.futures import ThreadPoolExecutor as RealPool
from unittest.mock import patch
import unittest
from helpers import small_codebook
from jev_codebook.client import FakeJev, JevError
from jev_codebook.coder import code_responses
from jev_codebook.datafiles import Response

class WorkAdmissionTests(unittest.TestCase):
 def test_duplicate_and_invalid_ids_preflight_before_calls(self):
  for rows in [[Response('same','a'),Response('same','b')],[Response('','a')]]:
   fake=FakeJev({})
   with self.assertRaises(ValueError):code_responses(rows,small_codebook(),fake)
   self.assertEqual(fake.calls,[])
 def test_concurrency_is_bounded_before_calls(self):
  for value in [True,0,65,1.5]:
   fake=FakeJev({})
   with self.assertRaises(ValueError):code_responses([Response('id','a')],small_codebook(),fake,concurrency=value)
   self.assertEqual(fake.calls,[])
 def test_failure_starts_no_queued_rows_and_waits_for_inflight_work(self):
  first=threading.Event();second=threading.Event();release=threading.Event();calls=[];base=FakeJev({})
  class Provider:
   model=base.model
   def ask(self,state,questions):
    calls.append(state['response'])
    if state['response']=='0':
     first.set()
     if not second.wait(2):raise AssertionError('second gate missing')
     raise JevError('synthetic failure')
    second.set()
    if not first.wait(2):raise AssertionError('first gate missing')
    release.wait(2)
    return base.ask(state,questions)
  failure_observed=threading.Event()
  class TrackingPool(RealPool):
   def submit(self,*args,**kwargs):
    future=super().submit(*args,**kwargs)
    future.add_done_callback(lambda f: failure_observed.set() if not f.cancelled() and isinstance(f.exception(),JevError) else None)
    return future
  with RealPool(max_workers=1) as caller, patch('jev_codebook.coder.ThreadPoolExecutor',TrackingPool):
   task=caller.submit(code_responses,[Response(str(i),str(i)) for i in range(100)],small_codebook(),Provider(),concurrency=2)
   try:
    self.assertTrue(failure_observed.wait(2))
    release.set()
    with self.assertRaisesRegex(JevError,'synthetic failure'):task.result(timeout=2)
   finally:release.set()
  self.assertEqual(set(calls),{'0','1'})
 def test_callback_mutation_does_not_rewrite_pending_inputs_or_result_order(self):
  rows=[Response('a','original-a'),Response('b','original-b')];base=FakeJev({})
  class Provider:
   model=base.model
   def ask(self,state,questions):rows[1]=Response('replacement','rewritten');return base.ask(state,questions)
  result=code_responses(rows,small_codebook(),Provider(),concurrency=1)
  self.assertEqual([r.text for r in result.rows],['original-a','original-b'])
  self.assertEqual([r.id for r in result.rows],['a','b'])

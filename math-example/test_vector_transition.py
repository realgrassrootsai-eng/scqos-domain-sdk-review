import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from vector_transition import Store, VectorAdapter, Update, scenarios

class VectorTests(unittest.TestCase):
    def test_scenarios(self):
        rows = list(scenarios())
        self.assertEqual(len(rows),9)
        for row in rows:
            with self.subTest(scenario=row['scenario']):
                receipt = row['receipt']
                if row['scenario']=='valid':
                    self.assertEqual(receipt['decision'],'PERMIT')
                    self.assertEqual(receipt['kernel_decision'],'PERMIT')
                    self.assertEqual(receipt['effect_status'],'VERIFIED_EFFECT')
                    self.assertEqual(receipt['observed_after'],dict(x=4,y=6,revision=1))
                    self.assertEqual(row['writer_calls_this_attempt'],1)
                else:
                    self.assertEqual(receipt['decision'],'HOLD')
                    self.assertFalse(receipt['writer_invoked'])
                    self.assertEqual(row['writer_calls_this_attempt'],0)
                    if row['scenario']!='atomic_competing_change':
                        self.assertEqual(receipt['observed_after'],row['state_before_attempt'])
                if row['scenario']=='atomic_competing_change':
                    self.assertEqual(receipt['kernel_decision'],'PERMIT')
                    self.assertEqual(receipt['observed_after'],dict(x=5,y=5,revision=1))
    def test_duplicate_race(self):
        store=Store(); adapter=VectorAdapter(store); request=Update('race',2)
        approval=adapter.issue_approval(request); barrier=Barrier(2)
        def kernel(prepared):
            result=adapter.kernel(prepared); barrier.wait(timeout=5); return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:adapter.execute(request,approval,kernel),range(2)))
        self.assertEqual(sorted(r.decision for r in results),['HOLD','PERMIT'])
        self.assertEqual(store.writer_count,1)
        self.assertEqual(store.read(),dict(x=4,y=6,revision=1))
    def test_integer_domain(self):
        for k in [True,1.5,float('nan'),'2']:
            with self.subTest(k=k),self.assertRaises(ValueError): Update('bad',k)

if __name__=='__main__': unittest.main()

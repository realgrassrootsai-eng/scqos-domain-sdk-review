"""Maintainer tests against the installed wheel, not bundled source imports."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier
import sys
import pytest
import scqos_domain_sdk
from scqos_domain_sdk import execute_governed_transition
from governed_transition import TransitionDecision

ROOT = Path(__file__).resolve().parents[1]

def load_module(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

vector = load_module('extension_vector', ROOT/'math-example/vector_transition.py')
AdapterStarter = load_module('extension_starter', ROOT/'adapter_starter.py').AdapterStarter
NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)

def fixture(x=6, k=2):
    store = vector.Store()
    # Test fixture setup only: applications must enforce their writer boundary.
    store._state = dict(x=x, y=10-x, revision=0)
    clock = [NOW]
    adapter = vector.VectorAdapter(store, lambda: clock[0])
    request = vector.Update('case', k)
    authority = adapter.issue_approval(request)
    return store, clock, adapter, request, authority

def assert_no_write(store, adapter, request, authority, reason):
    before = store.read()
    count = store.writer_count
    receipt = adapter.execute(request, authority)
    assert receipt.decision == 'HOLD'
    assert reason in receipt.domain_admission_failures
    assert receipt.writer_invoked is False
    assert receipt.effect_status == 'NOT_INVOKED'
    assert receipt.observed_after == before == store.read()
    assert store.writer_count == count
    return receipt

def test_installed_sdk():
    assert 'site-packages' in Path(scqos_domain_sdk.__file__).parts
    assert Path(scqos_domain_sdk.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())

@pytest.mark.parametrize('x', range(11))
@pytest.mark.parametrize('k', range(-1,13))
def test_all_integer_transitions(x, k):
    store, clock, adapter, request, authority = fixture(x,k)
    before = store.read()
    receipt = adapter.execute(request, authority)
    if 1 <= k <= 3 and k <= x:
        assert receipt.decision == receipt.kernel_decision == 'PERMIT'
        assert receipt.writer_invoked is True
        assert receipt.effect_status == 'VERIFIED_EFFECT'
        assert receipt.observed_after == store.read() == dict(x=x-k,y=10-x+k,revision=1)
        assert store.writer_count == 1
        assert authority.approval_id in store.used
    else:
        assert receipt.decision == 'HOLD'
        assert receipt.kernel_decision is None
        assert receipt.writer_invoked is False
        assert receipt.effect_status == 'NOT_INVOKED'
        assert receipt.observed_after == store.read() == before
        assert store.writer_count == 0
        assert authority.approval_id not in store.used
    assert store.read()['x'] + store.read()['y'] == 10

@pytest.mark.parametrize('changes', [
    {'approval_id':'forged'}, {'request_digest':'0'*64}, {'state_digest':'0'*64},
    {'expected_digest':'0'*64}, {'actor':'someone-else'},
    {'issued_at':NOW-timedelta(seconds=1)}, {'expires_at':NOW+timedelta(days=1)},
])
def test_forged_approval(changes):
    store, clock, adapter, request, authority = fixture()
    assert_no_write(store, adapter, request, replace(authority,**changes), 'unrecognized_authority')

def test_missing_authority():
    store, clock, adapter, request, authority = fixture()
    assert_no_write(store,adapter,request,None,'approval_missing')

@pytest.mark.parametrize('delta,permit', [(-1,False),(0,True),(59,True),(60,False),(61,False)])
def test_authority_time_boundaries(delta,permit):
    store, clock, adapter, request, authority = fixture()
    clock[0] = NOW+timedelta(seconds=delta)
    if permit:
        receipt=adapter.execute(request,authority)
        assert receipt.effect_status=='VERIFIED_EFFECT'
        assert store.writer_count==1
    else:
        assert_no_write(store,adapter,request,authority,'expired_authority')

@pytest.mark.parametrize('changes', [{'k':3},{'transition_id':'changed'},{'actor':'different'}])
def test_changed_request(changes):
    store, clock, adapter, request, authority = fixture()
    assert_no_write(store,adapter,replace(request,**changes),authority,'changed_proposal')

def test_replay_preserves_first_effect():
    store, clock, adapter, request, authority = fixture()
    assert adapter.execute(request,authority).effect_status=='VERIFIED_EFFECT'
    assert_no_write(store,adapter,request,authority,'replay')
    assert store.read()==dict(x=4,y=6,revision=1)
    assert store.writer_count==1

def test_same_values_new_revision_rejects_old_approval():
    store, clock, adapter, request, authority = fixture()
    # Simulated intervening history returning x,y to their original values.
    with store.lock:
        store._state = dict(x=6,y=4,revision=2)
    assert_no_write(store,adapter,request,authority,'stale_reference')

@pytest.mark.parametrize('interference', ['state','expiry'])
def test_change_after_kernel_permit(interference):
    store, clock, adapter, request, authority = fixture()
    def hook():
        if interference=='state': store.competing_change()
        else: clock[0]=authority.expires_at
    adapter.before_atomic_write=hook
    receipt=adapter.execute(request,authority)
    assert receipt.kernel_decision=='PERMIT'
    assert receipt.decision=='HOLD'
    assert receipt.domain_admission_failures==('atomic_guard_rejected',)
    assert receipt.writer_invoked is False
    assert store.writer_count==0
    expected=dict(x=5,y=5,revision=1) if interference=='state' else dict(x=6,y=4,revision=0)
    assert receipt.observed_after==store.read()==expected
    assert authority.approval_id not in store.used

def test_concurrent_duplicate_exactly_one_write():
    store, clock, adapter, request, authority = fixture()
    barrier=Barrier(2)
    def kernel(prepared):
        result=adapter.kernel(prepared)
        barrier.wait(timeout=5)
        return result
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts=list(executor.map(lambda _:adapter.execute(request,authority,kernel),range(2)))
    assert sorted(r.decision for r in receipts)==['HOLD','PERMIT']
    assert sum(r.writer_invoked for r in receipts)==1
    assert store.writer_count==1
    assert store.read()==dict(x=4,y=6,revision=1)

@pytest.mark.parametrize('behavior,reason', [('invalid','kernel_receipt_invalid'),('hold','kernel_hold'),('other','kernel_receipt_binding_invalid')])
def test_kernel_failure_cannot_write(behavior,reason):
    store, clock, adapter, request, authority = fixture()
    before=store.read()
    def kernel(prepared):
        if behavior=='invalid': return None
        if behavior=='hold': return replace(adapter.kernel(prepared),decision=TransitionDecision.HOLD, resulting_state_ref=None, release_block_reason="test_policy_hold")
        other=adapter.normalize_proposal(replace(request,k=3),before,authority)
        return adapter.kernel(other)
    receipt=adapter.execute(request,authority,kernel)
    assert receipt.decision=='HOLD'
    assert reason in receipt.domain_admission_failures
    assert receipt.writer_invoked is False
    assert store.writer_count==0
    assert store.read()==before

@pytest.mark.parametrize('method,args', [
    ('read_authoritative_state',()),('collect_authority',(None,)),
    ('normalize_proposal',(None,{},None)),('evaluate_domain_predicates',(None,None,None,{})),
    ('execute_consequence',(None,None,None,lambda:pytest.fail('writer marked'))),
    ('verify_consequence',(None,{})),
])
def test_starter_requires_implementation(method,args):
    with pytest.raises(NotImplementedError): getattr(AdapterStarter(),method)(*args)

def test_unimplemented_starter_holds():
    receipt=execute_governed_transition(AdapterStarter(),None,None,
        kernel=lambda _:pytest.fail('kernel should not be called'))
    assert receipt.decision=='HOLD'
    assert receipt.kernel_decision is None
    assert receipt.writer_invoked is False
    assert receipt.effect_status=='NOT_INVOKED'
    assert receipt.domain_admission_failures==('evaluation_error:NotImplementedError',)

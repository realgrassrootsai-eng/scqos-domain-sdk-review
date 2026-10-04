"""Behavioral proof of local synthetic payment controls with the real SCQOS kernel."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier
import json
import subprocess
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from governed_transition import TransitionDecision, TransitionReceipt
from scqos_synthetic_payment_adapter import PaymentRequest, SyntheticPaymentAdapter, SyntheticPaymentStore

NOW = datetime(2026, 9, 20, 22, tzinfo=timezone.utc)
def setup(balance=1_000_000, amount=50_000):
    store = SyntheticPaymentStore(balance)
    adapter = SyntheticPaymentAdapter(store, lambda: NOW)
    request = PaymentRequest("payment-001", "Vendor X", amount)
    return store, adapter, request
def assert_hold(receipt, store, reason):
    assert receipt.decision == "HOLD"
    assert reason in receipt.domain_admission_failures
    assert not receipt.writer_invoked
    assert store.writer_count == 0

def test_real_kernel_permit_and_observed_debit():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    r = adapter.execute(request, approval)
    assert r.decision == r.kernel_decision == "PERMIT"
    assert len(r.kernel_invariant_results) == 8
    assert all(i["passed"] for i in r.kernel_invariant_results)
    assert r.writer_invoked and store.writer_count == 1
    assert r.effect_status == "VERIFIED_EFFECT"
    assert r.observed_after["balance_cents"] == 950_000
    assert r.observed_after["payments"]["payment-001"]["recipient"] == "Vendor X"
    assert r.provenance == "synthetic_local_lab"
    json.dumps(r.to_dict())

def test_missing_approval():
    store, adapter, request = setup()
    assert_hold(adapter.execute(request), store, "approval_missing")

def test_limit():
    store, adapter, request = setup(amount=500_000)
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(request, approval), store, "domain_boundary")

@pytest.mark.parametrize("issued,expired", [(NOW-timedelta(seconds=61), NOW),
    (NOW+timedelta(seconds=1), NOW+timedelta(seconds=60))])
def test_expired_and_future(issued, expired):
    store, adapter, request = setup()
    approval = adapter.issue_approval(request, issued_at=issued, expires_at=expired)
    assert_hold(adapter.execute(request, approval), store, "domain_time")

def test_expiry_rechecked_after_kernel():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request, lifetime_seconds=5)
    def kernel(p):
        result = adapter.kernel(p)
        adapter.clock = lambda: NOW+timedelta(seconds=5)
        return result
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "domain_time")

def test_stale_source():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    store.competing_change()
    assert_hold(adapter.execute(request, approval), store, "domain_reference")

@pytest.mark.parametrize("changes", [dict(recipient="Vendor Y"), dict(amount_cents=51_000),
    dict(actor="guest:other"), dict(payment_id="payment-002")])
def test_proposal_mutation(changes):
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(replace(request, **changes), approval), store, "domain_reference")

def test_funds():
    store, adapter, request = setup(balance=40_000)
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(request, approval), store, "insufficient_funds")

@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "500"])
def test_invalid_money(amount):
    with pytest.raises(ValueError):
        PaymentRequest("p", "Vendor X", amount)

def test_approval_object_not_authentic():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(request, replace(approval, max_amount_cents=500_000)),
                store, "domain_genesis")

def test_replay_and_duplicate_approval_id():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    assert adapter.execute(request, approval).effect_status == "VERIFIED_EFFECT"
    replay = adapter.execute(request, approval)
    assert replay.decision == "HOLD" and not replay.writer_invoked
    assert "replay" in replay.domain_admission_failures
    assert store.writer_count == 1 and store.read()["balance_cents"] == 950_000
    with pytest.raises(ValueError, match="approval_id_already_issued"):
        adapter.issue_approval(request)

def test_kernel_hold():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    def kernel(p):
        accepted = adapter.kernel(p)
        results = list(accepted.invariant_results)
        results[0] = replace(results[0], passed=False, reason="test missing temporal evidence")
        return TransitionReceipt(proposal=accepted.proposal, invariant_results=results,
            decision=TransitionDecision.HOLD, first_failed_invariant="time")
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "kernel_hold")

def test_kernel_exception():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    def kernel(p):
        raise RuntimeError("unavailable")
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "evaluation_error:RuntimeError")

def test_wrong_kernel_proposal():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    def kernel(p):
        accepted = adapter.kernel(p)
        wrong = replace(accepted.proposal, proposed_consequence_digest="0"*64)
        return TransitionReceipt(proposal=wrong, invariant_results=accepted.invariant_results,
            decision=TransitionDecision.PERMIT, resulting_state_ref="test:wrong")
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "kernel_receipt_binding_invalid")

def test_invalid_kernel_response():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(request, approval, kernel=lambda p: "PERMIT"), store, "kernel_receipt_invalid")

def test_race_before_atomic_write():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    adapter.before_atomic_write = lambda: store.competing_change(100)
    assert_hold(adapter.execute(request, approval), store, "atomic_guard_rejected")
    assert store.read()["balance_cents"] == 1_000_100

def test_two_concurrent_attempts_only_one_debit():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    barrier = Barrier(2, timeout=5)
    adapter.before_atomic_write = lambda: barrier.wait()
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: adapter.execute(request, approval), range(2)))
    assert sum(r.writer_invoked for r in receipts) == store.writer_count == 1
    assert sorted(r.decision for r in receipts) == ["HOLD", "PERMIT"]
    assert store.read()["balance_cents"] == 950_000

def test_writer_returns_without_effect():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    adapter.writer = lambda value: None
    r = adapter.execute(request, approval)
    assert r.writer_invoked and r.effect_status == "UNVERIFIED_EFFECT"
    assert store.read()["balance_cents"] == 1_000_000

def test_writer_exception_before_effect_blocks_retry():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    def writer(value):
        raise OSError("simulated")
    adapter.writer = writer
    r = adapter.execute(request, approval)
    assert r.writer_invoked and r.effect_status == "UNKNOWN_OUTCOME"
    assert not adapter.execute(request, approval).writer_invoked
    assert store.writer_count == 1

def test_writer_exception_after_effect_observed():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    def writer(value):
        adapter._write(value)
        raise OSError("ack lost")
    adapter.writer = writer
    r = adapter.execute(request, approval)
    assert r.effect_status == "VERIFIED_EFFECT"
    assert r.domain_admission_failures == ("writer_error:OSError",)

def test_writer_cannot_mutate_expected_to_fake_success():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    def writer(value):
        value["balance_cents"] = 1
        adapter._write(value)
    adapter.writer = writer
    r = adapter.execute(request, approval)
    assert r.expected_after["balance_cents"] == 950_000
    assert r.observed_after["balance_cents"] == 1
    assert r.effect_status == "UNVERIFIED_EFFECT"

def test_reads_are_copies():
    store, adapter, request = setup()
    read = store.read()
    read["payments"]["fake"] = {}
    assert store.read()["payments"] == {}

def test_naive_clock_fails_closed():
    store, adapter, request = setup()
    approval = adapter.issue_approval(request)
    adapter.clock = lambda: NOW.replace(tzinfo=None)
    assert_hold(adapter.execute(request, approval), store, "evaluation_error:ValueError")

def test_demo_cli():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root/"examples/run_scqos_synthetic_payment_demo.py")],
                            capture_output=True, text=True, check=True)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r["scenario"] for r in rows] == ["valid", "unapproved", "expired", "stale_state"]
    assert rows[0]["receipt"]["effect_status"] == "VERIFIED_EFFECT"
    assert all(not r["receipt"]["writer_invoked"] for r in rows[1:])

"""The same SDK admission and writer rules across two distinct local workflows."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
import json
import subprocess
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from governed_transition import TransitionDecision, TransitionReceipt
from scqos_synthetic_payment_adapter import (PaymentRequest, SyntheticPaymentAdapter, SyntheticPaymentStore)
from scqos_synthetic_deployment_adapter import (DeploymentRequest, SyntheticDeploymentAdapter,
    SyntheticDeploymentStore, INITIAL_IMAGE, TARGET_IMAGE)

NOW = datetime(2026, 9, 20, 22, tzinfo=timezone.utc)
def case(kind):
    if kind == "payment":
        store = SyntheticPaymentStore()
        adapter = SyntheticPaymentAdapter(store, lambda: NOW)
        request = PaymentRequest("payment-001", "Vendor X", 50_000)
    else:
        store = SyntheticDeploymentStore()
        adapter = SyntheticDeploymentAdapter(store, lambda: NOW)
        request = DeploymentRequest("deploy-001", "service-ABC", "production", TARGET_IMAGE)
    return store, adapter, request

@pytest.fixture(params=["payment", "deployment"])
def domain(request):
    return request.param

def assert_hold(receipt, store, reason):
    assert receipt.decision == "HOLD"
    assert not receipt.writer_invoked and store.writer_count == 0
    assert reason in receipt.domain_admission_failures

def test_real_kernel_and_effect_in_both_domains(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    r = adapter.execute(request, approval)
    assert r.decision == r.kernel_decision == "PERMIT"
    assert all(i["passed"] for i in r.kernel_invariant_results)
    assert len(r.kernel_invariant_results) == 8
    assert r.effect_status == "VERIFIED_EFFECT" and store.writer_count == 1
    assert r.observed_after == r.expected_after
    json.dumps(r.to_dict())
    if domain == "payment":
        assert r.observed_after["balance_cents"] == 950_000
    else:
        assert r.observed_after["image_digest"] == TARGET_IMAGE
        assert r.observed_after["generation"] == 1

def test_unapproved(domain):
    store, adapter, request = case(domain)
    assert_hold(adapter.execute(request), store, "approval_missing")

def test_expired(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request, issued_at=NOW-timedelta(seconds=61), expires_at=NOW)
    assert_hold(adapter.execute(request, approval), store, "domain_time")

def test_not_yet_valid(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request, issued_at=NOW+timedelta(seconds=1),
                                     expires_at=NOW+timedelta(seconds=60))
    assert_hold(adapter.execute(request, approval), store, "domain_time")

def test_stale_state(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    store.competing_change()
    assert_hold(adapter.execute(request, approval), store, "domain_reference")

def test_actor_mutation(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(replace(request, actor="guest:other"), approval), store, "domain_reference")

def test_expiry_after_kernel(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request, lifetime_seconds=5)
    def kernel(p):
        result = adapter.kernel(p)
        adapter.clock = lambda: NOW+timedelta(seconds=5)
        return result
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "domain_time")

def test_atomic_race_blocks_writer(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    adapter.before_atomic_write = lambda: store.competing_change()
    assert_hold(adapter.execute(request, approval), store, "atomic_guard_rejected")

def test_concurrent_duplicates(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    barrier = Barrier(2, timeout=5)
    adapter.before_atomic_write = lambda: barrier.wait()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: adapter.execute(request, approval), range(2)))
    assert sorted(r.decision for r in rows) == ["HOLD", "PERMIT"]
    assert sum(r.writer_invoked for r in rows) == store.writer_count == 1

def test_replay(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    assert adapter.execute(request, approval).effect_status == "VERIFIED_EFFECT"
    again = adapter.execute(request, approval)
    assert again.decision == "HOLD" and "replay" in again.domain_admission_failures
    assert not again.writer_invoked and store.writer_count == 1

def test_kernel_hold(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    def kernel(p):
        accepted = adapter.kernel(p)
        results = list(accepted.invariant_results)
        results[0] = replace(results[0], passed=False, reason="test invalid temporal evidence")
        return TransitionReceipt(proposal=accepted.proposal, invariant_results=results,
            decision=TransitionDecision.HOLD, first_failed_invariant="time")
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "kernel_hold")

def test_kernel_exception(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    def kernel(p):
        raise RuntimeError("unavailable")
    assert_hold(adapter.execute(request, approval, kernel=kernel), store, "evaluation_error:RuntimeError")

def test_writer_no_effect(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    adapter.writer = lambda expected: None
    r = adapter.execute(request, approval)
    assert r.decision == "PERMIT" and r.writer_invoked and r.effect_status == "UNVERIFIED_EFFECT"

def test_writer_error_consumes_authority(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    def writer(expected):
        raise OSError("simulated")
    adapter.writer = writer
    r = adapter.execute(request, approval)
    assert r.writer_invoked and r.effect_status == "UNKNOWN_OUTCOME"
    assert not adapter.execute(request, approval).writer_invoked
    assert store.writer_count == 1

def test_writer_error_after_effect(domain):
    store, adapter, request = case(domain)
    approval = adapter.issue_approval(request)
    def writer(expected):
        adapter._write(expected)
        raise OSError("ack lost")
    adapter.writer = writer
    r = adapter.execute(request, approval)
    assert r.effect_status == "VERIFIED_EFFECT"
    assert r.domain_admission_failures == ("writer_error:OSError",)

@pytest.mark.parametrize("changes", [dict(service="another-service"), dict(environment="staging"),
    dict(image_digest="sha256:"+"4"*64), dict(deployment_id="different-deploy")])
def test_deployment_proposal_mutation(changes):
    store, adapter, request = case("deployment")
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(replace(request, **changes), approval), store, "domain_reference")

@pytest.mark.parametrize("scope", [dict(allowed_service="another-service"),
    dict(allowed_environment="staging"), dict(allowed_actor="guest:other")])
def test_deployment_approval_scope(scope):
    store, adapter, request = case("deployment")
    approval = adapter.issue_approval(request, **scope)
    assert_hold(adapter.execute(request, approval), store, "domain_boundary")

@pytest.mark.parametrize("digest", ["latest", "image:v1", "sha256:abc", "sha256:"+"G"*64, True])
def test_immutable_digest_required(digest):
    with pytest.raises(ValueError, match="immutable_image_digest_required"):
        DeploymentRequest("d", "s", "production", digest)

def test_no_image_change():
    store, adapter, request = case("deployment")
    request = replace(request, image_digest=INITIAL_IMAGE)
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(request, approval), store, "no_image_change")

def test_deployment_mutated_approval_origin():
    store, adapter, request = case("deployment")
    approval = adapter.issue_approval(request)
    assert_hold(adapter.execute(request, replace(approval, allowed_environment="staging")),
                store, "domain_genesis")

def test_adapter_independent_import():
    root = Path(__file__).resolve().parents[1]
    command = "import sys; import scqos_synthetic_deployment_adapter; assert 'scqos_synthetic_payment_adapter' not in sys.modules; assert 'boto3' not in sys.modules; assert 'web_chat' not in sys.modules"
    subprocess.run([sys.executable, "-c", command], cwd=root, check=True)

def test_comparison_cli():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root/"scripts/run_scqos_domain_reuse_demo.py")],
                            capture_output=True, text=True, check=True)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 8
    for domain in ("payment", "deployment"):
        selected = [r for r in rows if r["domain"] == domain]
        assert selected[0]["receipt"]["effect_status"] == "VERIFIED_EFFECT"
        assert all(r["receipt"]["decision"] == "HOLD" and not r["receipt"]["writer_invoked"]
                   for r in selected[1:])

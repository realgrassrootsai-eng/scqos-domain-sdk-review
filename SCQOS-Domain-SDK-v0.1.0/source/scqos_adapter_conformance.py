"""Reusable behavioral probes for disposable domain adapters; not certification."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any, Callable
import argparse
import json
from governed_transition import TransitionDecision, TransitionReceipt
from scqos_domain_sdk import DomainAdapter, PreparedTransition, execute_governed_transition

@dataclass
class AdapterConformanceCase:
    """A factory supplies a fresh disposable, authorized test case for every probe."""
    adapter: DomainAdapter
    request: Any
    authority: Any
    kernel: Callable[[PreparedTransition], TransitionReceipt]
    read_state: Callable[[], dict]
    writer_count: Callable[[], int]
    changed_request: Callable[[], Any]
    advance_clock: Callable[[int], None]
    competing_change: Callable[[], None]
    set_before_write: Callable[[Callable[[], None]], None]
    set_writer: Callable[[Callable[[dict], None]], None]
    write_expected: Callable[[dict], None]

def builtin_case(domain):
    now = [datetime(2026, 9, 20, 22, tzinfo=timezone.utc)]
    if domain == "payment":
        from scqos_synthetic_payment_adapter import PaymentRequest, SyntheticPaymentAdapter, SyntheticPaymentStore
        store = SyntheticPaymentStore()
        adapter = SyntheticPaymentAdapter(store, lambda: now[0])
        request = PaymentRequest("conformance-payment", "Vendor X", 50_000)
        changed = lambda: replace(request, amount_cents=51_000)
    elif domain == "deployment":
        from scqos_synthetic_deployment_adapter import (DeploymentRequest, SyntheticDeploymentAdapter,
            SyntheticDeploymentStore, TARGET_IMAGE)
        store = SyntheticDeploymentStore()
        adapter = SyntheticDeploymentAdapter(store, lambda: now[0])
        request = DeploymentRequest("conformance-deploy", "service-ABC", "production", TARGET_IMAGE)
        changed = lambda: replace(request, image_digest="sha256:"+"4"*64)
    else:
        raise ValueError("unknown_builtin_domain")
    authority = adapter.issue_approval(request)
    def advance(seconds):
        now[0] += timedelta(seconds=seconds)
    return AdapterConformanceCase(adapter, request, authority, adapter.kernel,
        store.read, lambda: store.writer_count, changed, advance, store.competing_change,
        lambda hook: setattr(adapter, "before_atomic_write", hook),
        lambda writer: setattr(adapter, "writer", writer), adapter._write)

def payment_case():
    return builtin_case("payment")

def deployment_case():
    return builtin_case("deployment")

def _require(condition, reason):
    if not condition:
        raise AssertionError(reason)

def _execute(case, authority=None, *, absent=False, request=None, kernel=None):
    return execute_governed_transition(case.adapter, request if request is not None else case.request,
        None if absent else case.authority if authority is None else authority,
        kernel=kernel if kernel is not None else case.kernel)

def _hold(case, result, count=0):
    _require(result.decision == "HOLD", "expected_hold")
    _require(result.writer_invoked is False, "hold_invoked_writer")
    _require(case.writer_count() == count, "hold_changed_writer_count")

def _probe(name, case):
    before = case.read_state()
    if name == "valid_effect":
        result = _execute(case)
        _require(result.decision == result.kernel_decision == "PERMIT", "valid_not_permitted")
        _require(result.writer_invoked and case.writer_count() == 1, "valid_writer_count")
        _require(result.effect_status == "VERIFIED_EFFECT", "valid_effect_unverified")
        _require(result.observed_after == case.read_state() == result.expected_after,
                 "observed_effect_mismatch")
        _require(before != case.read_state(), "valid_effect_no_change")
        _require(len(result.kernel_invariant_results) == 8 and
                 all(item["passed"] is True for item in result.kernel_invariant_results),
                 "valid_kernel_chain_missing")
    elif name == "missing_authority":
        _hold(case, _execute(case, absent=True))
        _require(case.read_state() == before, "hold_mutated_state")
    elif name == "expired_authority":
        case.advance_clock(61)
        _hold(case, _execute(case))
        _require(case.read_state() == before, "expired_mutated_state")
    elif name == "changed_proposal":
        _hold(case, _execute(case, request=case.changed_request()))
        _require(case.read_state() == before, "changed_proposal_mutated_state")
    elif name == "stale_state":
        case.competing_change()
        competing = case.read_state()
        _require(competing != before, "stale_fixture_did_not_change_state")
        _hold(case, _execute(case))
        _require(case.read_state() == competing, "stale_attempt_mutated_state")
    elif name == "approval_replay":
        first = _execute(case)
        _require(first.effect_status == "VERIFIED_EFFECT", "replay_setup_failed")
        after = case.read_state()
        _hold(case, _execute(case), count=1)
        _require(case.read_state() == after, "replay_mutated_state")
    elif name == "atomic_stale_guard":
        case.set_before_write(case.competing_change)
        _hold(case, _execute(case))
        _require(case.read_state() != before, "race_fixture_did_not_change_state")
    elif name == "atomic_expiry_guard":
        case.set_before_write(lambda: case.advance_clock(61))
        _hold(case, _execute(case))
        _require(case.read_state() == before, "expiry_race_mutated_state")
    elif name == "writer_no_effect":
        case.set_writer(lambda expected: None)
        result = _execute(case)
        _require(result.writer_invoked and case.writer_count() == 1, "writer_not_attempted")
        _require(result.effect_status == "UNVERIFIED_EFFECT", "no_effect_claimed_verified")
        _require(result.observed_after == before == case.read_state(), "no_effect_readback_wrong")
    elif name in ("writer_exception", "writer_exception_after_effect"):
        def writer(expected):
            if name == "writer_exception_after_effect":
                case.write_expected(expected)
            raise OSError("conformance simulated writer failure")
        case.set_writer(writer)
        result = _execute(case)
        _require(result.writer_invoked and case.writer_count() == 1, "failed_writer_not_attempted")
        status = "VERIFIED_EFFECT" if name.endswith("after_effect") else "UNKNOWN_OUTCOME"
        _require(result.effect_status == status, "writer_exception_wrong_status")
        _hold(case, _execute(case), count=1)
    elif name == "kernel_unavailable":
        def unavailable(prepared):
            raise RuntimeError("conformance kernel unavailable")
        _hold(case, _execute(case, kernel=unavailable))
        _require(case.read_state() == before, "kernel_error_mutated_state")
    elif name == "kernel_hold":
        def held(prepared):
            original = case.kernel(prepared)
            results = list(original.invariant_results)
            results[0] = replace(results[0], passed=False, reason="conformance temporal failure")
            return TransitionReceipt(proposal=original.proposal, invariant_results=results,
                decision=TransitionDecision.HOLD, first_failed_invariant=results[0].invariant)
        _hold(case, _execute(case, kernel=held))
        _require(case.read_state() == before, "kernel_hold_mutated_state")
    elif name == "concurrent_duplicate":
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2, timeout=5)
        case.set_before_write(lambda: barrier.wait())
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda _: _execute(case), range(2)))
        _require(sorted(r.decision for r in rows) == ["HOLD", "PERMIT"], "duplicate_decisions_wrong")
        _require(sum(r.writer_invoked for r in rows) == case.writer_count() == 1,
                 "duplicate_writer_count_wrong")
    else:
        raise ValueError("unknown_probe")

PROBES = ("valid_effect", "missing_authority", "expired_authority", "changed_proposal",
    "stale_state", "approval_replay", "atomic_stale_guard", "atomic_expiry_guard",
    "writer_no_effect", "writer_exception", "writer_exception_after_effect",
    "kernel_unavailable", "kernel_hold", "concurrent_duplicate")

def run_conformance(factory: Callable[[], AdapterConformanceCase], *, adapter_id="custom"):
    checks = []
    for name in PROBES:
        try:
            case = factory()
            if type(case) is not AdapterConformanceCase:
                raise TypeError("adapter_conformance_case_required")
            _probe(name, case)
            checks.append(dict(check=name, passed=True))
        except Exception as exc:
            # Assertion diagnostics are controlled by this module; external errors stay opaque.
            reason = str(exc) if type(exc) is AssertionError else type(exc).__name__
            checks.append(dict(check=name, passed=False, reason=reason))
    return dict(schema_version="scqos_adapter_conformance_v1", adapter_id=adapter_id,
                passed=all(row["passed"] for row in checks), checks=checks,
                scope="disposable_local_behavioral_probes", certification=False)

def resolve_factory(value):
    if value == "builtin-payment":
        return payment_case
    if value == "builtin-deployment":
        return deployment_case
    module, separator, symbol = value.partition(":")
    if not separator or not module or not symbol or "." in symbol:
        raise ValueError("factory_must_be_module_colon_callable")
    factory = getattr(import_module(module), symbol)
    if not callable(factory):
        raise TypeError("factory_not_callable")
    return factory

def main():
    parser = argparse.ArgumentParser(description="Run behavioral probes on a disposable adapter factory.")
    parser.add_argument("--factory", required=True, help="builtin-payment, builtin-deployment or module:callable")
    args = parser.parse_args()
    try:
        report = run_conformance(resolve_factory(args.factory), adapter_id=args.factory)
    except Exception as exc:
        print(json.dumps(dict(passed=False, error=type(exc).__name__), sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())

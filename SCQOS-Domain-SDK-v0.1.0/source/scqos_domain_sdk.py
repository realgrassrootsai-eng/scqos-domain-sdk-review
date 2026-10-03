"""Local prototype domain orchestration; kernel and domain admission stay distinct."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol
from governed_transition import SCQOS_INVARIANTS, TransitionDecision, TransitionReceipt, TransitionProposal

@dataclass(frozen=True)
class PreparedTransition:
    proposal_digest: str
    before: dict
    expected_after: dict
    kernel_input: Any
    kernel_proposal: TransitionProposal

class DomainAdapter(Protocol):
    def read_authoritative_state(self) -> dict: ...
    def normalize_proposal(self, request: Any, before: dict, authority: Any) -> PreparedTransition: ...
    def collect_authority(self, authority: Any) -> Any: ...
    def evaluate_domain_predicates(self, request: Any, prepared: PreparedTransition, authority: Any, current: dict) -> tuple[str, ...]: ...
    def execute_consequence(self, request: Any, prepared: PreparedTransition, authority: Any, mark_invoked: Callable[[], None]) -> bool: ...
    def verify_consequence(self, prepared: PreparedTransition, observed: dict) -> bool: ...

@dataclass(frozen=True)
class DomainReceipt:
    schema_version: str
    proposal_digest: str | None
    before: dict | None
    expected_after: dict | None
    decision: str
    kernel_decision: str | None
    kernel_invariant_results: tuple[dict, ...]
    domain_admission_failures: tuple[str, ...]
    writer_invoked: bool
    observed_after: dict | None
    effect_status: str
    provenance: str = "synthetic_local_lab"
    def to_dict(self) -> dict:
        return asdict(self)

def execute_governed_transition(adapter: DomainAdapter, request: Any, authority: Any, *,
                                kernel: Callable[[PreparedTransition], TransitionReceipt]) -> DomainReceipt:
    """Only the guarded adapter writer may mutate; success comes from observation."""
    before = expected = observed = None
    digest = kernel_decision = None
    results = ()
    invoked = False
    def mark_invoked():
        nonlocal invoked
        invoked = True
    def receipt(decision, failures=(), effect="NOT_INVOKED"):
        return DomainReceipt("scqos_domain_receipt_v1", digest, before, expected, decision,
                             kernel_decision, results, tuple(failures), invoked, observed, effect)
    try:
        before = adapter.read_authoritative_state()
        authority = adapter.collect_authority(authority)
        prepared = adapter.normalize_proposal(request, before, authority)
        digest, expected = prepared.proposal_digest, prepared.expected_after
        failures = adapter.evaluate_domain_predicates(request, prepared, authority, before)
        if failures:
            observed = adapter.read_authoritative_state()
            return receipt("HOLD", failures)
        bound = kernel(prepared)
        if type(bound) is not TransitionReceipt:
            return receipt("HOLD", ("kernel_receipt_invalid",))
        results = tuple(item.to_dict() if hasattr(item, "to_dict") else asdict(item)
                        for item in bound.invariant_results)
        kernel_decision = bound.decision.value
        # Never accept a permit for some other proposal or an incomplete chain.
        if (bound.proposal != prepared.kernel_proposal
                or tuple(i.invariant for i in bound.invariant_results) != SCQOS_INVARIANTS):
            return receipt("HOLD", ("kernel_receipt_binding_invalid",))
        if bound.decision is not TransitionDecision.PERMIT:
            observed = adapter.read_authoritative_state()
            return receipt("HOLD", ("kernel_hold",))
        current = adapter.read_authoritative_state()
        failures = adapter.evaluate_domain_predicates(request, prepared, authority, current)
        if failures:
            observed = current
            return receipt("HOLD", failures)
        # execute_consequence MUST repeat guards atomically with mutation.
        wrote = adapter.execute_consequence(request, prepared, authority, mark_invoked)
        observed = adapter.read_authoritative_state()
        if not wrote:
            return receipt("HOLD", ("atomic_guard_rejected",))
        verified = adapter.verify_consequence(prepared, observed)
        return receipt("PERMIT", effect="VERIFIED_EFFECT" if verified else "UNVERIFIED_EFFECT")
    except Exception as exc:
        try:
            observed = adapter.read_authoritative_state()
        except Exception:
            observed = None
        if not invoked:
            return receipt("HOLD", ("evaluation_error:" + type(exc).__name__,))
        # An exception does not prove absence or success. Observe, never retry.
        verified = observed is not None and observed == expected
        return receipt("PERMIT", ("writer_error:" + type(exc).__name__,),
                       "VERIFIED_EFFECT" if verified else "UNKNOWN_OUTCOME")

"""Synthetic payment controls over the existing installed database lab boundary."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable
from database_action_approval import attach_database_action_approval, build_database_action_approval
from database_action_contracts import DatabaseWriteActionV1, DatabaseWriteOperation
from database_action_decision import build_database_action_decision
from database_action_governance import DATABASE_ACTION_LAB_TABLE, build_database_action_transition_binding
from scqos_contract_digest import contract_digest
from scqos_domain_sdk import PreparedTransition, execute_governed_transition
from scqos_runtime_evidence import (ContinuityRequirementEvidence, IdentityProvenanceEvidence,
    ReferenceResolutionEvidence, SCQOSRuntimeEvidence, TemporalEvidence, TypedConsequenceProductionEvidenceV1)

ACTOR = "guest:action-lab"
def canonical(value):
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
def positive_cents(value):
    if type(value) is not int or value <= 0:
        raise ValueError("positive_integer_cents_required")
    return value
def aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_aware_clock_required")
    return value.astimezone(timezone.utc)

@dataclass(frozen=True)
class PaymentRequest:
    payment_id: str
    recipient: str
    amount_cents: int
    actor: str = ACTOR
    def __post_init__(self):
        positive_cents(self.amount_cents)
        for text in (self.payment_id, self.recipient, self.actor):
            if type(text) is not str or not text or text != text.strip():
                raise ValueError("nonempty_exact_text_required")
    def to_dict(self):
        return dict(payment_id=self.payment_id, recipient=self.recipient,
                    amount_cents=self.amount_cents, actor=self.actor)

@dataclass(frozen=True)
class SyntheticApproval:
    approval_id: str
    request_digest: str
    state_digest: str
    expected_digest: str
    issued_at: datetime
    expires_at: datetime
    max_amount_cents: int
    actor: str
    recipient: str

class SyntheticPaymentStore:
    """One process-local atomic aggregate; not a bank, credential or durable ledger."""
    def __init__(self, balance_cents=1_000_000):
        positive_cents(balance_cents)
        self.lock = RLock()
        self._state = dict(account_id="account-A", balance_cents=balance_cents,
                           version=0, payments={})
        self._issued = {}
        self._used = set()
        self.writer_count = 0
    def read(self):
        with self.lock:
            return deepcopy(self._state)
    def competing_change(self, delta_cents=100):
        if type(delta_cents) is not int:
            raise ValueError("integer_cents_required")
        with self.lock:
            self._state["balance_cents"] += delta_cents
            self._state["version"] += 1

class SyntheticPaymentAdapter:
    def __init__(self, store, clock: Callable[[], datetime] | None = None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        # Test hooks model writer failures and a competing update.
        self.before_atomic_write = None
        self.writer = self._write
    def read_authoritative_state(self):
        return self.store.read()
    def collect_authority(self, authority):
        if authority is not None and type(authority) is not SyntheticApproval:
            raise ValueError("synthetic_approval_required")
        return authority
    def expected(self, request, before):
        result = deepcopy(before)
        result["balance_cents"] -= request.amount_cents
        result["version"] += 1
        result["payments"][request.payment_id] = dict(status="paid", recipient=request.recipient,
                                                     amount_cents=request.amount_cents)
        return result
    def normalize_proposal(self, request, before, authority):
        if type(request) is not PaymentRequest:
            raise ValueError("exact_payment_request_required")
        expected = self.expected(request, before)
        action = DatabaseWriteActionV1(transition_id="payment:" + request.payment_id,
            actor_id=request.actor, operation=DatabaseWriteOperation.SET_FIELD,
            table_name=DATABASE_ACTION_LAB_TABLE, record_key=before["account_id"],
            field_name="synthetic_payment_aggregate", old_value=canonical(before),
            proposed_value=canonical(expected),
            evidence_refs=("synthetic-state:" + contract_digest(before),))
        lab_approval = None
        if authority is not None:
            lab_approval = build_database_action_approval(action,
                approval_id=authority.approval_id, approver_id="synthetic-lab-operator")
            action = attach_database_action_approval(action, lab_approval)
        proposal_digest = contract_digest(dict(request=request.to_dict(), before=before, expected_after=expected))
        binding = build_database_action_transition_binding(action, request_id=action.transition_id,
            session_id="action-lab", inherited_state_ref="synthetic-state:" + contract_digest(before))
        return PreparedTransition(proposal_digest, deepcopy(before), expected,
                                  dict(action=action, approval=lab_approval), binding.proposal)
    def issue_approval(self, request, *, approval_id="synthetic-approval-1",
                       max_amount_cents=100_000, lifetime_seconds=60,
                       issued_at=None, expires_at=None):
        if type(approval_id) is not str or not approval_id.strip() or approval_id != approval_id.strip():
            raise ValueError("approval_id_required")
        positive_cents(max_amount_cents)
        now = aware(self.clock())
        issued = aware(issued_at) if issued_at is not None else now
        expiry = aware(expires_at) if expires_at is not None else issued + timedelta(seconds=lifetime_seconds)
        if expiry <= issued:
            raise ValueError("approval_interval_invalid")
        with self.store.lock:
            if approval_id in self.store._issued:
                raise ValueError("approval_id_already_issued")
            before = self.store.read()
            approval = SyntheticApproval(approval_id, contract_digest(request.to_dict()),
                contract_digest(before), contract_digest(self.expected(request, before)),
                issued, expiry, max_amount_cents, request.actor, request.recipient)
            self.store._issued[approval_id] = approval
            return approval
    def evaluate_domain_predicates(self, request, prepared, authority, current):
        failures = []
        if authority is None:
            return ("approval_missing",)
        now = aware(self.clock())
        if not (aware(authority.issued_at) <= now < aware(authority.expires_at)):
            failures.append("domain_time")
        with self.store.lock:
            if self.store._issued.get(authority.approval_id) != authority:
                failures.append("domain_genesis")
            if authority.approval_id in self.store._used or request.payment_id in current["payments"]:
                failures.append("replay")
        if (request.actor != ACTOR or authority.actor != request.actor
            or authority.recipient != request.recipient or request.amount_cents > authority.max_amount_cents):
            failures.append("domain_boundary")
        if (contract_digest(request.to_dict()) != authority.request_digest
            or contract_digest(current) != authority.state_digest
            or current != prepared.before
            or contract_digest(prepared.expected_after) != authority.expected_digest):
            failures.append("domain_reference")
        if current["balance_cents"] < request.amount_cents:
            failures.append("insufficient_funds")
        return tuple(failures)
    def kernel(self, prepared):
        action = prepared.kernel_input["action"]
        binding = build_database_action_transition_binding(action, request_id=action.transition_id,
            session_id="action-lab", inherited_state_ref="synthetic-state:" + contract_digest(prepared.before))
        refs = binding.proposal.reference_bindings
        # These are honest local lab observations, not independent authenticity proof.
        digests = tuple((ref, contract_digest(dict(reference=ref, state=prepared.before))) for ref in refs)
        runtime = SCQOSRuntimeEvidence(
            temporal=TemporalEvidence(claimed_observation_timestamp=None,
                runtime_observed_at=aware(self.clock()).isoformat().replace("+00:00", "Z"),
                runtime_clock="server_utc", runtime_observation_kind="request_received"),
            continuity=ContinuityRequirementEvidence(inherited_state_required=False,
                requirement_status="not_required", requirement_bases=("no_inherited_state_dependency",),
                determination_source="server_continuity_classifier"),
            identity=IdentityProvenanceEvidence(transition_id=action.transition_id,
                authenticated_subject=None, origin_class="guest", actor_type="guest",
                session_id="action-lab", principal_reference=ACTOR),
            references=ReferenceResolutionEvidence(required=False, requested_references=refs,
                resolved_references=refs, consumed_content_digests=digests, resolved_content_digests=digests),
            execution=TypedConsequenceProductionEvidenceV1(transition_id=action.transition_id,
                request_id=action.transition_id, consequence_type="database_write",
                producer_id="scqos-action-lab:typed-builder:v1",
                request_digest=contract_digest(dict(proposal_digest=prepared.proposal_digest)),
                produced_consequence_digest=action.action_digest),
            boundary=binding.boundary_evidence)
        return build_database_action_decision(action=action, runtime_evidence=runtime,
            request_id=action.transition_id, session_id="action-lab",
            inherited_state_ref=binding.proposal.inherited_state_ref,
            approval=prepared.kernel_input["approval"]).receipt
    def _write(self, expected):
        self.store._state = deepcopy(expected)
    def execute_consequence(self, request, prepared, authority, mark_invoked):
        if self.before_atomic_write is not None:
            self.before_atomic_write()
        with self.store.lock:
            # The comparison, approval consumption and local writer share one lock.
            if self.evaluate_domain_predicates(request, prepared, authority, self.store.read()):
                return False
            self.store._used.add(authority.approval_id)
            self.store.writer_count += 1
            mark_invoked()
            self.writer(deepcopy(prepared.expected_after))
            return True
    def verify_consequence(self, prepared, observed):
        return observed == prepared.expected_after
    def execute(self, request, authority=None, *, kernel=None):
        return execute_governed_transition(self, request, authority, kernel=kernel or self.kernel)

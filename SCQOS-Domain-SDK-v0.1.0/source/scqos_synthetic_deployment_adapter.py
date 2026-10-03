"""Local deployment-state simulation using the unchanged SCQOS Domain SDK."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from threading import RLock
from database_action_approval import attach_database_action_approval, build_database_action_approval
from database_action_contracts import DatabaseWriteActionV1, DatabaseWriteOperation
from database_action_decision import build_database_action_decision
from database_action_governance import DATABASE_ACTION_LAB_TABLE, build_database_action_transition_binding
from scqos_contract_digest import contract_digest
from scqos_domain_sdk import PreparedTransition, execute_governed_transition
from scqos_runtime_evidence import (ContinuityRequirementEvidence, IdentityProvenanceEvidence,
    ReferenceResolutionEvidence, SCQOSRuntimeEvidence, TemporalEvidence, TypedConsequenceProductionEvidenceV1)

ACTOR = "guest:action-lab"
INITIAL_IMAGE = "sha256:" + "1"*64
TARGET_IMAGE = "sha256:" + "2"*64

def text(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("exact_nonempty_text_required")
    return value

def image(value):
    if type(value) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("immutable_image_digest_required")
    return value

def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_aware_clock_required")
    return value.astimezone(timezone.utc)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

@dataclass(frozen=True)
class DeploymentRequest:
    deployment_id: str
    service: str
    environment: str
    image_digest: str
    actor: str = ACTOR
    def __post_init__(self):
        for value in (self.deployment_id, self.service, self.environment, self.actor):
            text(value)
        image(self.image_digest)

@dataclass(frozen=True)
class DeploymentApproval:
    approval_id: str
    proposal_digest: str
    state_digest: str
    expected_digest: str
    issued_at: datetime
    expires_at: datetime
    allowed_service: str
    allowed_environment: str
    allowed_actor: str

class SyntheticDeploymentStore:
    """Simulated service metadata only. No ECS, cluster, container or rollout."""
    def __init__(self, service="service-ABC", environment="production", image_digest=INITIAL_IMAGE):
        self.lock = RLock()
        self._state = dict(service=text(service), environment=text(environment),
                           image_digest=image(image_digest), generation=0, last_deployment_id=None)
        self._issued = {}
        self._used = set()
        self._executed = set()
        self.writer_count = 0
    def read(self):
        with self.lock:
            return deepcopy(self._state)
    def competing_change(self, image_digest="sha256:" + "3"*64):
        image(image_digest)
        with self.lock:
            self._state["image_digest"] = image_digest
            self._state["generation"] += 1

class SyntheticDeploymentAdapter:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.before_atomic_write = None
        self.writer = self._write
    def read_authoritative_state(self):
        return self.store.read()
    def collect_authority(self, authority):
        if authority is not None and type(authority) is not DeploymentApproval:
            raise ValueError("deployment_approval_required")
        return authority
    def expected(self, request, before):
        return dict(before, image_digest=request.image_digest,
                    generation=before["generation"] + 1, last_deployment_id=request.deployment_id)
    def normalize_proposal(self, request, before, authority):
        if type(request) is not DeploymentRequest:
            raise ValueError("exact_deployment_request_required")
        expected = self.expected(request, before)
        action = DatabaseWriteActionV1(transition_id="deployment:" + request.deployment_id,
            actor_id=request.actor, operation=DatabaseWriteOperation.SET_FIELD,
            table_name=DATABASE_ACTION_LAB_TABLE, record_key=before["service"],
            field_name="synthetic_deployment_state", old_value=canonical(before),
            proposed_value=canonical(expected),
            evidence_refs=("synthetic-deployment-state:" + contract_digest(before),))
        lab_approval = None
        if authority is not None:
            lab_approval = build_database_action_approval(action,
                approval_id=authority.approval_id, approver_id="synthetic-lab-operator")
            action = attach_database_action_approval(action, lab_approval)
        binding = build_database_action_transition_binding(action, request_id=action.transition_id,
            session_id="action-lab", inherited_state_ref="synthetic-state:" + contract_digest(before))
        digest = contract_digest(dict(request=asdict(request), before=before, expected_after=expected))
        return PreparedTransition(digest, deepcopy(before), expected,
                                  dict(action=action, approval=lab_approval), binding.proposal)
    def issue_approval(self, request, *, approval_id="synthetic-deployment-approval-1",
                       lifetime_seconds=60, issued_at=None, expires_at=None,
                       allowed_service=None, allowed_environment=None, allowed_actor=None):
        text(approval_id)
        if type(request) is not DeploymentRequest:
            raise ValueError("exact_deployment_request_required")
        now = utc(self.clock())
        issued = utc(issued_at) if issued_at is not None else now
        expires = utc(expires_at) if expires_at is not None else issued + timedelta(seconds=lifetime_seconds)
        if expires <= issued:
            raise ValueError("approval_interval_invalid")
        with self.store.lock:
            if approval_id in self.store._issued:
                raise ValueError("approval_id_already_issued")
            before = self.store.read()
            approval = DeploymentApproval(approval_id, contract_digest(asdict(request)),
                contract_digest(before), contract_digest(self.expected(request, before)), issued, expires,
                text(allowed_service if allowed_service is not None else request.service),
                text(allowed_environment if allowed_environment is not None else request.environment),
                text(allowed_actor if allowed_actor is not None else request.actor))
            self.store._issued[approval_id] = approval
            return approval
    def evaluate_domain_predicates(self, request, prepared, authority, current):
        if authority is None:
            return ("approval_missing",)
        failures = []
        now = utc(self.clock())
        if not (utc(authority.issued_at) <= now < utc(authority.expires_at)):
            failures.append("domain_time")
        with self.store.lock:
            if self.store._issued.get(authority.approval_id) != authority:
                failures.append("domain_genesis")
            if authority.approval_id in self.store._used or request.deployment_id in self.store._executed:
                failures.append("replay")
        if (request.actor != ACTOR or request.actor != authority.allowed_actor
            or request.service != authority.allowed_service
            or request.environment != authority.allowed_environment
            or current["service"] != request.service or current["environment"] != request.environment):
            failures.append("domain_boundary")
        if (contract_digest(asdict(request)) != authority.proposal_digest
            or contract_digest(current) != authority.state_digest or current != prepared.before
            or contract_digest(prepared.expected_after) != authority.expected_digest):
            failures.append("domain_reference")
        if request.image_digest == current["image_digest"]:
            failures.append("no_image_change")
        return tuple(failures)
    def kernel(self, prepared):
        action = prepared.kernel_input["action"]
        binding = build_database_action_transition_binding(action, request_id=action.transition_id,
            session_id="action-lab", inherited_state_ref="synthetic-state:" + contract_digest(prepared.before))
        refs = binding.proposal.reference_bindings
        digests = tuple((ref, contract_digest(dict(reference=ref, state=prepared.before))) for ref in refs)
        runtime = SCQOSRuntimeEvidence(
            temporal=TemporalEvidence(claimed_observation_timestamp=None,
                runtime_observed_at=utc(self.clock()).isoformat().replace("+00:00", "Z"),
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
            if self.evaluate_domain_predicates(request, prepared, authority, self.store.read()):
                return False
            self.store._used.add(authority.approval_id)
            self.store._executed.add(request.deployment_id)
            self.store.writer_count += 1
            mark_invoked()
            self.writer(deepcopy(prepared.expected_after))
            return True
    def verify_consequence(self, prepared, observed):
        return observed == prepared.expected_after
    def execute(self, request, authority=None, *, kernel=None):
        return execute_governed_transition(self, request, authority, kernel=kernel or self.kernel)

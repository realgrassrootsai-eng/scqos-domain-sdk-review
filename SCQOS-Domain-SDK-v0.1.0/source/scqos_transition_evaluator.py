"""SCQOS eight-invariant transition evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from typing import Mapping

from authority_lineage import AuthorityLineageV1
from baton_transfer import BatonTransferV1
from constitutional_binding import ConstitutionalContractError
from requalification import (
    MaterialChangeEvidenceV1,
    QualificationSnapshotV1,
    RequalificationDecision,
    RequalificationV1,
    validate_requalification,
    validate_requalification_for_resume,
)
from transition_proof_bundle import TransitionProofBundleV1

from governed_action_registry import (
    GovernedActionRegistryError,
    governed_action_registry_digest,
    is_installed_governed_boundary,
    resolve_governed_boundary,
)
from governed_transition import (
    AlignmentVerification,
    InvariantResult,
    SCQOS_INVARIANTS,
    TransitionProposal,
)
from scqos_runtime_evidence import (
    BoundaryReleaseEvidence,
    ContinuityRequirementEvidence,
    IdentityProvenanceEvidence,
    ModelExecutionEvidence,
    TypedConsequenceProductionEvidenceV1,
    ExecutionObservation,
    ReferenceResolutionEvidence,
    SCQOSRuntimeEvidence,
    TemporalEvidence,
)
from scqos_time import (
    normalize_observation_timestamp,
    validate_observation_timestamp,
    validate_observation_timestamp_against_reference,
)


RUNTIME_TEMPORAL_EVIDENCE_REFERENCE = (
    "runtime:temporal:request_received:server_utc"
)

CLAIMED_TEMPORAL_EVIDENCE_REFERENCE = (
    "claim:temporal:observation_timestamp"
)

_AUTHORIZED_NON_ACTION_BOUNDARIES = {
    (
        "assistant_response",
        "chat_response_release",
    ): (
        "http_json_response",
        "POST /chat:response",
    ),
}

_COGNITO_PRINCIPAL_BINDINGS = {
    "cognito:grassrootsai": (
        "personal",
        "jerry_elizares",
    ),
    "cognito:supremeadmin": (
        "collaborator",
        "Eric",
    ),
}

_COGNITO_LAB_PRINCIPAL_BINDINGS = {
    "cognito-lab:scqos-action-lab-tester": (
        "collaborator",
        "action_lab_test_operator",
    ),
}

def evaluate_time_invariant(
    temporal_evidence: TemporalEvidence,
) -> InvariantResult:
    """
    Evaluate whether authoritative runtime temporal evidence exists
    and is temporally admissible.

    A caller-supplied observation timestamp is treated only as a claim.
    It may be checked for temporal admissibility, but it cannot itself
    establish authoritative runtime time.
    """

    if not isinstance(temporal_evidence, TemporalEvidence):
        return InvariantResult(
            invariant="time",
            passed=False,
            reason="temporal_evidence_required",
            evidence_references=(),
        )

    (
        normalized_runtime_timestamp,
        runtime_validation_status,
    ) = validate_observation_timestamp(
        temporal_evidence.runtime_observed_at
    )

    if runtime_validation_status != "accepted":
        return InvariantResult(
            invariant="time",
            passed=False,
            reason=(
                f"runtime_{runtime_validation_status}"
            ),
            evidence_references=(
                RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
            ),
        )

    claimed_timestamp = (
        temporal_evidence.claimed_observation_timestamp
    )

    if claimed_timestamp is not None:
        (
            normalized_claimed_timestamp,
            claimed_validation_status,
        ) = (
            validate_observation_timestamp_against_reference(
                claimed_timestamp,
                reference_timestamp=(
                    normalized_runtime_timestamp
                ),
            )
        )

        if claimed_validation_status != "accepted":
            return InvariantResult(
                invariant="time",
                passed=False,
                reason=(
                    f"claimed_{claimed_validation_status}"
                ),
                evidence_references=(
                    RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
                    CLAIMED_TEMPORAL_EVIDENCE_REFERENCE,
                ),
            )
    else:
        normalized_claimed_timestamp = None

    authority_values = (
        temporal_evidence.authority_valid_from,
        temporal_evidence.authority_expires_at,
        temporal_evidence.authority_reference,
    )
    if any(value is not None for value in authority_values):
        if any(value is None for value in authority_values):
            return InvariantResult(
                invariant="time",
                passed=False,
                reason="authority_temporal_window_incomplete",
                evidence_references=(
                    RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
                ),
            )

        normalized_valid_from, valid_from_status = (
            normalize_observation_timestamp(
                temporal_evidence.authority_valid_from
            )
        )
        normalized_expires_at, expires_status = (
            normalize_observation_timestamp(
                temporal_evidence.authority_expires_at
            )
        )
        if valid_from_status != "accepted":
            return InvariantResult(
                invariant="time",
                passed=False,
                reason="authority_valid_from_invalid",
                evidence_references=(
                    RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
                ),
            )
        if expires_status != "accepted":
            return InvariantResult(
                invariant="time",
                passed=False,
                reason="authority_expires_at_invalid",
                evidence_references=(
                    RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
                ),
            )

        runtime_dt = datetime.datetime.fromisoformat(
            normalized_runtime_timestamp.replace("Z", "+00:00")
        )
        valid_from_dt = datetime.datetime.fromisoformat(
            normalized_valid_from.replace("Z", "+00:00")
        )
        expires_dt = datetime.datetime.fromisoformat(
            normalized_expires_at.replace("Z", "+00:00")
        )
        authority_refs = (
            RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
            f"authority:temporal:{temporal_evidence.authority_reference}",
            f"time:authority-valid-from:{normalized_valid_from}",
            f"time:authority-expires-at:{normalized_expires_at}",
        )
        if runtime_dt < valid_from_dt:
            return InvariantResult(
                invariant="time",
                passed=False,
                reason="authority_not_yet_current",
                evidence_references=authority_refs,
            )
        if runtime_dt >= expires_dt:
            return InvariantResult(
                invariant="time",
                passed=False,
                reason="authority_expired",
                evidence_references=authority_refs,
            )

    evidence_references = [
        RUNTIME_TEMPORAL_EVIDENCE_REFERENCE,
        f"time:runtime:{normalized_runtime_timestamp}",
    ]

    if normalized_claimed_timestamp is not None:
        evidence_references.extend([
            CLAIMED_TEMPORAL_EVIDENCE_REFERENCE,
            f"time:claimed:{normalized_claimed_timestamp}",
        ])

    if all(value is not None for value in authority_values):
        evidence_references.extend([
            f"authority:temporal:{temporal_evidence.authority_reference}",
            f"time:authority-valid-from:{normalized_valid_from}",
            f"time:authority-expires-at:{normalized_expires_at}",
        ])
        reason = (
            "authoritative runtime timestamp and bound authority "
            "lifetime are current"
        )
    else:
        reason = (
            "authoritative runtime timestamp is valid; "
            "caller timestamp, when supplied, is treated "
            "only as a temporal claim"
        )

    return InvariantResult(
        invariant="time",
        passed=True,
        reason=reason,
        evidence_references=tuple(evidence_references),
    )

def evaluate_genesis_invariant(
    proposal: TransitionProposal,
    identity_evidence: IdentityProvenanceEvidence,
) -> InvariantResult:
    """
    Evaluate transition-bound actor identity under runtime authentication
    and canonical guest policy. This does not establish consequence origin.
    """

    if not isinstance(proposal, TransitionProposal):
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="transition_proposal_required",
        )

    if not isinstance(
        identity_evidence,
        IdentityProvenanceEvidence,
    ):
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="identity_provenance_evidence_required",
        )

    evidence_reference = (
        f"runtime:identity:{identity_evidence.principal_reference}"
    )

    if identity_evidence.transition_id != proposal.transition_id:
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="identity_transition_id_mismatch",
            evidence_references=(evidence_reference,),
        )

    if identity_evidence.origin_class == "local_personal_override":
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="local_personal_override_not_authenticated",
            evidence_references=(evidence_reference,),
        )

    if identity_evidence.session_id != proposal.session_id:
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="identity_session_does_not_match_transition",
            evidence_references=(evidence_reference,),
        )

    expected_actor_id = (
        f"{identity_evidence.actor_type}:"
        f"{identity_evidence.session_id}"
    )

    if proposal.actor_id != expected_actor_id:
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="identity_actor_does_not_match_transition",
            evidence_references=(evidence_reference,),
        )

    if identity_evidence.origin_class == "cognito_verified":
        if not identity_evidence.authenticated_subject:
            return InvariantResult(
                invariant="genesis",
                passed=False,
                reason="cognito_authenticated_subject_required",
                evidence_references=(evidence_reference,),
            )

        if not identity_evidence.principal_reference.startswith(
            "cognito:"
        ):
            return InvariantResult(
                invariant="genesis",
                passed=False,
                reason="cognito_origin_requires_cognito_principal",
                evidence_references=(evidence_reference,),
            )

        expected_identity = _COGNITO_PRINCIPAL_BINDINGS.get(
            identity_evidence.principal_reference
        )

        actual_identity = (
            identity_evidence.actor_type,
            identity_evidence.session_id,
        )

        if expected_identity != actual_identity:
            return InvariantResult(
                invariant="genesis",
                passed=False,
                reason="cognito_principal_does_not_match_actor",
                evidence_references=(evidence_reference,),
            )

    if identity_evidence.origin_class == "cognito_lab_verified":
        if not identity_evidence.authenticated_subject:
            return InvariantResult(
                invariant="genesis",
                passed=False,
                reason="cognito_authenticated_subject_required",
                evidence_references=(evidence_reference,),
            )

        if not is_installed_governed_boundary(
            consequence_type=proposal.consequence_type,
            boundary=proposal.boundary,
        ):
            return InvariantResult(
                invariant="genesis",
                passed=False,
                reason="cognito_lab_identity_outside_action_lab",
                evidence_references=(evidence_reference,),
            )

        expected_identity = _COGNITO_LAB_PRINCIPAL_BINDINGS.get(
            identity_evidence.principal_reference
        )
        actual_identity = (
            identity_evidence.actor_type,
            identity_evidence.session_id,
        )
        if expected_identity != actual_identity:
            return InvariantResult(
                invariant="genesis",
                passed=False,
                reason="cognito_lab_principal_does_not_match_actor",
                evidence_references=(evidence_reference,),
            )

    if (
        identity_evidence.origin_class == "guest"
        and identity_evidence.actor_type != "guest"
    ):
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="guest_origin_requires_guest_actor",
            evidence_references=(evidence_reference,),
        )

    if (
        identity_evidence.origin_class == "guest"
        and identity_evidence.principal_reference != f"guest:{proposal.session_id}"
    ):
        return InvariantResult(
            invariant="genesis",
            passed=False,
            reason="guest_principal_does_not_match_session",
            evidence_references=(evidence_reference,),
        )

    return InvariantResult(
        invariant="genesis",
        passed=True,
        reason=(
            "transition actor identity is attributable to "
            "runtime-authenticated or canonical guest provenance"
        ),
        evidence_references=(evidence_reference,),
    )

def evaluate_boundary_invariant(
    proposal: TransitionProposal,
    release_evidence: BoundaryReleaseEvidence | None = None,
) -> InvariantResult:
    """Admit a transition-bound release operation, not attest actual confinement."""
    evidence_references: tuple[str, ...] = ()

    def fail(reason: str) -> InvariantResult:
        return InvariantResult(
            invariant="boundary", passed=False, reason=reason,
            evidence_references=evidence_references,
        )

    if not isinstance(proposal, TransitionProposal):
        return fail("transition_proposal_required")
    if not isinstance(release_evidence, BoundaryReleaseEvidence):
        return fail("boundary_release_evidence_required")
    evidence_references = (
        f"runtime:boundary:{release_evidence.transition_id}:"
        f"{release_evidence.consequence_type}:{release_evidence.boundary}:"
        f"{release_evidence.release_operation}:{release_evidence.release_destination}:"
        f"{release_evidence.release_consequence_digest}",
    )
    boundary_binding = _AUTHORIZED_NON_ACTION_BOUNDARIES.get(
        (proposal.consequence_type, proposal.boundary)
    )
    if boundary_binding is None:
        try:
            descriptor = resolve_governed_boundary(
                consequence_type=proposal.consequence_type,
                boundary=proposal.boundary,
            )
        except GovernedActionRegistryError:
            return fail("consequence_not_authorized_for_boundary")
        boundary_binding = (
            descriptor.release_operation,
            descriptor.release_destination,
        )
        evidence_references = (
            *evidence_references,
            (
                "runtime:governed-action-registry:"
                f"{governed_action_registry_digest()}:"
                f"{descriptor.adapter_id}"
            ),
        )

    for field, expected in (
        ("transition_id", proposal.transition_id),
        ("consequence_type", proposal.consequence_type),
        ("boundary", proposal.boundary),
        ("release_consequence_digest", proposal.proposed_consequence_digest),
    ):
        if getattr(release_evidence, field) != expected:
            return fail(f"boundary_{field}_mismatch")

    expected_operation, expected_destination = boundary_binding
    if release_evidence.release_operation != expected_operation:
        return fail("boundary_release_operation_not_authorized")
    if release_evidence.release_destination != expected_destination:
        return fail("boundary_release_destination_not_authorized")

    return InvariantResult(
        invariant="boundary",
        passed=True,
        reason="server-selected release operation and destination are allowed and bound to the exact transition consequence",
        evidence_references=evidence_references,
    )

def evaluate_causality_invariant(
    proposal: TransitionProposal,
    execution_evidence: ModelExecutionEvidence,
) -> InvariantResult:
    """
    Evaluate whether the successful runtime execution path accounts for
    the exact proposed consequence.

    Execution success alone is insufficient. The consequence digest
    recorded by execution evidence must match the consequence committed
    to by the transition proposal.
    """

    if not isinstance(proposal, TransitionProposal):
        return InvariantResult(
            invariant="causality",
            passed=False,
            reason="transition_proposal_required",
        )

    if isinstance(
        execution_evidence,
        TypedConsequenceProductionEvidenceV1,
    ):
        references = (
            f"runtime:production:{execution_evidence.producer_id}:"
            f"{execution_evidence.status}",
            (
                "runtime:production:transition:"
                f"{execution_evidence.transition_id}"
            ),
            (
                "runtime:production:request:"
                f"{execution_evidence.request_digest}"
            ),
            (
                "runtime:production:consequence:"
                f"{execution_evidence.produced_consequence_digest}"
            ),
        )

        def production_fail(reason: str) -> InvariantResult:
            return InvariantResult(
                invariant="causality",
                passed=False,
                reason=reason,
                evidence_references=references,
            )

        if execution_evidence.transition_id != proposal.transition_id:
            return production_fail(
                "typed_production_transition_id_mismatch"
            )
        if execution_evidence.request_id != proposal.request_id:
            return production_fail(
                "typed_production_request_id_mismatch"
            )
        if (
            execution_evidence.consequence_type
            != proposal.consequence_type
        ):
            return production_fail(
                "typed_production_consequence_type_mismatch"
            )
        if (
            execution_evidence.produced_consequence_digest
            != proposal.proposed_consequence_digest
        ):
            return production_fail(
                "produced_consequence_digest_mismatch"
            )

        return InvariantResult(
            invariant="causality",
            passed=True,
            reason=(
                "typed local production evidence binds this transition "
                "to the exact proposed consequence"
            ),
            evidence_references=references,
        )

    if not isinstance(
        execution_evidence,
        ModelExecutionEvidence,
    ):
        return InvariantResult(
            invariant="causality",
            passed=False,
            reason="model_execution_evidence_required",
        )

    evidence_reference = (
        f"runtime:execution:"
        f"{execution_evidence.model_backend}:"
        f"{execution_evidence.status}"
    )

    references = [evidence_reference,
                  f"runtime:execution:transition:{execution_evidence.submitted_transition_id}"]
    for field in ("request_id", "returned_transition_id", "decision_receipt_id",
                  "release_receipt_id", "consequence_receipt_id", "evidence_record_id"):
        value = getattr(execution_evidence, field)
        if value:
            references.append(f"runtime:execution:{field}:{value}")
    observation = execution_evidence.observation
    if isinstance(observation, ExecutionObservation):
        references.extend((f"runtime:execution:request:{observation.request_digest}",
                           f"runtime:execution:returned_text:{observation.returned_text_digest}"))

    def fail(reason):
        return InvariantResult(invariant="causality", passed=False, reason=reason,
                               evidence_references=tuple(references))

    if not execution_evidence.succeeded:
        return InvariantResult(
            invariant="causality",
            passed=False,
            reason=(
                execution_evidence.error_reason
                or "model_execution_failed"
            ),
            evidence_references=tuple(references),
        )

    if (
        execution_evidence.produced_consequence_digest
        != proposal.proposed_consequence_digest
    ):
        return InvariantResult(
            invariant="causality",
            passed=False,
            reason="produced_consequence_digest_mismatch",
            evidence_references=tuple(references),
        )

    if (
        execution_evidence.model_backend == "governed_aws"
        and execution_evidence.upstream_response_released
        is not True
    ):
        return InvariantResult(
            invariant="causality",
            passed=False,
            reason="governed_response_not_released",
            evidence_references=tuple(references),
        )

    if execution_evidence.submitted_transition_id != proposal.transition_id:
        return fail("execution_transition_id_mismatch")
    if execution_evidence.error_reason is not None:
        return fail("successful_execution_has_error")
    if not isinstance(observation, ExecutionObservation):
        return fail("execution_observation_required")
    if observation.transition_id != proposal.transition_id:
        return fail("execution_observation_transition_mismatch")
    if observation.model_backend != execution_evidence.model_backend:
        return fail("execution_observation_backend_mismatch")
    if observation.consequence_digest != proposal.proposed_consequence_digest:
        return fail("execution_observation_consequence_mismatch")
    if execution_evidence.model_backend in {"together", "bedrock_scout"}:
        if execution_evidence.status != "COMPLETED":
            return fail("execution_status_invalid")
    elif execution_evidence.model_backend == "governed_aws":
        if execution_evidence.status != "RELEASED" or execution_evidence.http_status != 200:
            return fail("governed_execution_status_invalid")
        if execution_evidence.returned_transition_id != proposal.transition_id:
            return fail("governed_transition_id_mismatch")
        if not execution_evidence.request_id:
            return fail("governed_request_id_required")
        if execution_evidence.request_id != proposal.request_id:
            return fail("governed_request_id_mismatch")
    else:
        return fail("execution_backend_invalid")

    return InvariantResult(
        invariant="causality",
        passed=True,
        reason=(
            "local dispatch/result observation binds this transition to the "
            "filtered proposed consequence"
        ),
        evidence_references=tuple(references),
    )

def evaluate_continuity_invariant(
    proposal: TransitionProposal,
    *,
    continuity_evidence: ContinuityRequirementEvidence,
) -> InvariantResult:
    """
    Evaluate the authoritative runtime determination of whether this
    transition depends on state established before the current request.

    Reference resolution and semantic agreement remain separately
    governed by Reference and Alignment.
    """

    if not isinstance(proposal, TransitionProposal):
        return InvariantResult(
            invariant="continuity",
            passed=False,
            reason="transition_proposal_required",
        )

    if not isinstance(
        continuity_evidence,
        ContinuityRequirementEvidence,
    ):
        return InvariantResult(
            invariant="continuity",
            passed=False,
            reason="continuity_requirement_evidence_required",
        )

    continuity_reference = (
        "runtime:continuity:"
        f"{continuity_evidence.determination_source}"
    )

    basis_references = tuple(
        f"continuity:basis:{basis}"
        for basis in continuity_evidence.requirement_bases
    )

    if continuity_evidence.requirement_status == "unresolved":
        return InvariantResult(
            invariant="continuity",
            passed=False,
            reason="inherited_state_requirement_unresolved",
            evidence_references=(
                continuity_reference,
                *basis_references,
            ),
        )

    if not continuity_evidence.inherited_state_required:
        return InvariantResult(
            invariant="continuity",
            passed=True,
            reason=(
                "authoritative runtime determination found no "
                "inherited-state dependency"
            ),
            evidence_references=(
                continuity_reference,
                *basis_references,
            ),
        )

    if not proposal.reference_bindings:
        return InvariantResult(
            invariant="continuity",
            passed=False,
            reason="required_inherited_state_not_bound",
            evidence_references=(
                continuity_reference,
                *basis_references,
            ),
        )

    return InvariantResult(
        invariant="continuity",
        passed=True,
        reason=(
            "authoritative runtime determination required inherited "
            "state and the transition carries inherited references"
        ),
        evidence_references=(
            continuity_reference,
            *basis_references,
            *proposal.reference_bindings,
        ),
    )

def evaluate_reference_invariant(
    reference_evidence: ReferenceResolutionEvidence,
) -> InvariantResult:
    """Resolve each persistent ID to the same role/content snapshot consumed."""
    if not isinstance(reference_evidence, ReferenceResolutionEvidence):
        return InvariantResult(
            invariant="reference", passed=False,
            reason="reference_resolution_evidence_required",
        )

    requested = set(reference_evidence.requested_references)
    resolved = set(reference_evidence.resolved_references)
    consumed_bindings = reference_evidence.consumed_content_digests
    resolved_bindings = reference_evidence.resolved_content_digests
    forensic = tuple(sorted(requested | resolved)) + tuple(
        f"runtime:reference:{kind}:{reference}:{digest}"
        for kind, bindings in (("consumed", consumed_bindings), ("resolved", resolved_bindings))
        for reference, digest in bindings
    )

    def fail(reason: str) -> InvariantResult:
        return InvariantResult(
            invariant="reference", passed=False, reason=reason,
            evidence_references=forensic,
        )

    if reference_evidence.required and not requested:
        return fail("required_reference_not_supplied")
    if resolved - requested:
        return fail("unexpected_reference_resolution")
    if requested - resolved:
        return fail("requested_reference_not_resolved")

    consumed_digests = dict(consumed_bindings)
    resolved_digests = dict(resolved_bindings)
    if (len(consumed_digests) != len(consumed_bindings)
            or len(resolved_digests) != len(resolved_bindings)):
        return fail("duplicate_reference_content_binding")
    if set(consumed_digests) != requested or set(resolved_digests) != resolved:
        return fail("reference_content_bindings_mismatch")
    if consumed_digests != resolved_digests:
        return fail("reference_content_digest_mismatch")

    return InvariantResult(
        invariant="reference", passed=True,
        reason=("all requested persistent references resolved to consumed content"
                if requested else "no persistent references were required by this transition"),
        evidence_references=forensic,
    )

def evaluate_alignment_invariant(
    alignment_verification: AlignmentVerification | None,
    *,
    proposal: TransitionProposal,
    alignment_verification_required: bool,
) -> InvariantResult:
    """
    Evaluate whether the proposed consequence requires and satisfies
    semantic Alignment verification.

    Alignment may be required by inherited state, current admitted
    evidence, or another authorized evidence source. The substantive
    semantic verification is performed upstream by the dedicated
    AlignmentVerification path.
    """

    if not isinstance(alignment_verification_required, bool):
        return InvariantResult(
            invariant="alignment",
            passed=False,
            reason=(
                "alignment_verification_required_must_be_boolean"
            ),
        )

    if (
        isinstance(alignment_verification, AlignmentVerification)
        and not alignment_verification.passed
    ):
        return alignment_verification.to_invariant_result()

    if isinstance(alignment_verification, AlignmentVerification):
        if not isinstance(proposal, TransitionProposal):
            return InvariantResult(
                invariant="alignment",
                passed=False,
                reason="alignment_proposal_required",
            )
        if (
            alignment_verification.proposed_consequence_digest
            != proposal.proposed_consequence_digest
        ):
            return InvariantResult(
                invariant="alignment",
                passed=False,
                reason="alignment_proposed_consequence_digest_mismatch",
                evidence_references=alignment_verification.evidence_references,
            )

    if not alignment_verification_required:
        return InvariantResult(
            invariant="alignment",
            passed=True,
            reason=(
                "transition does not require semantic "
                "alignment verification"
            ),
        )

    if not isinstance(
        alignment_verification,
        AlignmentVerification,
    ):
        return InvariantResult(
            invariant="alignment",
            passed=False,
            reason="alignment_verification_required",
        )

    return alignment_verification.to_invariant_result()

def _evaluate_coherence_mechanism(
    proposal: TransitionProposal,
    runtime_evidence: SCQOSRuntimeEvidence,
    *,
    alignment_verification_required: bool = False,
    alignment_verification: AlignmentVerification | None = None,
) -> InvariantResult:
    """
    Evaluate whether the runtime proof chain is internally consistent
    across the transition-scoped bindings exposed by its evidence records.

    Each evidence object may be structurally valid on its own while
    still contradicting another part of the same transition proof.
    Coherence verifies those cross-evidence relationships as an internal
    mechanism. It does not independently occupy an invariant slot.
    """

    if not isinstance(proposal, TransitionProposal):
        return InvariantResult(
            invariant="consciousness",
            passed=False,
            reason="transition_proposal_required",
        )

    if not isinstance(
        runtime_evidence,
        SCQOSRuntimeEvidence,
    ):
        return InvariantResult(
            invariant="consciousness",
            passed=False,
            reason="runtime_evidence_required",
        )

    evidence_reference = f"runtime:coherence:{proposal.transition_id}"
    forensic = [evidence_reference]

    def fail(reason: str) -> InvariantResult:
        return InvariantResult(
            invariant="consciousness", passed=False, reason=reason,
            evidence_references=tuple(forensic),
        )

    # The aggregate dataclass does not validate nested types. Gather all
    # available typed records before failing, retaining substituted values.
    invalid = []
    for name, contract in (
        ("temporal", TemporalEvidence),
        ("continuity", ContinuityRequirementEvidence),
        ("identity", IdentityProvenanceEvidence),
        ("references", ReferenceResolutionEvidence),
        (
            "execution",
            (
                ModelExecutionEvidence,
                TypedConsequenceProductionEvidenceV1,
            ),
        ),
        ("boundary", BoundaryReleaseEvidence),
    ):
        record = getattr(runtime_evidence, name)
        if not isinstance(record, contract):
            invalid.append(name)
            continue
        for field, value in record.to_contract_dict().items():
            if value is not None:
                forensic.append(f"runtime:coherence:{name}:{field}:{value}")
    if isinstance(alignment_verification, AlignmentVerification):
        forensic.extend(alignment_verification.evidence_references)
        forensic.append(
            "runtime:coherence:alignment:consequence:"
            + alignment_verification.proposed_consequence_digest
        )
    if invalid:
        return fail(f"coherence_{invalid[0]}_evidence_required")

    execution = runtime_evidence.execution
    if isinstance(
        execution,
        TypedConsequenceProductionEvidenceV1,
    ):
        if execution.transition_id != proposal.transition_id:
            return fail("typed_production_transition_id_mismatch")
        if execution.request_id != proposal.request_id:
            return fail("typed_production_request_id_mismatch")
        if execution.consequence_type != proposal.consequence_type:
            return fail("typed_production_consequence_type_mismatch")
    else:
        if (
            execution.submitted_transition_id
            != proposal.transition_id
        ):
            return InvariantResult(
                invariant="consciousness",
                passed=False,
                reason="submitted_transition_id_mismatch",
                evidence_references=tuple(forensic),
            )

        if (
            execution.returned_transition_id is not None
            and execution.returned_transition_id
            != proposal.transition_id
        ):
            return InvariantResult(
                invariant="consciousness",
                passed=False,
                reason="returned_transition_id_mismatch",
                evidence_references=tuple(forensic),
            )

    if (
        proposal.reference_bindings
        != runtime_evidence.references.requested_references
    ):
        return InvariantResult(
            invariant="consciousness",
            passed=False,
            reason=(
                "reference_bindings_do_not_match_"
                "requested_references"
            ),
            evidence_references=tuple(forensic),
        )

    if (
        runtime_evidence.continuity.inherited_state_required
        != runtime_evidence.references.required
    ):
        return InvariantResult(
            invariant="consciousness",
            passed=False,
            reason=(
                "continuity_reference_requirement_mismatch"
            ),
            evidence_references=tuple(forensic),
        )

    if isinstance(execution, ModelExecutionEvidence):
        if (
            execution.model_backend == "governed_aws"
            and execution.succeeded
        ):
            required_provenance = (
                execution.returned_transition_id,
                execution.request_id,
                execution.decision_receipt_id,
                execution.release_receipt_id,
                execution.consequence_receipt_id,
                execution.evidence_record_id,
            )

            if any(
                value is None
                for value in required_provenance
            ):
                return InvariantResult(
                    invariant="consciousness",
                    passed=False,
                    reason="governed_provenance_incomplete",
                    evidence_references=tuple(forensic),
                )

            if execution.request_id != proposal.request_id:
                return InvariantResult(
                    invariant="consciousness",
                    passed=False,
                    reason="governed_request_id_mismatch",
                    evidence_references=tuple(forensic),
                )

        if (
            execution.request_id is not None
            and execution.request_id != proposal.request_id
        ):
            return fail("coherence_request_id_mismatch")

    identity = runtime_evidence.identity
    boundary = runtime_evidence.boundary
    for name, actual, expected in (
        ("identity_transition_id", identity.transition_id, proposal.transition_id),
        ("identity_session", identity.session_id, proposal.session_id),
        ("identity_actor", f"{identity.actor_type}:{identity.session_id}", proposal.actor_id),
        ("boundary_transition_id", boundary.transition_id, proposal.transition_id),
        ("boundary_consequence_type", boundary.consequence_type, proposal.consequence_type),
        ("boundary", boundary.boundary, proposal.boundary),
        ("boundary_consequence_digest", boundary.release_consequence_digest, proposal.proposed_consequence_digest),
    ):
        if actual != expected:
            return fail(f"coherence_{name}_mismatch")

    # Failure/status/authorization semantics remain with the owner invariants.
    # Any supplied output or observation must still agree, even on failure.
    if (
        execution.produced_consequence_digest
        != proposal.proposed_consequence_digest
    ):
        return fail("coherence_execution_consequence_mismatch")

    if isinstance(execution, ModelExecutionEvidence):
        observation = execution.observation
        if execution.succeeded and observation is None:
            return fail("coherence_execution_observation_required")
        if observation is not None:
            for name, actual, expected in (
                (
                    "transition",
                    observation.transition_id,
                    proposal.transition_id,
                ),
                (
                    "backend",
                    observation.model_backend,
                    execution.model_backend,
                ),
                (
                    "consequence",
                    observation.consequence_digest,
                    proposal.proposed_consequence_digest,
                ),
            ):
                if actual != expected:
                    return fail(
                        f"coherence_observation_{name}_mismatch"
                    )

    if not isinstance(alignment_verification_required, bool):
        return fail("coherence_alignment_requirement_invalid")
    if alignment_verification is not None and not isinstance(alignment_verification, AlignmentVerification):
        return fail("coherence_alignment_verification_invalid")
    if alignment_verification_required and alignment_verification is None:
        return fail("coherence_alignment_verification_required")
    if (alignment_verification is not None
            and alignment_verification.proposed_consequence_digest != proposal.proposed_consequence_digest):
        return fail("coherence_alignment_consequence_mismatch")
    if (
        alignment_verification_required
        and alignment_verification is not None
        and not alignment_verification.passed
    ):
        return fail("coherence_alignment_verification_failed")

    return InvariantResult(
        invariant="consciousness",
        passed=True,
        reason=(
            "supplied typed evidence agrees with the proposal on exposed "
            "transition, actor, release, consequence and requirement bindings; "
            "owner-invariant admission and unbound evidence provenance remain separate"
        ),
        evidence_references=tuple(forensic),
    )


@dataclass(frozen=True)
class ConsciousnessRequalificationContext:
    """Runtime inputs proving how a material change was requalified.

    This is an evaluation carrier, not durable proof and not authority. The
    durable objects remain requalification_v1, baton_transfer_v1, and the
    canonical transition proof bundle.
    """

    prior_qualification: QualificationSnapshotV1
    material_change: MaterialChangeEvidenceV1
    requalification: RequalificationV1
    proof_bundle: TransitionProofBundleV1 | None = None
    resolved_artifact_digests: Mapping[str, str] | None = None
    baton_transfer: BatonTransferV1 | None = None
    predecessor_lineage: AuthorityLineageV1 | None = None
    successor_lineage: AuthorityLineageV1 | None = None


def evaluate_consciousness_invariant(
    proposal: TransitionProposal,
    runtime_evidence: SCQOSRuntimeEvidence,
    *,
    alignment_verification_required: bool = False,
    alignment_verification: AlignmentVerification | None = None,
    requalification_context: ConsciousnessRequalificationContext | None = None,
) -> InvariantResult:
    """Evaluate invariant #8 while using coherence only as its mechanism.

    With no explicit material-change evidence, current typed evidence must be
    coherent. When a material change is supplied, automatic continuation is
    blocked unless requalification_v1 validates; REQUALIFIED additionally
    requires a new fully resolved transition_proof_bundle_v1, plus
    baton_transfer_v1 when authority lineage changed.
    """

    coherence = _evaluate_coherence_mechanism(
        proposal,
        runtime_evidence,
        alignment_verification_required=alignment_verification_required,
        alignment_verification=alignment_verification,
    )
    if not coherence.passed:
        return coherence

    if requalification_context is None:
        return InvariantResult(
            invariant="consciousness",
            passed=True,
            reason=(
                "coherence mechanism found no current cross-evidence "
                "contradiction and no material-change evidence was supplied"
            ),
            evidence_references=coherence.evidence_references,
        )

    if type(requalification_context) is not ConsciousnessRequalificationContext:
        return InvariantResult(
            invariant="consciousness",
            passed=False,
            reason="consciousness_requalification_context_invalid",
            evidence_references=coherence.evidence_references,
        )

    context = requalification_context
    forensic = list(coherence.evidence_references)
    for reference in (
        f"qualification:{context.prior_qualification.digest}",
        f"material-change:{context.material_change.digest}",
        f"requalification:{context.requalification.digest}",
    ):
        if reference not in forensic:
            forensic.append(reference)
    if context.baton_transfer is not None:
        forensic.append(f"baton-transfer:{context.baton_transfer.digest}")

    def fail(reason: str) -> InvariantResult:
        return InvariantResult(
            invariant="consciousness",
            passed=False,
            reason=reason,
            evidence_references=tuple(forensic),
        )

    try:
        validate_requalification(
            context.prior_qualification,
            context.material_change,
            context.requalification,
            baton_transfer=context.baton_transfer,
            predecessor_lineage=context.predecessor_lineage,
            successor_lineage=context.successor_lineage,
        )
    except ConstitutionalContractError as error:
        return fail(f"consciousness_requalification_invalid:{error}")

    if context.requalification.decision is RequalificationDecision.HOLD:
        return fail("consciousness_material_change_holds_automatic_continuation")

    if (
        context.proof_bundle is None
        or context.resolved_artifact_digests is None
    ):
        return fail("consciousness_requalified_proof_required")

    result = context.requalification.resulting_qualification
    if result is None:
        return fail("consciousness_requalified_snapshot_required")
    if result.transition_id != proposal.transition_id:
        return fail("consciousness_requalified_transition_mismatch")
    if result.session_id != proposal.session_id:
        return fail("consciousness_requalified_session_mismatch")

    try:
        validate_requalification_for_resume(
            context.prior_qualification,
            context.material_change,
            context.requalification,
            context.proof_bundle,
            context.resolved_artifact_digests,
            baton_transfer=context.baton_transfer,
            predecessor_lineage=context.predecessor_lineage,
            successor_lineage=context.successor_lineage,
        )
    except ConstitutionalContractError as error:
        return fail(f"consciousness_requalification_invalid:{error}")

    forensic.append(f"transition-proof-bundle:{context.proof_bundle.digest}")
    return InvariantResult(
        invariant="consciousness",
        passed=True,
        reason=(
            "material change invalidated prior automatic continuation and was "
            "explicitly requalified against new canonical proof"
        ),
        evidence_references=tuple(forensic),
    )


def evaluate_coherence_invariant(
    proposal: TransitionProposal,
    runtime_evidence: SCQOSRuntimeEvidence,
    *,
    alignment_verification_required: bool = False,
    alignment_verification: AlignmentVerification | None = None,
) -> InvariantResult:
    """Compatibility entry point; coherence is a mechanism, not invariant #8."""

    return evaluate_consciousness_invariant(
        proposal,
        runtime_evidence,
        alignment_verification_required=alignment_verification_required,
        alignment_verification=alignment_verification,
    )

def evaluate_transition_invariants(
    *,
    proposal: TransitionProposal,
    runtime_evidence: SCQOSRuntimeEvidence,
    alignment_verification_required: bool,
    alignment_verification: AlignmentVerification | None,
    consciousness_requalification_context: ConsciousnessRequalificationContext | None = None,
) -> tuple[InvariantResult, ...]:
    """
    Evaluate one transition across the complete canonical SCQOS
    invariant chain.

    The returned results always follow SCQOS_INVARIANTS order.
    """

    results = (
        evaluate_time_invariant(
            runtime_evidence.temporal
            if isinstance(
                runtime_evidence,
                SCQOSRuntimeEvidence,
            )
            else None
        ),
        evaluate_continuity_invariant(
            proposal,
            continuity_evidence=(
                runtime_evidence.continuity
                if isinstance(
                    runtime_evidence,
                    SCQOSRuntimeEvidence,
                )
                else None
            ),
        ),
        evaluate_alignment_invariant(
            alignment_verification,
            proposal=proposal,
            alignment_verification_required=(
                alignment_verification_required
            ),
        ),
        evaluate_genesis_invariant(
            proposal,
            (
                runtime_evidence.identity
                if isinstance(
                    runtime_evidence,
                    SCQOSRuntimeEvidence,
                )
                else None
            ),
        ),
        evaluate_boundary_invariant(
            proposal,
            runtime_evidence.boundary
            if isinstance(runtime_evidence, SCQOSRuntimeEvidence)
            else None,
        ),
        evaluate_reference_invariant(
            (
                runtime_evidence.references
                if isinstance(
                    runtime_evidence,
                    SCQOSRuntimeEvidence,
                )
                else None
            )
        ),
        evaluate_causality_invariant(
            proposal,
            (
                runtime_evidence.execution
                if isinstance(
                    runtime_evidence,
                    SCQOSRuntimeEvidence,
                )
                else None
            ),
        ),
        evaluate_consciousness_invariant(
            proposal,
            runtime_evidence,
            alignment_verification_required=alignment_verification_required,
            alignment_verification=alignment_verification,
            requalification_context=consciousness_requalification_context,
        ),
    )

    if tuple(
        result.invariant
        for result in results
    ) != SCQOS_INVARIANTS:
        raise RuntimeError(
            "scqos_invariant_order_violation"
        )

    return results

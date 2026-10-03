"""Constitution v1 explicit requalification contracts.

Material change invalidates reuse of a prior qualification. Resume requires a
new canonical transition-proof bundle, and any changed authority lineage must
be accompanied by a separately validated baton transfer. Structural validity
never issues permission by itself.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from authority_lineage import AuthorityLineageV1
from baton_transfer import BatonTransferV1, validate_baton_transfer
from constitutional_binding import (
    _Contract,
    _canonical_time,
    _digest,
    _ref,
    _require,
)
from transition_proof_bundle import (
    TransitionProofBundleV1,
    validate_transition_proof_bundle_for_release,
)


class MaterialChangeClass(str, Enum):
    NEW_EVIDENCE = "new_evidence"
    CONTRADICTION = "contradiction"
    CHANGED_STATE = "changed_state"
    CHANGED_AUTHORITY_INTERPRETATION = "changed_authority_interpretation"


class RequalificationDecision(str, Enum):
    HOLD = "HOLD"
    REQUALIFIED = "REQUALIFIED"


@dataclass(frozen=True)
class QualificationSnapshotV1(_Contract):
    """One fully qualified understanding eligible for governed reuse."""

    VERSION = "qualification_snapshot_v1"

    qualification_id: str
    transition_id: str
    session_id: str
    constitutional_binding_digest: str
    authority_lineage_digest: str
    purpose_binding_digest: str
    transition_proof_bundle_digest: str
    current_authority_id: str
    current_authority_digest: str
    qualified_at: str

    def __post_init__(self) -> None:
        _require(type(self) is QualificationSnapshotV1, "exact_contract_type_required")
        for value, code in (
            (self.qualification_id, "qualification_id_invalid"),
            (self.transition_id, "qualification_transition_id_invalid"),
            (self.session_id, "qualification_session_id_invalid"),
            (self.current_authority_id, "qualification_authority_id_invalid"),
        ):
            _ref(value, code)
        for value, code in (
            (self.constitutional_binding_digest, "qualification_constitutional_binding_digest_invalid"),
            (self.authority_lineage_digest, "qualification_authority_lineage_digest_invalid"),
            (self.purpose_binding_digest, "qualification_purpose_binding_digest_invalid"),
            (self.transition_proof_bundle_digest, "qualification_proof_bundle_digest_invalid"),
            (self.current_authority_digest, "qualification_authority_digest_invalid"),
        ):
            _digest(value, code)
        _canonical_time(self.qualified_at, "qualification_time_invalid")


@dataclass(frozen=True)
class MaterialChangeEvidenceV1(_Contract):
    """Durable evidence that a prior qualified understanding materially changed."""

    VERSION = "material_change_evidence_v1"

    change_id: str
    prior_qualification_digest: str
    change_class: MaterialChangeClass
    prior_state_digest: str
    changed_state_digest: str
    evidence_reference: str
    evidence_digest: str
    observed_at: str

    def __post_init__(self) -> None:
        _require(type(self) is MaterialChangeEvidenceV1, "exact_contract_type_required")
        _ref(self.change_id, "material_change_id_invalid")
        _require(type(self.change_class) is MaterialChangeClass, "material_change_class_invalid")
        _ref(self.evidence_reference, "material_change_evidence_reference_invalid")
        for value, code in (
            (self.prior_qualification_digest, "material_change_prior_qualification_digest_invalid"),
            (self.prior_state_digest, "material_change_prior_state_digest_invalid"),
            (self.changed_state_digest, "material_change_changed_state_digest_invalid"),
            (self.evidence_digest, "material_change_evidence_digest_invalid"),
        ):
            _digest(value, code)
        _require(
            self.prior_state_digest != self.changed_state_digest,
            "material_change_requires_distinct_state",
        )
        _canonical_time(self.observed_at, "material_change_observed_at_invalid")


@dataclass(frozen=True)
class RequalificationV1(_Contract):
    """Explicit HOLD-and-reevaluate record after material change."""

    VERSION = "requalification_v1"

    requalification_id: str
    source_qualification_digest: str
    triggering_change_digest: str
    invalidation_hold_reference: str
    invalidation_hold_digest: str
    evaluated_constitutional_binding_digest: str
    evaluated_authority_lineage_digest: str
    evaluated_purpose_binding_digest: str
    candidate_transition_proof_bundle_digest: str | None
    baton_transfer_digest: str | None
    decision: RequalificationDecision
    resulting_qualification: QualificationSnapshotV1 | None
    started_at: str
    evaluated_at: str

    def __post_init__(self) -> None:
        _require(type(self) is RequalificationV1, "exact_contract_type_required")
        _ref(self.requalification_id, "requalification_id_invalid")
        _ref(self.invalidation_hold_reference, "requalification_hold_reference_invalid")
        for value, code in (
            (self.source_qualification_digest, "requalification_source_digest_invalid"),
            (self.triggering_change_digest, "requalification_change_digest_invalid"),
            (self.invalidation_hold_digest, "requalification_hold_digest_invalid"),
            (self.evaluated_constitutional_binding_digest, "requalification_constitutional_binding_digest_invalid"),
            (self.evaluated_authority_lineage_digest, "requalification_authority_lineage_digest_invalid"),
            (self.evaluated_purpose_binding_digest, "requalification_purpose_binding_digest_invalid"),
        ):
            _digest(value, code)
        if self.candidate_transition_proof_bundle_digest is not None:
            _digest(self.candidate_transition_proof_bundle_digest, "requalification_candidate_proof_digest_invalid")
        if self.baton_transfer_digest is not None:
            _digest(self.baton_transfer_digest, "requalification_baton_digest_invalid")
        _require(type(self.decision) is RequalificationDecision, "requalification_decision_invalid")
        started = _canonical_time(self.started_at, "requalification_started_at_invalid")
        evaluated = _canonical_time(self.evaluated_at, "requalification_evaluated_at_invalid")
        _require(started <= evaluated, "requalification_time_reordered")

        if self.decision is RequalificationDecision.HOLD:
            _require(self.resulting_qualification is None, "hold_cannot_create_qualification")
        else:
            _require(
                type(self.resulting_qualification) is QualificationSnapshotV1,
                "requalified_snapshot_required",
            )
            _require(
                self.candidate_transition_proof_bundle_digest is not None,
                "requalified_proof_bundle_required",
            )
            result = self.resulting_qualification
            _require(
                result.transition_proof_bundle_digest == self.candidate_transition_proof_bundle_digest,
                "requalified_proof_bundle_mismatch",
            )
            _require(
                result.constitutional_binding_digest == self.evaluated_constitutional_binding_digest,
                "requalified_constitutional_binding_mismatch",
            )
            _require(
                result.authority_lineage_digest == self.evaluated_authority_lineage_digest,
                "requalified_authority_lineage_mismatch",
            )
            _require(
                result.purpose_binding_digest == self.evaluated_purpose_binding_digest,
                "requalified_purpose_binding_mismatch",
            )
            _require(
                _canonical_time(result.qualified_at, "qualification_time_invalid") >= evaluated,
                "qualification_precedes_requalification_decision",
            )


def validate_requalification(
    prior: QualificationSnapshotV1,
    change: MaterialChangeEvidenceV1,
    requalification: RequalificationV1,
    *,
    baton_transfer: BatonTransferV1 | None = None,
    predecessor_lineage: AuthorityLineageV1 | None = None,
    successor_lineage: AuthorityLineageV1 | None = None,
) -> None:
    """Bind prior qualification, material change, forced HOLD and reevaluation."""

    _require(type(prior) is QualificationSnapshotV1, "prior_qualification_required")
    _require(type(change) is MaterialChangeEvidenceV1, "material_change_required")
    _require(type(requalification) is RequalificationV1, "requalification_required")
    _require(change.prior_qualification_digest == prior.digest, "material_change_prior_qualification_mismatch")
    _require(requalification.source_qualification_digest == prior.digest, "requalification_source_mismatch")
    _require(requalification.triggering_change_digest == change.digest, "requalification_change_mismatch")

    qualified = _canonical_time(prior.qualified_at, "qualification_time_invalid")
    observed = _canonical_time(change.observed_at, "material_change_observed_at_invalid")
    started = _canonical_time(requalification.started_at, "requalification_started_at_invalid")
    _require(qualified <= observed <= started, "requalification_change_time_mismatch")

    lineage_changed = requalification.evaluated_authority_lineage_digest != prior.authority_lineage_digest
    if lineage_changed:
        _require(
            baton_transfer is not None
            and predecessor_lineage is not None
            and successor_lineage is not None,
            "authority_change_requires_baton_transfer",
        )
        _require(type(baton_transfer) is BatonTransferV1, "baton_transfer_required")
        _require(type(predecessor_lineage) is AuthorityLineageV1, "predecessor_lineage_required")
        _require(type(successor_lineage) is AuthorityLineageV1, "successor_lineage_required")
        validate_baton_transfer(predecessor_lineage, successor_lineage, baton_transfer)
        _require(prior.authority_lineage_digest == predecessor_lineage.digest, "prior_lineage_mismatch")
        _require(
            requalification.evaluated_authority_lineage_digest == successor_lineage.digest,
            "requalification_successor_lineage_mismatch",
        )
        _require(baton_transfer.triggering_change_digest == change.digest, "baton_change_mismatch")
        _require(requalification.baton_transfer_digest == baton_transfer.digest, "requalification_baton_mismatch")
        if requalification.resulting_qualification is not None:
            _require(
                (requalification.resulting_qualification.current_authority_id,
                 requalification.resulting_qualification.current_authority_digest)
                == (successor_lineage.current_authority_id, successor_lineage.current_authority_digest),
                "requalified_authority_endpoint_mismatch",
            )
    else:
        _require(baton_transfer is None, "unchanged_authority_forbids_baton_transfer")
        _require(predecessor_lineage is None and successor_lineage is None,
                 "unchanged_authority_forbids_lineage_transfer_inputs")
        _require(requalification.baton_transfer_digest is None, "unchanged_authority_forbids_baton_digest")


def validate_requalification_for_resume(
    prior: QualificationSnapshotV1,
    change: MaterialChangeEvidenceV1,
    requalification: RequalificationV1,
    proof_bundle: TransitionProofBundleV1,
    resolved_artifact_digests: Mapping[str, str],
    *,
    baton_transfer: BatonTransferV1 | None = None,
    predecessor_lineage: AuthorityLineageV1 | None = None,
    successor_lineage: AuthorityLineageV1 | None = None,
) -> None:
    """Require complete new proof before automatic governed continuation may resume."""

    validate_requalification(
        prior,
        change,
        requalification,
        baton_transfer=baton_transfer,
        predecessor_lineage=predecessor_lineage,
        successor_lineage=successor_lineage,
    )
    _require(
        requalification.decision is RequalificationDecision.REQUALIFIED,
        "requalification_hold_blocks_resume",
    )
    result = requalification.resulting_qualification
    _require(type(result) is QualificationSnapshotV1, "requalified_snapshot_required")
    _require(type(proof_bundle) is TransitionProofBundleV1, "transition_proof_bundle_required")
    _require(proof_bundle.digest == result.transition_proof_bundle_digest, "resume_proof_bundle_digest_mismatch")
    _require(proof_bundle.transition_id == result.transition_id, "resume_transition_id_mismatch")
    _require(proof_bundle.session_id == result.session_id, "resume_session_id_mismatch")
    _require(
        proof_bundle.constitutional_binding_digest == result.constitutional_binding_digest,
        "resume_constitutional_binding_mismatch",
    )
    _require(
        proof_bundle.authority_lineage_digest == result.authority_lineage_digest,
        "resume_authority_lineage_mismatch",
    )
    _require(
        proof_bundle.purpose_binding_digest == result.purpose_binding_digest,
        "resume_purpose_binding_mismatch",
    )
    _require(
        proof_bundle.digest != prior.transition_proof_bundle_digest,
        "material_change_requires_new_transition_proof_bundle",
    )
    validate_transition_proof_bundle_for_release(proof_bundle, resolved_artifact_digests)

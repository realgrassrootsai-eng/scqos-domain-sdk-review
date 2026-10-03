"""Pure, in-memory governed observation contracts. No storage or authority."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json

from governed_transition import AlignmentVerification, TransitionDecision, TransitionProposal, TransitionReceipt
from scqos_contract_digest import canonical_contract_json, contract_digest
from scqos_runtime_evidence import SCQOSRuntimeEvidence
from semantic_evidence_binding import SemanticEvidenceBindingResult


class GovernanceExperienceError(ValueError):
    """A supplied observation cannot bind the supplied source artifacts."""


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceExperienceError(f"{name}_required")
    return value


def _timestamp(value: str, name: str) -> datetime:
    _text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GovernanceExperienceError(f"{name}_invalid") from error
    if parsed.utcoffset() is None:
        raise GovernanceExperienceError(f"{name}_timezone_required")
    return parsed


@dataclass(frozen=True, init=False)
class TransitionEvidenceBundle:
    """Detached snapshot of supplied decision artifacts, not proof of their use.

    Optional nulls mean unavailable or not run, never a fabricated pass. Inner
    runtime contradictions are retained: they can be the reason for a HOLD.
    """

    _canonical_payload: str = field(repr=False)

    def __init__(self, *, proposal: TransitionProposal,
                 runtime_evidence: SCQOSRuntimeEvidence,
                 alignment_verification_required: bool,
                 alignment_verification: AlignmentVerification | None = None,
                 semantic_binding: SemanticEvidenceBindingResult | None = None,
                 response_target_result: str | None = None) -> None:
        if not isinstance(proposal, TransitionProposal):
            raise GovernanceExperienceError("proposal_required")
        if not isinstance(runtime_evidence, SCQOSRuntimeEvidence):
            raise GovernanceExperienceError("runtime_evidence_required")
        if not isinstance(alignment_verification_required, bool):
            raise GovernanceExperienceError("alignment_requirement_must_be_boolean")
        if alignment_verification is not None and not isinstance(alignment_verification, AlignmentVerification):
            raise GovernanceExperienceError("alignment_verification_invalid")
        if semantic_binding is not None and not isinstance(semantic_binding, SemanticEvidenceBindingResult):
            raise GovernanceExperienceError("semantic_binding_invalid")
        if response_target_result is not None and response_target_result not in (
            "responsive", "previous_turn_targeted", "unrelated", "indeterminate",
        ):
            raise GovernanceExperienceError("response_target_result_invalid")
        payload = {
            "schema_version": "transition_evidence_bundle_v1",
            "source_transition_id": proposal.transition_id,
            "proposal": proposal.to_contract_dict(),
            "runtime_evidence": runtime_evidence.to_contract_dict(),
            "alignment_verification_required": alignment_verification_required,
            "alignment_verification": alignment_verification.to_contract_dict() if alignment_verification else None,
            "semantic_binding": asdict(semantic_binding) if semantic_binding else None,
            "response_target": {
                "result": response_target_result,
                "provenance": None,
                "capture_status": "result_only" if response_target_result is not None else "unavailable_or_not_run",
            },
        }
        object.__setattr__(self, "_canonical_payload", canonical_contract_json(payload))

    def to_contract_dict(self) -> dict:
        """Return a fresh copy; mutations cannot change this snapshot."""
        return json.loads(self._canonical_payload)

    @property
    def digest(self) -> str:
        return contract_digest(self.to_contract_dict())


@dataclass(frozen=True, init=False)
class GovernanceExperience:
    """HOLD-only observation binding supplied artifacts, without lesson fields.

    Recorder and timestamps are supplied declarations, not authenticated by
    construction. Source payloads remain attached for in-memory inspection.
    """

    _canonical_payload: str = field(repr=False)

    def __init__(self, *, experience_id: str, source_transition_id: str,
                 source_receipt: TransitionReceipt,
                 evidence_bundle: TransitionEvidenceBundle,
                 source_receipt_digest: str, evidence_bundle_digest: str,
                 hold_class: str, observed_at: str, recorded_at: str,
                 recorder_id: str, recorder_provenance_reference: str) -> None:
        for name, value in (
            ("experience_id", experience_id), ("source_transition_id", source_transition_id),
            ("recorder_id", recorder_id), ("recorder_provenance_reference", recorder_provenance_reference),
        ):
            _text(value, name)
        if _timestamp(recorded_at, "recorded_at") < _timestamp(observed_at, "observed_at"):
            raise GovernanceExperienceError("recorded_before_observed")
        if not isinstance(source_receipt, TransitionReceipt):
            raise GovernanceExperienceError("source_receipt_required")
        if not isinstance(evidence_bundle, TransitionEvidenceBundle):
            raise GovernanceExperienceError("evidence_bundle_required")
        if source_receipt.decision is not TransitionDecision.HOLD:
            raise GovernanceExperienceError("hold_receipt_required")
        receipt = source_receipt.to_contract_dict()
        bundle = evidence_bundle.to_contract_dict()
        if source_transition_id != source_receipt.proposal.transition_id or source_transition_id != bundle["source_transition_id"]:
            raise GovernanceExperienceError("source_transition_id_mismatch")
        if canonical_contract_json(receipt["proposal"]) != canonical_contract_json(bundle["proposal"]):
            raise GovernanceExperienceError("source_proposal_mismatch")
        failed = [result for result in source_receipt.invariant_results if not result.passed]
        if hold_class == "invariant_failure":
            if not failed or source_receipt.first_failed_invariant != failed[0].invariant or source_receipt.release_block_reason is not None:
                raise GovernanceExperienceError("invariant_failure_receipt_required")
        elif hold_class == "release_admission_block":
            if failed or source_receipt.first_failed_invariant is not None or not source_receipt.release_block_reason:
                raise GovernanceExperienceError("release_block_receipt_required")
        else:
            raise GovernanceExperienceError("hold_class_invalid")
        if source_receipt.resulting_state_ref is not None:
            raise GovernanceExperienceError("hold_resulting_state_forbidden")
        if source_receipt_digest != contract_digest(receipt):
            raise GovernanceExperienceError("source_receipt_digest_mismatch")
        if evidence_bundle_digest != contract_digest(bundle):
            raise GovernanceExperienceError("evidence_bundle_digest_mismatch")
        payload = {
            "schema_version": "governance_experience_v1",
            "experience_id": experience_id,
            "observation_type": "transition_hold",
            "source_transition_id": source_transition_id,
            "source_receipt_digest": source_receipt_digest,
            "evidence_bundle_digest": evidence_bundle_digest,
            "source_receipt": receipt,
            "evidence_bundle": bundle,
            "hold_class": hold_class,
            "observed_at": observed_at,
            "recorded_at": recorded_at,
            "recorder_id": recorder_id,
            "recorder_provenance_reference": recorder_provenance_reference,
        }
        object.__setattr__(self, "_canonical_payload", canonical_contract_json(payload))

    def to_contract_dict(self) -> dict:
        return json.loads(self._canonical_payload)

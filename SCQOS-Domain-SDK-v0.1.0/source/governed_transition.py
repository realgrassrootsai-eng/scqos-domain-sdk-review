"""Phase 5.9 governed state-transition contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence


TRANSITION_CONTRACT_VERSION = "governed_transition_v1"

SCQOS_INVARIANTS = (
    "time",
    "continuity",
    "alignment",
    "genesis",
    "boundary",
    "reference",
    "causality",
    "consciousness",
)


class TransitionContractError(ValueError):
    """Raised when a proposed transition violates the contract."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TransitionDecision(str, Enum):
    """Authority attached only to one evaluated transition."""

    PERMIT = "PERMIT"
    HOLD = "HOLD"


def _normalize_required_text(
    value: Any,
    *,
    reason: str,
) -> str:
    if not isinstance(value, str):
        raise TransitionContractError(reason=reason)

    normalized = value.strip()

    if not normalized:
        raise TransitionContractError(reason=reason)

    return normalized


def _normalize_references(
    references: Sequence[str] | None,
) -> tuple[str, ...]:
    if references is None:
        return ()

    if isinstance(references, (str, bytes)) or not isinstance(
        references,
        Sequence,
    ):
        raise TransitionContractError(
            reason="reference_bindings_must_be_list"
        )

    normalized: list[str] = []

    for reference in references:
        normalized.append(
            _normalize_required_text(
                reference,
                reason="reference_binding_invalid",
            )
        )

    return tuple(normalized)


@dataclass(frozen=True)
class TransitionProposal:
    """
    One capability proposal to move reality from inherited state
    toward a proposed consequence.

    Creating a proposal does not authorize the consequence.
    """

    transition_id: str
    request_id: str
    actor_id: str
    session_id: str
    inherited_state_ref: str
    consequence_type: str
    proposed_consequence_digest: str
    boundary: str
    reference_bindings: tuple[str, ...]

    def __init__(
        self,
        *,
        transition_id: str,
        request_id: str,
        actor_id: str,
        session_id: str,
        inherited_state_ref: str,
        consequence_type: str,
        proposed_consequence_digest: str,
        boundary: str,
        reference_bindings: Sequence[str] | None = None,
    ) -> None:
        object.__setattr__(
            self,
            "transition_id",
            _normalize_required_text(
                transition_id,
                reason="transition_id_required",
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_required_text(
                request_id,
                reason="request_id_required",
            ),
        )
        object.__setattr__(
            self,
            "actor_id",
            _normalize_required_text(
                actor_id,
                reason="actor_id_required",
            ),
        )
        object.__setattr__(
            self,
            "session_id",
            _normalize_required_text(
                session_id,
                reason="session_id_required",
            ),
        )
        object.__setattr__(
            self,
            "inherited_state_ref",
            _normalize_required_text(
                inherited_state_ref,
                reason="inherited_state_ref_required",
            ),
        )
        object.__setattr__(
            self,
            "consequence_type",
            _normalize_required_text(
                consequence_type,
                reason="consequence_type_required",
            ),
        )
        object.__setattr__(
            self,
            "proposed_consequence_digest",
            _normalize_required_text(
                proposed_consequence_digest,
                reason="proposed_consequence_digest_required",
            ),
        )
        object.__setattr__(
            self,
            "boundary",
            _normalize_required_text(
                boundary,
                reason="boundary_required",
            ),
        )
        object.__setattr__(
            self,
            "reference_bindings",
            _normalize_references(reference_bindings),
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "contract_version": TRANSITION_CONTRACT_VERSION,
            **asdict(self),
        }


@dataclass(frozen=True)
class InvariantResult:
    """Result of proving one invariant for one transition."""

    invariant: str
    passed: bool
    reason: str
    evidence_references: tuple[str, ...]

    def __init__(
        self,
        *,
        invariant: str,
        passed: bool,
        reason: str,
        evidence_references: Sequence[str] | None = None,
    ) -> None:
        normalized_invariant = _normalize_required_text(
            invariant,
            reason="invariant_required",
        ).lower()

        if normalized_invariant not in SCQOS_INVARIANTS:
            raise TransitionContractError(
                reason="invariant_invalid"
            )

        if not isinstance(passed, bool):
            raise TransitionContractError(
                reason="invariant_passed_must_be_boolean"
            )

        object.__setattr__(
            self,
            "invariant",
            normalized_invariant,
        )
        object.__setattr__(
            self,
            "passed",
            passed,
        )
        object.__setattr__(
            self,
            "reason",
            _normalize_required_text(
                reason,
                reason="invariant_reason_required",
            ),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _normalize_references(evidence_references),
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransitionReceipt:
    """
    Proof record establishing whether one proposed transition
    acquired authority to become consequential state.

    A transition may be placed on HOLD for either of two reasons:

    1. One of the eight canonical invariants failed.
    2. All eight invariants passed, but an independent release-admission
       check blocked the proposed consequence before release.

    release_block_reason records the second case without inventing
    an additional SCQOS invariant.
    """

    proposal: TransitionProposal
    invariant_results: tuple[InvariantResult, ...]
    decision: TransitionDecision
    first_failed_invariant: str | None
    release_block_reason: str | None
    resulting_state_ref: str | None

    def __init__(
        self,
        *,
        proposal: TransitionProposal,
        invariant_results: Sequence[InvariantResult],
        decision: TransitionDecision,
        first_failed_invariant: str | None = None,
        release_block_reason: str | None = None,
        resulting_state_ref: str | None = None,
    ) -> None:
        if not isinstance(proposal, TransitionProposal):
            raise TransitionContractError(
                reason="transition_proposal_required"
            )

        if isinstance(invariant_results, (str, bytes)) or not isinstance(
            invariant_results,
            Sequence,
        ):
            raise TransitionContractError(
                reason="invariant_results_must_be_list"
            )

        normalized_results = tuple(invariant_results)

        if not normalized_results:
            raise TransitionContractError(
                reason="invariant_results_required"
            )

        if not all(
            isinstance(result, InvariantResult)
            for result in normalized_results
        ):
            raise TransitionContractError(
                reason="invariant_result_invalid"
            )

        if len(normalized_results) != len(
            SCQOS_INVARIANTS
        ):
            raise TransitionContractError(
                reason="complete_invariant_results_required"
            )

        normalized_invariant_names = tuple(
            result.invariant
            for result in normalized_results
        )

        if set(normalized_invariant_names) != set(
            SCQOS_INVARIANTS
        ):
            raise TransitionContractError(
                reason="invariant_results_must_match_canonical_set"
            )

        if normalized_invariant_names != SCQOS_INVARIANTS:
            raise TransitionContractError(
                reason="invariant_results_not_in_canonical_order"
            )

        if not isinstance(decision, TransitionDecision):
            raise TransitionContractError(
                reason="transition_decision_invalid"
            )

        failed_results = [
            result
            for result in normalized_results
            if not result.passed
        ]

        normalized_failed_invariant = (
            _normalize_required_text(
                first_failed_invariant,
                reason="first_failed_invariant_invalid",
            ).lower()
            if first_failed_invariant is not None
            else None
        )

        normalized_release_block_reason = (
            _normalize_required_text(
                release_block_reason,
                reason="release_block_reason_invalid",
            )
            if release_block_reason is not None
            else None
        )

        normalized_resulting_state_ref = (
            _normalize_required_text(
                resulting_state_ref,
                reason="resulting_state_ref_invalid",
            )
            if resulting_state_ref is not None
            else None
        )

        if decision is TransitionDecision.PERMIT:
            if failed_results:
                raise TransitionContractError(
                    reason="permit_with_failed_invariant_forbidden"
                )

            if normalized_failed_invariant is not None:
                raise TransitionContractError(
                    reason="permit_cannot_name_failed_invariant"
                )

            if normalized_release_block_reason is not None:
                raise TransitionContractError(
                    reason="permit_cannot_have_release_block_reason"
                )

            if normalized_resulting_state_ref is None:
                raise TransitionContractError(
                    reason="permit_requires_resulting_state_ref"
                )

        if decision is TransitionDecision.HOLD:
            if normalized_resulting_state_ref is not None:
                raise TransitionContractError(
                    reason="hold_cannot_create_resulting_state"
                )

            if failed_results:
                actual_first_failure = failed_results[0].invariant

                if normalized_failed_invariant != actual_first_failure:
                    raise TransitionContractError(
                        reason="first_failed_invariant_mismatch"
                    )

                if normalized_release_block_reason is not None:
                    raise TransitionContractError(
                        reason=(
                            "invariant_failure_cannot_have_"
                            "release_block_reason"
                        )
                    )

            else:
                if normalized_failed_invariant is not None:
                    raise TransitionContractError(
                        reason=(
                            "release_block_cannot_name_failed_invariant"
                        )
                    )

                if normalized_release_block_reason is None:
                    raise TransitionContractError(
                        reason=(
                            "hold_requires_failed_invariant_"
                            "or_release_block_reason"
                        )
                    )

        object.__setattr__(self, "proposal", proposal)

        object.__setattr__(
            self,
            "invariant_results",
            normalized_results,
        )

        object.__setattr__(self, "decision", decision)

        object.__setattr__(
            self,
            "first_failed_invariant",
            normalized_failed_invariant,
        )

        object.__setattr__(
            self,
            "release_block_reason",
            normalized_release_block_reason,
        )

        object.__setattr__(
            self,
            "resulting_state_ref",
            normalized_resulting_state_ref,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "contract_version": TRANSITION_CONTRACT_VERSION,
            "proposal": self.proposal.to_contract_dict(),
            "invariant_results": [
                result.to_contract_dict()
                for result in self.invariant_results
            ],
            "decision": self.decision.value,
            "first_failed_invariant": self.first_failed_invariant,
            "release_block_reason": self.release_block_reason,
            "resulting_state_ref": self.resulting_state_ref,
        }
@dataclass(frozen=True)
class AlignmentVerification:
    """
    Independent verification that one proposed consequence agrees
    with the referenced inherited state.

    This object records verification. It does not infer alignment
    through keywords and it does not rewrite the consequence.
    """

    verifier_id: str
    verifier_version: str
    passed: bool
    reason: str
    evidence_references: tuple[str, ...]

    def __init__(
        self,
        *,
        verifier_id: str,
        verifier_version: str,
        passed: bool,
        reason: str,
        evidence_references: Sequence[str] | None = None,
    ) -> None:
        if not isinstance(passed, bool):
            raise TransitionContractError(
                reason="alignment_passed_must_be_boolean"
            )

        normalized_references = _normalize_references(
            evidence_references
        )

        if passed and not normalized_references:
            raise TransitionContractError(
                reason="alignment_pass_requires_evidence"
            )

        object.__setattr__(
            self,
            "verifier_id",
            _normalize_required_text(
                verifier_id,
                reason="alignment_verifier_id_required",
            ),
        )
        object.__setattr__(
            self,
            "verifier_version",
            _normalize_required_text(
                verifier_version,
                reason="alignment_verifier_version_required",
            ),
        )
        object.__setattr__(
            self,
            "passed",
            passed,
        )
        object.__setattr__(
            self,
            "reason",
            _normalize_required_text(
                reason,
                reason="alignment_reason_required",
            ),
        )
        object.__setattr__(
            self,
            "evidence_references",
            normalized_references,
        )

    def to_invariant_result(self) -> InvariantResult:
        return InvariantResult(
            invariant="alignment",
            passed=self.passed,
            reason=self.reason,
            evidence_references=self.evidence_references,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class AlignmentVerification:
    """
    Independent verification that one proposed consequence agrees
    with the referenced inherited state.

    This object records verification. It does not infer alignment
    through keywords and it does not rewrite the consequence.
    """

    proposed_consequence_digest: str
    verifier_id: str
    verifier_version: str
    passed: bool
    reason: str
    evidence_references: tuple[str, ...]

    def __init__(
        self,
        *,
        proposed_consequence_digest: str,
        verifier_id: str,
        verifier_version: str,
        passed: bool,
        reason: str,
        evidence_references: Sequence[str] | None = None,
    ) -> None:
        if not isinstance(passed, bool):
            raise TransitionContractError(
                reason="alignment_passed_must_be_boolean"
            )

        object.__setattr__(
            self,
            "proposed_consequence_digest",
            _normalize_required_text(
                proposed_consequence_digest,
                reason="alignment_proposed_consequence_digest_required",
            ),
        )

        normalized_references = _normalize_references(
            evidence_references
        )

        if passed and not normalized_references:
            raise TransitionContractError(
                reason="alignment_pass_requires_evidence"
            )

        object.__setattr__(
            self,
            "verifier_id",
            _normalize_required_text(
                verifier_id,
                reason="alignment_verifier_id_required",
            ),
        )

        object.__setattr__(
            self,
            "verifier_version",
            _normalize_required_text(
                verifier_version,
                reason="alignment_verifier_version_required",
            ),
        )

        object.__setattr__(
            self,
            "passed",
            passed,
        )

        object.__setattr__(
            self,
            "reason",
            _normalize_required_text(
                reason,
                reason="alignment_reason_required",
            ),
        )

        object.__setattr__(
            self,
            "evidence_references",
            normalized_references,
        )

    def to_invariant_result(self) -> InvariantResult:
        return InvariantResult(
            invariant="alignment",
            passed=self.passed,
            reason=self.reason,
            evidence_references=self.evidence_references,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return asdict(self)

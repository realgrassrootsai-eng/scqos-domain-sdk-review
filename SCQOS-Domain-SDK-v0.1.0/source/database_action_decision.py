"""Final SCQOS decision assembly for the isolated database action lab."""

from __future__ import annotations

from dataclasses import dataclass

from database_action_approval import (
    DatabaseActionApprovalError,
    DatabaseActionApprovalV1,
    validate_database_action_approval,
)
from database_action_contracts import DatabaseWriteActionV1
from database_action_governance import (
    DatabaseActionTransitionBindingV1,
    build_database_action_transition_binding,
)
from governed_transition import (
    AlignmentVerification,
    TransitionDecision,
    TransitionReceipt,
)
from scqos_runtime_evidence import SCQOSRuntimeEvidence
from scqos_transition_evaluator import evaluate_transition_invariants


@dataclass(frozen=True)
class DatabaseActionDecisionV1:
    action: DatabaseWriteActionV1
    binding: DatabaseActionTransitionBindingV1
    runtime_evidence: SCQOSRuntimeEvidence
    invariant_results: tuple
    receipt: TransitionReceipt


def build_database_action_decision(
    *,
    action: DatabaseWriteActionV1,
    runtime_evidence: SCQOSRuntimeEvidence,
    request_id: str,
    session_id: str,
    inherited_state_ref: str,
    alignment_verification_required: bool = False,
    alignment_verification: AlignmentVerification | None = None,
    approval: DatabaseActionApprovalV1 | None = None,
) -> DatabaseActionDecisionV1:
    binding = build_database_action_transition_binding(
        action,
        request_id=request_id,
        session_id=session_id,
        inherited_state_ref=inherited_state_ref,
    )

    invariant_results = tuple(
        evaluate_transition_invariants(
            proposal=binding.proposal,
            runtime_evidence=runtime_evidence,
            alignment_verification_required=(
                alignment_verification_required
            ),
            alignment_verification=alignment_verification,
        )
    )
    failed = [
        result
        for result in invariant_results
        if not result.passed
    ]

    if failed:
        receipt = TransitionReceipt(
            proposal=binding.proposal,
            invariant_results=invariant_results,
            decision=TransitionDecision.HOLD,
            first_failed_invariant=failed[0].invariant,
        )
    elif approval is None:
        receipt = TransitionReceipt(
            proposal=binding.proposal,
            invariant_results=invariant_results,
            decision=TransitionDecision.HOLD,
            release_block_reason="required_approval_missing",
        )
    else:
        try:
            validate_database_action_approval(action, approval)
        except DatabaseActionApprovalError as error:
            receipt = TransitionReceipt(
                proposal=binding.proposal,
                invariant_results=invariant_results,
                decision=TransitionDecision.HOLD,
                release_block_reason=(
                    f"database_action_approval_invalid:{error}"
                ),
            )
        else:
            receipt = TransitionReceipt(
                proposal=binding.proposal,
                invariant_results=invariant_results,
                decision=TransitionDecision.PERMIT,
                resulting_state_ref=(
                    "authorized-database-action:"
                    f"{action.action_digest}"
                ),
            )

    return DatabaseActionDecisionV1(
        action=action,
        binding=binding,
        runtime_evidence=runtime_evidence,
        invariant_results=invariant_results,
        receipt=receipt,
    )

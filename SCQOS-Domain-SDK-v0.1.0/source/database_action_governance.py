"""SCQOS binding adapter for the isolated database-action lab.

This module binds one exact typed database action to one exact SCQOS
TransitionProposal and BoundaryReleaseEvidence object. It does not execute
the action and does not grant authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from database_action_contracts import DatabaseWriteActionV1
from governed_action_registry import (
    GovernedActionAdmissionV1,
    GovernedActionRegistryError,
    build_governed_action_admission,
    request_governed_consequence,
    resolve_governed_action,
)
from governed_transition import InvariantResult, TransitionProposal
from scqos_runtime_evidence import BoundaryReleaseEvidence
from scqos_transition_evaluator import evaluate_boundary_invariant


_DATABASE_ACTION_ADAPTER = request_governed_consequence(
    "database_write"
)
DATABASE_ACTION_CONSEQUENCE_TYPE = (
    _DATABASE_ACTION_ADAPTER.consequence_type
)
DATABASE_ACTION_BOUNDARY = _DATABASE_ACTION_ADAPTER.boundary
DATABASE_ACTION_RELEASE_OPERATION = (
    _DATABASE_ACTION_ADAPTER.release_operation
)
DATABASE_ACTION_LAB_TABLE = "grassrootsai-scqos-action-lab"
DATABASE_ACTION_RELEASE_DESTINATION = (
    _DATABASE_ACTION_ADAPTER.release_destination
)


class DatabaseActionGovernanceError(ValueError):
    """Raised when an action cannot be safely bound into SCQOS."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DatabaseActionGovernanceError(reason)


@dataclass(frozen=True)
class DatabaseActionTransitionBindingV1:
    """Exact proposal, registry admission, and boundary evidence."""

    action_digest: str
    admission: GovernedActionAdmissionV1
    proposal: TransitionProposal
    boundary_evidence: BoundaryReleaseEvidence


def _validate_action_for_lab(action: DatabaseWriteActionV1) -> None:
    try:
        descriptor = resolve_governed_action(action)
    except GovernedActionRegistryError as error:
        raise DatabaseActionGovernanceError(
            "database_write_action_v1_required"
        ) from error
    _require(
        descriptor is _DATABASE_ACTION_ADAPTER,
        "database_action_adapter_not_installed",
    )
    _require(
        action.table_name == DATABASE_ACTION_LAB_TABLE,
        "database_action_table_not_authorized",
    )


def build_database_action_transition_binding(
    action: DatabaseWriteActionV1,
    *,
    request_id: str,
    session_id: str,
    inherited_state_ref: str,
) -> DatabaseActionTransitionBindingV1:
    """Derive the SCQOS proposal and boundary evidence from one exact action."""

    _validate_action_for_lab(action)
    digest = action.action_digest
    admission = build_governed_action_admission(
        action,
        consequence_type=DATABASE_ACTION_CONSEQUENCE_TYPE,
        boundary=DATABASE_ACTION_BOUNDARY,
    )

    proposal = TransitionProposal(
        transition_id=action.transition_id,
        request_id=request_id,
        actor_id=action.actor_id,
        session_id=session_id,
        inherited_state_ref=inherited_state_ref,
        consequence_type=DATABASE_ACTION_CONSEQUENCE_TYPE,
        proposed_consequence_digest=digest,
        boundary=DATABASE_ACTION_BOUNDARY,
        reference_bindings=(
            *action.evidence_refs,
            *action.authorization_refs,
        ),
    )

    boundary_evidence = BoundaryReleaseEvidence(
        transition_id=action.transition_id,
        consequence_type=DATABASE_ACTION_CONSEQUENCE_TYPE,
        boundary=DATABASE_ACTION_BOUNDARY,
        release_operation=DATABASE_ACTION_RELEASE_OPERATION,
        release_destination=DATABASE_ACTION_RELEASE_DESTINATION,
        release_consequence_digest=digest,
    )

    return DatabaseActionTransitionBindingV1(
        action_digest=digest,
        admission=admission,
        proposal=proposal,
        boundary_evidence=boundary_evidence,
    )


def evaluate_database_action_boundary_binding(
    action: DatabaseWriteActionV1,
    proposal: TransitionProposal,
    boundary_evidence: BoundaryReleaseEvidence,
) -> InvariantResult:
    """Fail closed unless SCQOS is evaluating the exact supplied action."""

    evidence_references: tuple[str, ...] = ()

    def fail(reason: str) -> InvariantResult:
        return InvariantResult(
            invariant="boundary",
            passed=False,
            reason=reason,
            evidence_references=evidence_references,
        )

    if type(action) is not DatabaseWriteActionV1:
        return fail("database_write_action_v1_required")
    if not isinstance(proposal, TransitionProposal):
        return fail("transition_proposal_required")
    if not isinstance(boundary_evidence, BoundaryReleaseEvidence):
        return fail("boundary_release_evidence_required")

    evidence_references = (
        f"database-action:{action.transition_id}:{action.action_digest}",
    )

    if action.table_name != DATABASE_ACTION_LAB_TABLE:
        return fail("database_action_table_not_authorized")
    if action.transition_id != proposal.transition_id:
        return fail("database_action_transition_id_mismatch")
    if action.actor_id != proposal.actor_id:
        return fail("database_action_actor_id_mismatch")
    if proposal.consequence_type != DATABASE_ACTION_CONSEQUENCE_TYPE:
        return fail("database_action_consequence_type_mismatch")
    if proposal.boundary != DATABASE_ACTION_BOUNDARY:
        return fail("database_action_boundary_mismatch")
    if action.action_digest != proposal.proposed_consequence_digest:
        return fail("database_action_digest_mismatch")
    if (
        boundary_evidence.release_consequence_digest
        != action.action_digest
    ):
        return fail("database_action_boundary_digest_mismatch")

    return evaluate_boundary_invariant(
        proposal,
        boundary_evidence,
    )

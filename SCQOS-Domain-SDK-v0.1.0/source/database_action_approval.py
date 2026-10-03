"""Typed synthetic approval for the isolated database action lab.

This is a structural lab approval contract, not a signature or production
identity credential. It proves separation between proposal and approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from database_action_contracts import (
    DatabaseWriteActionV1,
    DatabaseWriteOperation,
)
from scqos_contract_digest import contract_digest


class DatabaseActionApprovalError(ValueError):
    """Raised when a lab approval is missing or mismatched."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DatabaseActionApprovalError(reason)


def _text(value: Any, reason: str) -> str:
    _require(
        type(value) is str
        and bool(value)
        and value == value.strip(),
        reason,
    )
    return value


@dataclass(frozen=True)
class DatabaseActionApprovalV1:
    """Approval of one exact unapproved action intent."""

    VERSION = "database_action_approval_v1"

    approval_id: str
    approver_id: str
    transition_id: str
    actor_id: str
    operation: DatabaseWriteOperation
    table_name: str
    record_key: str
    field_name: str
    old_value: str
    proposed_value: str
    evidence_refs: tuple[str, ...]

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.VERSION,
            "approval_id": self.approval_id,
            "approver_id": self.approver_id,
            "transition_id": self.transition_id,
            "actor_id": self.actor_id,
            "operation": self.operation.value,
            "table_name": self.table_name,
            "record_key": self.record_key,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "proposed_value": self.proposed_value,
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def approval_digest(self) -> str:
        return contract_digest(self.to_contract_dict())

    @property
    def authorization_reference(self) -> str:
        return f"database-action-approval:{self.approval_digest}"


def build_database_action_approval(
    action: DatabaseWriteActionV1,
    *,
    approval_id: str,
    approver_id: str,
) -> DatabaseActionApprovalV1:
    """Approve an exact action intent before authority is attached."""

    _require(
        type(action) is DatabaseWriteActionV1,
        "database_write_action_v1_required",
    )
    _require(
        not action.authorization_refs,
        "approval_requires_unapproved_action",
    )

    return DatabaseActionApprovalV1(
        approval_id=_text(approval_id, "approval_id_invalid"),
        approver_id=_text(approver_id, "approver_id_invalid"),
        transition_id=action.transition_id,
        actor_id=action.actor_id,
        operation=action.operation,
        table_name=action.table_name,
        record_key=action.record_key,
        field_name=action.field_name,
        old_value=action.old_value,
        proposed_value=action.proposed_value,
        evidence_refs=action.evidence_refs,
    )


def attach_database_action_approval(
    action: DatabaseWriteActionV1,
    approval: DatabaseActionApprovalV1,
) -> DatabaseWriteActionV1:
    """Return a new action carrying only the exact approval digest reference."""

    _require(
        type(action) is DatabaseWriteActionV1,
        "database_write_action_v1_required",
    )
    _require(
        not action.authorization_refs,
        "approval_attachment_requires_unapproved_action",
    )
    validate_database_action_approval_intent(action, approval)

    return DatabaseWriteActionV1(
        transition_id=action.transition_id,
        actor_id=action.actor_id,
        operation=action.operation,
        table_name=action.table_name,
        record_key=action.record_key,
        field_name=action.field_name,
        old_value=action.old_value,
        proposed_value=action.proposed_value,
        evidence_refs=action.evidence_refs,
        authorization_refs=(approval.authorization_reference,),
    )


def validate_database_action_approval_intent(
    action: DatabaseWriteActionV1,
    approval: DatabaseActionApprovalV1,
) -> None:
    """Require approval fields to bind the exact mutation and evidence."""

    _require(
        type(action) is DatabaseWriteActionV1,
        "database_write_action_v1_required",
    )
    _require(
        type(approval) is DatabaseActionApprovalV1,
        "database_action_approval_v1_required",
    )

    for field in (
        "transition_id",
        "actor_id",
        "operation",
        "table_name",
        "record_key",
        "field_name",
        "old_value",
        "proposed_value",
        "evidence_refs",
    ):
        _require(
            getattr(action, field) == getattr(approval, field),
            f"database_action_approval_{field}_mismatch",
        )


def validate_database_action_approval(
    action: DatabaseWriteActionV1,
    approval: DatabaseActionApprovalV1,
) -> None:
    """Validate the attached approval reference and its exact intent binding."""

    validate_database_action_approval_intent(action, approval)
    _require(
        action.authorization_refs
        == (approval.authorization_reference,),
        "database_action_approval_reference_mismatch",
    )

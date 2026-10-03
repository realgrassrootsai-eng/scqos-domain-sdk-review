"""Narrow typed contracts for the isolated governed database-action lab.

These contracts describe a proposed database mutation. They do not authorize,
execute, or persist the mutation. Authority remains external to the proposal.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, Sequence

from scqos_contract_digest import contract_digest


class DatabaseActionContractError(ValueError):
    """Raised when a database action contract is structurally invalid."""


class DatabaseWriteOperation(str, Enum):
    SET_FIELD = "SET_FIELD"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise DatabaseActionContractError(code)


def _required_text(value: Any, code: str) -> str:
    _require(
        type(value) is str
        and bool(value)
        and value == value.strip(),
        code,
    )
    return value


def _references(
    value: Sequence[str] | None,
    code: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    _require(
        not isinstance(value, (str, bytes))
        and isinstance(value, Sequence),
        code,
    )
    result: list[str] = []
    for item in value:
        normalized = _required_text(item, code)
        _require(normalized not in result, code)
        result.append(normalized)
    return tuple(result)


@dataclass(frozen=True)
class DatabaseWriteActionV1:
    """One proposed single-field mutation against one exact record."""

    VERSION = "database_write_action_v1"

    transition_id: str
    actor_id: str
    operation: DatabaseWriteOperation
    table_name: str
    record_key: str
    field_name: str
    old_value: str
    proposed_value: str
    evidence_refs: tuple[str, ...]
    authorization_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        transition_id: str,
        actor_id: str,
        operation: DatabaseWriteOperation,
        table_name: str,
        record_key: str,
        field_name: str,
        old_value: str,
        proposed_value: str,
        evidence_refs: Sequence[str] | None = None,
        authorization_refs: Sequence[str] | None = None,
    ) -> None:
        _require(
            type(self) is DatabaseWriteActionV1,
            "exact_contract_type_required",
        )
        _require(
            type(operation) is DatabaseWriteOperation,
            "database_write_operation_invalid",
        )

        object.__setattr__(
            self, "transition_id",
            _required_text(transition_id, "transition_id_invalid"),
        )
        object.__setattr__(
            self, "actor_id",
            _required_text(actor_id, "actor_id_invalid"),
        )
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self, "table_name",
            _required_text(table_name, "table_name_invalid"),
        )
        object.__setattr__(
            self, "record_key",
            _required_text(record_key, "record_key_invalid"),
        )
        object.__setattr__(
            self, "field_name",
            _required_text(field_name, "field_name_invalid"),
        )
        object.__setattr__(
            self, "old_value",
            _required_text(old_value, "old_value_invalid"),
        )
        object.__setattr__(
            self, "proposed_value",
            _required_text(proposed_value, "proposed_value_invalid"),
        )
        _require(
            old_value != proposed_value,
            "database_write_must_change_value",
        )
        object.__setattr__(
            self, "evidence_refs",
            _references(evidence_refs, "evidence_ref_invalid"),
        )
        object.__setattr__(
            self, "authorization_refs",
            _references(
                authorization_refs,
                "authorization_ref_invalid",
            ),
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.VERSION,
            **{
                field.name: (
                    getattr(self, field.name).value
                    if isinstance(getattr(self, field.name), Enum)
                    else list(getattr(self, field.name))
                    if type(getattr(self, field.name)) is tuple
                    else getattr(self, field.name)
                )
                for field in fields(self)
            },
        }

    @property
    def action_digest(self) -> str:
        return contract_digest(self.to_contract_dict())

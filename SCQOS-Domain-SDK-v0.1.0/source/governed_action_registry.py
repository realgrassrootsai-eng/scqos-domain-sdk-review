"""Closed registry for consequence types installed in the governed-action runtime.

The registry is admission metadata only. It contains no AWS clients, writers,
verifiers, import paths, dynamic registration hooks, or caller-supplied code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from database_action_contracts import DatabaseWriteActionV1
from s3_action_contracts import S3PutObjectActionV1
from scqos_contract_digest import contract_digest


GOVERNED_ACTION_REGISTRY_VERSION = "governed_action_registry_v1"


class GovernedActionRegistryError(ValueError):
    pass


def _digest(value: Any, reason: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise GovernedActionRegistryError(reason)
    return value


class GovernedConsequenceKind(str, Enum):
    DATABASE_WRITE = "database_write"
    OBJECT_WRITE = "object_write"


@dataclass(frozen=True)
class GovernedActionAdapterDescriptorV1:
    VERSION = "governed_action_adapter_descriptor_v1"

    adapter_id: str
    consequence_kind: GovernedConsequenceKind
    action_type: type
    boundary: str
    release_operation: str
    release_destination: str

    def __post_init__(self) -> None:
        if type(self) is not GovernedActionAdapterDescriptorV1:
            raise GovernedActionRegistryError(
                "exact_governed_action_adapter_descriptor_v1_required"
            )
        if (
            type(self.adapter_id) is not str
            or not self.adapter_id
            or self.adapter_id != self.adapter_id.strip()
        ):
            raise GovernedActionRegistryError(
                "governed_action_adapter_id_invalid"
            )
        if type(self.consequence_kind) is not GovernedConsequenceKind:
            raise GovernedActionRegistryError(
                "governed_consequence_kind_invalid"
            )
        if type(self.action_type) is not type:
            raise GovernedActionRegistryError(
                "governed_action_type_invalid"
            )
        for value, reason in (
            (self.boundary, "governed_action_boundary_invalid"),
            (
                self.release_operation,
                "governed_action_release_operation_invalid",
            ),
            (
                self.release_destination,
                "governed_action_release_destination_invalid",
            ),
        ):
            if (
                type(value) is not str
                or not value
                or value != value.strip()
            ):
                raise GovernedActionRegistryError(reason)

    @property
    def consequence_type(self) -> str:
        return self.consequence_kind.value

    def to_contract_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.VERSION,
            "adapter_id": self.adapter_id,
            "consequence_type": self.consequence_type,
            "action_contract_type": self.action_type.__name__,
            "boundary": self.boundary,
            "release_operation": self.release_operation,
            "release_destination": self.release_destination,
        }


@dataclass(frozen=True)
class GovernedActionAdmissionV1:
    VERSION = "governed_action_admission_v1"

    registry_digest: str
    adapter_id: str
    consequence_type: str
    boundary: str
    action_contract_type: str
    action_digest: str

    def __post_init__(self) -> None:
        if type(self) is not GovernedActionAdmissionV1:
            raise GovernedActionRegistryError(
                "exact_governed_action_admission_v1_required"
            )
        _digest(
            self.registry_digest,
            "governed_action_registry_digest_invalid",
        )
        _digest(
            self.action_digest,
            "governed_action_admission_action_digest_invalid",
        )
        for value, reason in (
            (self.adapter_id, "governed_action_admission_adapter_id_invalid"),
            (
                self.consequence_type,
                "governed_action_admission_consequence_type_invalid",
            ),
            (
                self.boundary,
                "governed_action_admission_boundary_invalid",
            ),
            (
                self.action_contract_type,
                "governed_action_admission_contract_type_invalid",
            ),
        ):
            if (
                type(value) is not str
                or not value
                or value != value.strip()
            ):
                raise GovernedActionRegistryError(reason)

    def to_contract_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.VERSION,
            "registry_digest": self.registry_digest,
            "adapter_id": self.adapter_id,
            "consequence_type": self.consequence_type,
            "boundary": self.boundary,
            "action_contract_type": self.action_contract_type,
            "action_digest": self.action_digest,
        }

    @property
    def admission_digest(self) -> str:
        return contract_digest(self.to_contract_dict())


_DATABASE_WRITE = GovernedActionAdapterDescriptorV1(
    adapter_id="scqos.database_write.v2",
    consequence_kind=GovernedConsequenceKind.DATABASE_WRITE,
    action_type=DatabaseWriteActionV1,
    boundary="database_action_execute",
    release_operation="dynamodb_update_item",
    release_destination=(
        "dynamodb:table:grassrootsai-scqos-action-lab"
    ),
)

_S3_OBJECT_WRITE = GovernedActionAdapterDescriptorV1(
    adapter_id="scqos.s3_put_object.v1",
    consequence_kind=GovernedConsequenceKind.OBJECT_WRITE,
    action_type=S3PutObjectActionV1,
    boundary="s3_action_execute",
    release_operation="s3_put_object",
    release_destination=(
        "s3:bucket:"
        "grassrootsai-scqos-s3-action-lab-327453383912-us-east-1"
    ),
)

_INSTALLED_GOVERNED_ACTION_ADAPTERS = (
    _DATABASE_WRITE,
    _S3_OBJECT_WRITE,
)


def _validate_registry() -> None:
    adapter_ids = [
        item.adapter_id
        for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
    ]
    consequence_types = [
        item.consequence_type
        for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
    ]
    action_types = [
        item.action_type
        for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
    ]
    boundary_pairs = [
        (item.consequence_type, item.boundary)
        for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
    ]
    for values, reason in (
        (adapter_ids, "duplicate_governed_action_adapter_id"),
        (
            consequence_types,
            "duplicate_governed_action_consequence_type",
        ),
        (action_types, "duplicate_governed_action_contract_type"),
        (
            boundary_pairs,
            "duplicate_governed_action_boundary_pair",
        ),
    ):
        if len(values) != len(set(values)):
            raise GovernedActionRegistryError(reason)


_validate_registry()


def governed_action_registry_contract() -> dict[str, Any]:
    return {
        "schema_version": GOVERNED_ACTION_REGISTRY_VERSION,
        "installed_adapters": [
            item.to_contract_dict()
            for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
        ],
    }


def governed_action_registry_digest() -> str:
    return contract_digest(governed_action_registry_contract())


def installed_governed_action_adapters(
) -> tuple[GovernedActionAdapterDescriptorV1, ...]:
    return _INSTALLED_GOVERNED_ACTION_ADAPTERS


def request_governed_consequence(
    consequence_type: str,
) -> GovernedActionAdapterDescriptorV1:
    """Resolve only an exact installed consequence type.

    This accepts no tool name, operation name, import path, destination,
    executor, factory, or callable.
    """

    if (
        type(consequence_type) is not str
        or not consequence_type
        or consequence_type != consequence_type.strip()
    ):
        raise GovernedActionRegistryError(
            "governed_consequence_type_invalid"
        )
    matches = tuple(
        item
        for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
        if item.consequence_type == consequence_type
    )
    if len(matches) != 1:
        raise GovernedActionRegistryError(
            "governed_consequence_not_installed"
        )
    return matches[0]


def resolve_governed_action(
    action: Any,
) -> GovernedActionAdapterDescriptorV1:
    """Admit by exact typed action contract, never subclass or duck type."""

    matches = tuple(
        item
        for item in _INSTALLED_GOVERNED_ACTION_ADAPTERS
        if type(action) is item.action_type
    )
    if len(matches) != 1:
        raise GovernedActionRegistryError(
            "governed_action_contract_not_installed"
        )
    return matches[0]


def resolve_governed_boundary(
    *,
    consequence_type: str,
    boundary: str,
) -> GovernedActionAdapterDescriptorV1:
    if type(boundary) is not str or not boundary:
        raise GovernedActionRegistryError(
            "governed_action_boundary_invalid"
        )
    descriptor = request_governed_consequence(
        consequence_type
    )
    if descriptor.boundary != boundary:
        raise GovernedActionRegistryError(
            "governed_action_boundary_not_installed"
        )
    return descriptor


def is_installed_governed_boundary(
    *,
    consequence_type: str,
    boundary: str,
) -> bool:
    try:
        resolve_governed_boundary(
            consequence_type=consequence_type,
            boundary=boundary,
        )
    except GovernedActionRegistryError:
        return False
    return True


def admit_governed_action(
    action: Any,
    *,
    consequence_type: str,
    boundary: str,
) -> GovernedActionAdapterDescriptorV1:
    descriptor = resolve_governed_action(action)
    if descriptor.consequence_type != consequence_type:
        raise GovernedActionRegistryError(
            "governed_action_consequence_type_mismatch"
        )
    if descriptor.boundary != boundary:
        raise GovernedActionRegistryError(
            "governed_action_boundary_mismatch"
        )
    return descriptor


def build_governed_action_admission(
    action: Any,
    *,
    consequence_type: str,
    boundary: str,
) -> GovernedActionAdmissionV1:
    descriptor = admit_governed_action(
        action,
        consequence_type=consequence_type,
        boundary=boundary,
    )
    action_digest = getattr(action, "action_digest", None)
    _digest(
        action_digest,
        "governed_action_admission_action_digest_invalid",
    )
    return GovernedActionAdmissionV1(
        registry_digest=governed_action_registry_digest(),
        adapter_id=descriptor.adapter_id,
        consequence_type=descriptor.consequence_type,
        boundary=descriptor.boundary,
        action_contract_type=descriptor.action_type.__name__,
        action_digest=action_digest,
    )

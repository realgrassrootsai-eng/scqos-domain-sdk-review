"""Pure Constitution v1 binding and authority-witness contracts.

These contracts make constitutional identity, runtime activation, and witness
currentness explicit. Structural validity never creates authority or permission.
Only SCQOS may turn admitted proof into PERMIT, HOLD, or REJECT.
"""

from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from scqos_contract_digest import contract_digest


CONSTITUTION_VERSION_V1 = "v1"
CONSTITUTIONAL_INVARIANTS_V1 = (
    "Time",
    "Continuity",
    "Alignment",
    "Genesis",
    "Boundary",
    "Reference",
    "Causality",
    "Consciousness",
)
COHERENCE_ROLE_V1 = "mechanism"


class ConstitutionalContractError(ValueError):
    """Raised when a Constitution v1 contract is structurally invalid."""


class ConstitutionalBindingStatus(str, Enum):
    ACTIVE = "ACTIVE"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ConstitutionalContractError(code)


def _ref(value: Any, code: str) -> None:
    _require(
        type(value) is str and bool(value) and value == value.strip(),
        code,
    )


def _digest(value: Any, code: str) -> None:
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        code,
    )


def _prefixed_digest(value: Any, code: str) -> None:
    _require(
        type(value) is str and value.startswith("sha256:"),
        code,
    )
    _digest(value.removeprefix("sha256:"), code)


def _canonical_time(value: Any, code: str) -> datetime:
    _ref(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConstitutionalContractError(code) from None
    _require(parsed.utcoffset() is not None, code)
    return parsed.astimezone(timezone.utc)


class _Contract:
    VERSION = ""

    def to_contract_dict(self) -> dict[str, Any]:
        def encode(value: Any) -> Any:
            if hasattr(value, "to_contract_dict"):
                return value.to_contract_dict()
            if isinstance(value, Enum):
                return value.value
            if type(value) is tuple:
                return [encode(item) for item in value]
            return value

        return {
            "schema_version": self.VERSION,
            **{
                field.name: encode(getattr(self, field.name))
                for field in fields(self)
            },
        }

    @property
    def digest(self) -> str:
        return contract_digest(self.to_contract_dict())


@dataclass(frozen=True)
class CanonicalConstitutionArtifactV1(_Contract):
    """Identity of the immutable Constitution artifact and its source runtime."""

    VERSION = "canonical_constitution_artifact_v1"

    constitution_version: str
    constitution_digest: str
    storage_reference: str
    storage_version: str
    artifact_image_digest: str
    artifact_task_definition: str
    purpose_digest: str
    authority_root_digest: str
    authority_policy_digest: str
    contract_universe_digest: str
    binding_id: str
    lineage_id: str
    invariants: tuple[str, ...] = CONSTITUTIONAL_INVARIANTS_V1
    coherence_role: str = COHERENCE_ROLE_V1

    def __post_init__(self) -> None:
        _require(
            type(self) is CanonicalConstitutionArtifactV1,
            "exact_contract_type_required",
        )
        _require(
            self.constitution_version == CONSTITUTION_VERSION_V1,
            "constitution_version_invalid",
        )
        _digest(self.constitution_digest, "constitution_digest_invalid")
        _ref(self.storage_reference, "storage_reference_invalid")
        _ref(self.storage_version, "storage_version_invalid")
        _prefixed_digest(self.artifact_image_digest, "artifact_image_digest_invalid")
        _ref(self.artifact_task_definition, "artifact_task_definition_invalid")
        _digest(self.purpose_digest, "purpose_digest_invalid")
        _digest(self.authority_root_digest, "authority_root_digest_invalid")
        _digest(self.authority_policy_digest, "authority_policy_digest_invalid")
        _prefixed_digest(
            self.contract_universe_digest,
            "contract_universe_digest_invalid",
        )
        _ref(self.binding_id, "binding_id_invalid")
        _ref(self.lineage_id, "lineage_id_invalid")
        _require(
            type(self.invariants) is tuple
            and self.invariants == CONSTITUTIONAL_INVARIANTS_V1,
            "constitutional_invariants_invalid",
        )
        _require(
            self.coherence_role == COHERENCE_ROLE_V1,
            "coherence_role_invalid",
        )


@dataclass(frozen=True)
class ConstitutionalActivationEvidenceV1(_Contract):
    """Durable bridge from the artifact task identity to an activated runtime."""

    VERSION = "constitutional_activation_evidence_v1"

    activation_id: str
    binding_id: str
    constitution_digest: str
    source_task_definition: str
    activated_task_definition: str
    runtime_service: str
    runtime_artifact_digest: str
    evidence_reference: str
    evidence_digest: str
    observed_at: str

    def __post_init__(self) -> None:
        _require(
            type(self) is ConstitutionalActivationEvidenceV1,
            "exact_contract_type_required",
        )
        for value, code in (
            (self.activation_id, "activation_id_invalid"),
            (self.binding_id, "binding_id_invalid"),
            (self.source_task_definition, "source_task_definition_invalid"),
            (self.activated_task_definition, "activated_task_definition_invalid"),
            (self.runtime_service, "runtime_service_invalid"),
            (self.evidence_reference, "activation_evidence_reference_invalid"),
        ):
            _ref(value, code)
        _digest(self.constitution_digest, "constitution_digest_invalid")
        _prefixed_digest(self.runtime_artifact_digest, "runtime_artifact_digest_invalid")
        _digest(self.evidence_digest, "activation_evidence_digest_invalid")
        _canonical_time(self.observed_at, "activation_observed_at_invalid")


@dataclass(frozen=True)
class ConstitutionalBindingV1(_Contract):
    """Explicit governed binding beneath the SCQOS authority root."""

    VERSION = "constitutional_binding_v1"

    artifact: CanonicalConstitutionArtifactV1
    activation: ConstitutionalActivationEvidenceV1
    status: ConstitutionalBindingStatus
    established_at: str

    def __post_init__(self) -> None:
        _require(type(self) is ConstitutionalBindingV1, "exact_contract_type_required")
        _require(
            type(self.artifact) is CanonicalConstitutionArtifactV1,
            "canonical_constitution_artifact_required",
        )
        _require(
            type(self.activation) is ConstitutionalActivationEvidenceV1,
            "constitutional_activation_evidence_required",
        )
        _require(
            type(self.status) is ConstitutionalBindingStatus
            and self.status is ConstitutionalBindingStatus.ACTIVE,
            "constitutional_binding_status_invalid",
        )
        established = _canonical_time(
            self.established_at,
            "binding_established_at_invalid",
        )
        observed = _canonical_time(
            self.activation.observed_at,
            "activation_observed_at_invalid",
        )
        _require(observed <= established, "activation_after_binding_establishment")
        _require(
            self.activation.binding_id == self.artifact.binding_id,
            "binding_id_mismatch",
        )
        _require(
            self.activation.constitution_digest == self.artifact.constitution_digest,
            "constitution_digest_mismatch",
        )
        _require(
            self.activation.source_task_definition == self.artifact.artifact_task_definition,
            "artifact_task_definition_mismatch",
        )
        _require(
            self.activation.runtime_artifact_digest == self.artifact.artifact_image_digest,
            "runtime_artifact_digest_mismatch",
        )

    @property
    def activated_runtime_task_definition(self) -> str:
        return self.activation.activated_task_definition


@dataclass(frozen=True)
class AuthorityWitnessAttestationV1(_Contract):
    """Current witness attestation of the exact active constitutional binding."""

    VERSION = "authority_witness_v1"

    witness_id: str
    witness_reference: str
    binding_digest: str
    binding_id: str
    constitution_digest: str
    purpose_digest: str
    authority_root_digest: str
    authority_policy_digest: str
    contract_universe_digest: str
    runtime_artifact_digest: str
    runtime_task_definition: str
    invariants: tuple[str, ...]
    sequence: int
    succession_epoch: int
    observed_at: str
    valid_through: str

    def __post_init__(self) -> None:
        _require(
            type(self) is AuthorityWitnessAttestationV1,
            "exact_contract_type_required",
        )
        for value, code in (
            (self.witness_id, "witness_id_invalid"),
            (self.witness_reference, "witness_reference_invalid"),
            (self.binding_id, "binding_id_invalid"),
            (self.runtime_task_definition, "runtime_task_definition_invalid"),
        ):
            _ref(value, code)
        for value, code in (
            (self.binding_digest, "binding_digest_invalid"),
            (self.constitution_digest, "constitution_digest_invalid"),
            (self.purpose_digest, "purpose_digest_invalid"),
            (self.authority_root_digest, "authority_root_digest_invalid"),
            (self.authority_policy_digest, "authority_policy_digest_invalid"),
        ):
            _digest(value, code)
        _prefixed_digest(
            self.contract_universe_digest,
            "contract_universe_digest_invalid",
        )
        _prefixed_digest(
            self.runtime_artifact_digest,
            "runtime_artifact_digest_invalid",
        )
        _require(
            type(self.invariants) is tuple
            and self.invariants == CONSTITUTIONAL_INVARIANTS_V1,
            "constitutional_invariants_invalid",
        )
        _require(type(self.sequence) is int and self.sequence >= 0, "sequence_invalid")
        _require(
            type(self.succession_epoch) is int and self.succession_epoch >= 0,
            "succession_epoch_invalid",
        )
        observed = _canonical_time(self.observed_at, "witness_observed_at_invalid")
        valid_through = _canonical_time(self.valid_through, "witness_valid_through_invalid")
        _require(observed < valid_through, "witness_validity_window_invalid")


def validate_authority_witness_binding(
    binding: ConstitutionalBindingV1,
    attestation: AuthorityWitnessAttestationV1,
    *,
    authoritative_time: str,
) -> None:
    """Validate exact binding/currentness; this function does not issue permission."""

    _require(type(binding) is ConstitutionalBindingV1, "constitutional_binding_required")
    _require(
        type(attestation) is AuthorityWitnessAttestationV1,
        "authority_witness_attestation_required",
    )
    artifact = binding.artifact
    expected = (
        binding.digest,
        artifact.binding_id,
        artifact.constitution_digest,
        artifact.purpose_digest,
        artifact.authority_root_digest,
        artifact.authority_policy_digest,
        artifact.contract_universe_digest,
        artifact.artifact_image_digest,
        binding.activated_runtime_task_definition,
        artifact.invariants,
    )
    actual = (
        attestation.binding_digest,
        attestation.binding_id,
        attestation.constitution_digest,
        attestation.purpose_digest,
        attestation.authority_root_digest,
        attestation.authority_policy_digest,
        attestation.contract_universe_digest,
        attestation.runtime_artifact_digest,
        attestation.runtime_task_definition,
        attestation.invariants,
    )
    _require(actual == expected, "authority_witness_binding_mismatch")
    now = _canonical_time(authoritative_time, "authoritative_time_invalid")
    observed = _canonical_time(attestation.observed_at, "witness_observed_at_invalid")
    valid_through = _canonical_time(
        attestation.valid_through,
        "witness_valid_through_invalid",
    )
    _require(observed <= now <= valid_through, "authority_witness_not_current")

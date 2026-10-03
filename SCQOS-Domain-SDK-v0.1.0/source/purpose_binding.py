"""Constitution v1 authoritative-purpose contracts.

A purpose binding makes mission intent explicit, versioned, durable and bound
to current governed authority. Structural validity is not itself permission.
"""

from dataclasses import dataclass
from enum import Enum

from authority_lineage import AuthorityLineageV1, validate_lineage_for_constitutional_binding
from constitutional_binding import (
    ConstitutionalBindingV1,
    _Contract,
    _canonical_time,
    _digest,
    _ref,
    _require,
)
from scqos_contract_digest import contract_digest


class PurposeBindingStatus(str, Enum):
    ACTIVE = "ACTIVE"


def purpose_content_digest(*, purpose_id: str, statement: str) -> str:
    """Digest the canonical purpose content already named by Constitution v1."""

    return contract_digest({"purpose_id": purpose_id, "statement": statement})


@dataclass(frozen=True)
class PurposeAuthorizationEvidenceV1(_Contract):
    """Durable verification that current authority authorized one purpose version."""

    VERSION = "purpose_authorization_evidence_v1"

    purpose_content_digest: str
    purpose_version: str
    authority_lineage_digest: str
    signer_authority_id: str
    signer_authority_digest: str
    signature_reference: str
    signature_digest: str
    verification_evidence_reference: str
    verification_evidence_digest: str
    verified_at: str

    def __post_init__(self) -> None:
        _require(
            type(self) is PurposeAuthorizationEvidenceV1,
            "exact_contract_type_required",
        )
        _digest(self.purpose_content_digest, "purpose_content_digest_invalid")
        _digest(self.authority_lineage_digest, "authority_lineage_digest_invalid")
        _digest(self.signer_authority_digest, "signer_authority_digest_invalid")
        _digest(self.signature_digest, "purpose_signature_digest_invalid")
        _digest(
            self.verification_evidence_digest,
            "purpose_verification_evidence_digest_invalid",
        )
        for value, code in (
            (self.purpose_version, "purpose_version_invalid"),
            (self.signer_authority_id, "signer_authority_id_invalid"),
            (self.signature_reference, "purpose_signature_reference_invalid"),
            (
                self.verification_evidence_reference,
                "purpose_verification_evidence_reference_invalid",
            ),
        ):
            _ref(value, code)
        _canonical_time(self.verified_at, "purpose_verified_at_invalid")


@dataclass(frozen=True)
class PurposeBindingV1(_Contract):
    """Authoritative versioned purpose bound to Constitution and authority lineage."""

    VERSION = "purpose_binding_v1"

    purpose_id: str
    purpose_version: str
    statement: str
    purpose_content_digest: str
    constitution_digest: str
    constitutional_binding_digest: str
    authority_root_digest: str
    authority_policy_digest: str
    authority_lineage_digest: str
    authorizing_authority_id: str
    authorizing_authority_digest: str
    authorization: PurposeAuthorizationEvidenceV1
    storage_reference: str
    storage_version: str
    status: PurposeBindingStatus
    effective_at: str
    established_at: str

    def __post_init__(self) -> None:
        _require(type(self) is PurposeBindingV1, "exact_contract_type_required")
        for value, code in (
            (self.purpose_id, "purpose_id_invalid"),
            (self.purpose_version, "purpose_version_invalid"),
            (self.statement, "purpose_statement_invalid"),
            (self.authorizing_authority_id, "authorizing_authority_id_invalid"),
            (self.storage_reference, "purpose_storage_reference_invalid"),
            (self.storage_version, "purpose_storage_version_invalid"),
        ):
            _ref(value, code)
        for value, code in (
            (self.purpose_content_digest, "purpose_content_digest_invalid"),
            (self.constitution_digest, "constitution_digest_invalid"),
            (self.constitutional_binding_digest, "constitutional_binding_digest_invalid"),
            (self.authority_root_digest, "authority_root_digest_invalid"),
            (self.authority_policy_digest, "authority_policy_digest_invalid"),
            (self.authority_lineage_digest, "authority_lineage_digest_invalid"),
            (self.authorizing_authority_digest, "authorizing_authority_digest_invalid"),
        ):
            _digest(value, code)
        _require(
            self.purpose_content_digest
            == purpose_content_digest(purpose_id=self.purpose_id, statement=self.statement),
            "purpose_content_digest_mismatch",
        )
        _require(
            type(self.authorization) is PurposeAuthorizationEvidenceV1,
            "purpose_authorization_evidence_required",
        )
        _require(
            type(self.status) is PurposeBindingStatus
            and self.status is PurposeBindingStatus.ACTIVE,
            "purpose_binding_status_invalid",
        )
        effective = _canonical_time(self.effective_at, "purpose_effective_at_invalid")
        established = _canonical_time(self.established_at, "purpose_established_at_invalid")
        verified = _canonical_time(self.authorization.verified_at, "purpose_verified_at_invalid")
        _require(effective <= established, "purpose_effective_after_establishment")
        _require(verified <= established, "purpose_verification_after_establishment")
        _require(
            self.authorization.purpose_content_digest == self.purpose_content_digest,
            "purpose_authorization_content_mismatch",
        )
        _require(
            self.authorization.purpose_version == self.purpose_version,
            "purpose_authorization_version_mismatch",
        )
        _require(
            self.authorization.authority_lineage_digest == self.authority_lineage_digest,
            "purpose_authorization_lineage_mismatch",
        )
        _require(
            (
                self.authorization.signer_authority_id,
                self.authorization.signer_authority_digest,
            )
            == (
                self.authorizing_authority_id,
                self.authorizing_authority_digest,
            ),
            "purpose_authorizing_authority_mismatch",
        )


def validate_purpose_binding(
    binding: ConstitutionalBindingV1,
    lineage: AuthorityLineageV1,
    purpose: PurposeBindingV1,
) -> None:
    """Require purpose, Constitution and current authority to describe one state."""

    _require(type(binding) is ConstitutionalBindingV1, "constitutional_binding_required")
    _require(type(lineage) is AuthorityLineageV1, "authority_lineage_required")
    _require(type(purpose) is PurposeBindingV1, "purpose_binding_required")
    validate_lineage_for_constitutional_binding(binding, lineage)
    artifact = binding.artifact
    _require(
        purpose.purpose_content_digest == artifact.purpose_digest,
        "purpose_constitution_digest_mismatch",
    )
    _require(
        purpose.constitution_digest == artifact.constitution_digest,
        "purpose_constitution_identity_mismatch",
    )
    _require(
        purpose.constitutional_binding_digest == binding.digest,
        "purpose_constitutional_binding_mismatch",
    )
    _require(
        purpose.authority_root_digest == artifact.authority_root_digest,
        "purpose_authority_root_mismatch",
    )
    _require(
        purpose.authority_policy_digest == artifact.authority_policy_digest,
        "purpose_authority_policy_mismatch",
    )
    _require(
        purpose.authority_lineage_digest == lineage.digest,
        "purpose_authority_lineage_mismatch",
    )
    _require(
        (
            purpose.authorizing_authority_id,
            purpose.authorizing_authority_digest,
        )
        == (
            lineage.current_authority_id,
            lineage.current_authority_digest,
        ),
        "purpose_not_authorized_by_current_authority",
    )

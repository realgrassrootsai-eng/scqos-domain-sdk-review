"""Canonical Constitution v1 transition proof bundle contracts.

A proof bundle records durable proof state. It does not grant permission merely
because it is structurally valid. Release requires a PERMIT bundle whose every
required artifact is durably bound and re-resolved by digest.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from authority_lineage import AuthorityLineageV1, validate_lineage_for_constitutional_binding
from constitutional_binding import (
    AuthorityWitnessAttestationV1,
    ConstitutionalBindingV1,
    _Contract,
    _canonical_time,
    _digest,
    _ref,
    _require,
    validate_authority_witness_binding,
)
from governed_transition import TransitionDecision, TransitionReceipt
from purpose_binding import PurposeBindingV1, validate_purpose_binding
from scqos_contract_digest import canonical_contract_json, contract_digest
from scqos_governance_experience import TransitionEvidenceBundle
from scqos_runtime_evidence import BoundaryReleaseEvidence


class ProofArtifactState(str, Enum):
    BOUND = "BOUND"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ProofArtifactRole(str, Enum):
    TRANSITION_RECEIPT = "transition_receipt"
    TRANSITION_EVIDENCE_BUNDLE = "transition_evidence_bundle"
    CONSTITUTIONAL_BINDING = "constitutional_binding"
    AUTHORITY_ROOT = "authority_root"
    AUTHORITY_POLICY = "authority_policy"
    AUTHORITY_LINEAGE = "authority_lineage"
    PURPOSE_BINDING = "purpose_binding"
    AUTHORITY_WITNESS = "authority_witness"
    OBSERVATION = "observation"
    RELEASE_EVIDENCE = "release_evidence"


_TRANSITION_SCOPED_ROLES = {
    ProofArtifactRole.TRANSITION_RECEIPT,
    ProofArtifactRole.TRANSITION_EVIDENCE_BUNDLE,
    ProofArtifactRole.OBSERVATION,
    ProofArtifactRole.RELEASE_EVIDENCE,
}


_SINGLETON_ROLES = (
    ProofArtifactRole.TRANSITION_RECEIPT,
    ProofArtifactRole.TRANSITION_EVIDENCE_BUNDLE,
    ProofArtifactRole.CONSTITUTIONAL_BINDING,
    ProofArtifactRole.AUTHORITY_ROOT,
    ProofArtifactRole.AUTHORITY_POLICY,
    ProofArtifactRole.AUTHORITY_LINEAGE,
    ProofArtifactRole.PURPOSE_BINDING,
    ProofArtifactRole.AUTHORITY_WITNESS,
    ProofArtifactRole.RELEASE_EVIDENCE,
)


@dataclass(frozen=True)
class DurableProofArtifactRefV1(_Contract):
    """Durable identity of one artifact required by canonical transition proof."""

    VERSION = "durable_proof_artifact_ref_v1"

    role: ProofArtifactRole
    logical_id: str
    schema_version: str
    transition_id: str | None
    state: ProofArtifactState
    artifact_digest: str | None
    storage_reference: str | None
    storage_version: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require(type(self) is DurableProofArtifactRefV1, "exact_contract_type_required")
        _require(type(self.role) is ProofArtifactRole, "proof_artifact_role_invalid")
        _require(type(self.state) is ProofArtifactState, "proof_artifact_state_invalid")
        _ref(self.logical_id, "proof_artifact_logical_id_invalid")
        _ref(self.schema_version, "proof_artifact_schema_version_invalid")
        if self.role in _TRANSITION_SCOPED_ROLES:
            _require(self.transition_id is not None, "proof_artifact_transition_id_required")
            _ref(self.transition_id, "proof_artifact_transition_id_invalid")
        else:
            _require(self.transition_id is None, "shared_proof_artifact_transition_id_forbidden")
        if self.state is ProofArtifactState.BOUND:
            _require(self.artifact_digest is not None, "bound_proof_artifact_digest_required")
            _digest(self.artifact_digest, "proof_artifact_digest_invalid")
            _require(self.storage_reference is not None, "bound_proof_artifact_storage_required")
            _require(self.storage_version is not None, "bound_proof_artifact_version_required")
            _ref(self.storage_reference, "proof_artifact_storage_reference_invalid")
            _ref(self.storage_version, "proof_artifact_storage_version_invalid")
            _require(self.reason is None, "bound_proof_artifact_reason_forbidden")
        else:
            _require(
                self.artifact_digest is None
                and self.storage_reference is None
                and self.storage_version is None,
                "unbound_proof_artifact_cannot_claim_storage",
            )
            _require(self.reason is not None, "unbound_proof_artifact_reason_required")
            _ref(self.reason, "unbound_proof_artifact_reason_invalid")


@dataclass(frozen=True, init=False)
class TransitionProofBundleV1(_Contract):
    """Canonical durable proof manifest for one governed transition."""

    VERSION = "transition_proof_bundle_v1"

    transition_id: str
    request_id: str
    actor_id: str
    session_id: str
    decision: TransitionDecision
    consequence_digest: str
    transition_receipt_digest: str
    transition_evidence_bundle_digest: str
    constitution_digest: str | None
    constitutional_binding_digest: str | None
    authority_root_digest: str | None
    authority_policy_digest: str | None
    authority_policy_version: str | None
    authority_lineage_digest: str | None
    purpose_binding_digest: str | None
    purpose_version: str | None
    authority_witness_attestation_digest: str | None
    observation_digests: tuple[str, ...]
    release_evidence_digest: str | None
    artifact_refs: tuple[DurableProofArtifactRefV1, ...]
    authoritative_time: str
    assembled_at: str

    def __init__(
        self,
        *,
        receipt: TransitionReceipt,
        evidence_bundle: TransitionEvidenceBundle,
        artifact_refs: Sequence[DurableProofArtifactRefV1],
        authoritative_time: str,
        assembled_at: str,
        constitutional_binding: ConstitutionalBindingV1 | None = None,
        authority_lineage: AuthorityLineageV1 | None = None,
        purpose_binding: PurposeBindingV1 | None = None,
        authority_witness: AuthorityWitnessAttestationV1 | None = None,
        release_evidence: BoundaryReleaseEvidence | None = None,
    ) -> None:
        _require(type(receipt) is TransitionReceipt, "transition_receipt_required")
        _require(type(evidence_bundle) is TransitionEvidenceBundle, "transition_evidence_bundle_required")
        refs = tuple(artifact_refs)
        proposal = receipt.proposal
        _validate_artifact_ref_set(refs, proposal.transition_id)
        bundle_payload = evidence_bundle.to_contract_dict()
        _require(
            bundle_payload["source_transition_id"] == proposal.transition_id,
            "evidence_bundle_transition_mismatch",
        )
        _require(
            canonical_contract_json(bundle_payload["proposal"])
            == canonical_contract_json(proposal.to_contract_dict()),
            "evidence_bundle_proposal_mismatch",
        )
        receipt_digest = contract_digest(receipt.to_contract_dict())
        evidence_digest = evidence_bundle.digest
        _validate_source_artifact(
            refs,
            ProofArtifactRole.TRANSITION_RECEIPT,
            source_digest=receipt_digest,
            schema_version="governed_transition_v1",
        )
        _validate_source_artifact(
            refs,
            ProofArtifactRole.TRANSITION_EVIDENCE_BUNDLE,
            source_digest=evidence_digest,
            schema_version="transition_evidence_bundle_v1",
        )

        constitutional_digest = None
        binding_digest = None
        root_digest = None
        policy_digest = None
        policy_version = None
        lineage_digest = None
        purpose_digest = None
        purpose_version = None
        witness_digest = None
        release_digest = None

        if constitutional_binding is not None:
            _require(
                type(constitutional_binding) is ConstitutionalBindingV1,
                "constitutional_binding_invalid",
            )
            artifact = constitutional_binding.artifact
            constitutional_digest = artifact.constitution_digest
            binding_digest = constitutional_binding.digest
            root_digest = artifact.authority_root_digest
            policy_digest = artifact.authority_policy_digest
            _validate_source_artifact(
                refs,
                ProofArtifactRole.CONSTITUTIONAL_BINDING,
                source_digest=binding_digest,
                schema_version="constitutional_binding_v1",
            )
            root_ref = _single_ref(refs, ProofArtifactRole.AUTHORITY_ROOT)
            policy_ref = _single_ref(refs, ProofArtifactRole.AUTHORITY_POLICY)
            if root_ref.state is ProofArtifactState.BOUND:
                _require(root_ref.artifact_digest == root_digest, "authority_root_proof_digest_mismatch")
            if policy_ref.state is ProofArtifactState.BOUND:
                _require(policy_ref.artifact_digest == policy_digest, "authority_policy_proof_digest_mismatch")
            policy_version = policy_ref.schema_version
        else:
            _validate_source_artifact(refs, ProofArtifactRole.CONSTITUTIONAL_BINDING, source_digest=None)

        if authority_lineage is not None:
            _require(constitutional_binding is not None, "lineage_requires_constitutional_binding")
            _require(type(authority_lineage) is AuthorityLineageV1, "authority_lineage_invalid")
            validate_lineage_for_constitutional_binding(constitutional_binding, authority_lineage)
            lineage_digest = authority_lineage.digest
            _validate_source_artifact(
                refs,
                ProofArtifactRole.AUTHORITY_LINEAGE,
                source_digest=lineage_digest,
                schema_version="authority_lineage_v1",
            )
        else:
            _validate_source_artifact(refs, ProofArtifactRole.AUTHORITY_LINEAGE, source_digest=None)

        if purpose_binding is not None:
            _require(
                constitutional_binding is not None and authority_lineage is not None,
                "purpose_requires_constitution_and_lineage",
            )
            _require(type(purpose_binding) is PurposeBindingV1, "purpose_binding_invalid")
            validate_purpose_binding(constitutional_binding, authority_lineage, purpose_binding)
            purpose_digest = purpose_binding.digest
            purpose_version = purpose_binding.purpose_version
            _validate_source_artifact(
                refs,
                ProofArtifactRole.PURPOSE_BINDING,
                source_digest=purpose_digest,
                schema_version="purpose_binding_v1",
            )
        else:
            _validate_source_artifact(refs, ProofArtifactRole.PURPOSE_BINDING, source_digest=None)

        observed = _canonical_time(authoritative_time, "proof_authoritative_time_invalid")
        assembled = _canonical_time(assembled_at, "proof_assembled_at_invalid")
        _require(observed <= assembled, "proof_assembled_before_authoritative_time")

        if authority_witness is not None:
            _require(constitutional_binding is not None, "witness_requires_constitutional_binding")
            _require(type(authority_witness) is AuthorityWitnessAttestationV1, "authority_witness_invalid")
            validate_authority_witness_binding(
                constitutional_binding,
                authority_witness,
                authoritative_time=authoritative_time,
            )
            witness_digest = authority_witness.digest
            _validate_source_artifact(
                refs,
                ProofArtifactRole.AUTHORITY_WITNESS,
                source_digest=witness_digest,
                schema_version="authority_witness_v1",
            )
        else:
            _validate_source_artifact(refs, ProofArtifactRole.AUTHORITY_WITNESS, source_digest=None)

        if release_evidence is not None:
            _require(type(release_evidence) is BoundaryReleaseEvidence, "release_evidence_invalid")
            _require(release_evidence.transition_id == proposal.transition_id, "release_transition_mismatch")
            _require(release_evidence.consequence_type == proposal.consequence_type, "release_consequence_type_mismatch")
            _require(release_evidence.boundary == proposal.boundary, "release_boundary_mismatch")
            _require(
                release_evidence.release_consequence_digest == proposal.proposed_consequence_digest,
                "release_consequence_digest_mismatch",
            )
            release_digest = contract_digest(release_evidence.to_contract_dict())
            _validate_source_artifact(
                refs,
                ProofArtifactRole.RELEASE_EVIDENCE,
                source_digest=release_digest,
                schema_version="boundary_release_evidence_v1",
            )
        else:
            _validate_source_artifact(refs, ProofArtifactRole.RELEASE_EVIDENCE, source_digest=None)

        observations = tuple(
            ref.artifact_digest
            for ref in refs
            if ref.role is ProofArtifactRole.OBSERVATION
            and ref.state is ProofArtifactState.BOUND
            and ref.artifact_digest is not None
        )

        object.__setattr__(self, "transition_id", proposal.transition_id)
        object.__setattr__(self, "request_id", proposal.request_id)
        object.__setattr__(self, "actor_id", proposal.actor_id)
        object.__setattr__(self, "session_id", proposal.session_id)
        object.__setattr__(self, "decision", receipt.decision)
        object.__setattr__(self, "consequence_digest", proposal.proposed_consequence_digest)
        object.__setattr__(self, "transition_receipt_digest", receipt_digest)
        object.__setattr__(self, "transition_evidence_bundle_digest", evidence_digest)
        object.__setattr__(self, "constitution_digest", constitutional_digest)
        object.__setattr__(self, "constitutional_binding_digest", binding_digest)
        object.__setattr__(self, "authority_root_digest", root_digest)
        object.__setattr__(self, "authority_policy_digest", policy_digest)
        object.__setattr__(self, "authority_policy_version", policy_version)
        object.__setattr__(self, "authority_lineage_digest", lineage_digest)
        object.__setattr__(self, "purpose_binding_digest", purpose_digest)
        object.__setattr__(self, "purpose_version", purpose_version)
        object.__setattr__(self, "authority_witness_attestation_digest", witness_digest)
        object.__setattr__(self, "observation_digests", observations)
        object.__setattr__(self, "release_evidence_digest", release_digest)
        object.__setattr__(self, "artifact_refs", refs)
        object.__setattr__(self, "authoritative_time", authoritative_time)
        object.__setattr__(self, "assembled_at", assembled_at)


def _single_ref(
    refs: tuple[DurableProofArtifactRefV1, ...],
    role: ProofArtifactRole,
) -> DurableProofArtifactRefV1:
    matches = tuple(ref for ref in refs if ref.role is role)
    _require(len(matches) == 1, f"proof_artifact_{role.value}_cardinality_invalid")
    return matches[0]


def _validate_artifact_ref_set(
    refs: tuple[DurableProofArtifactRefV1, ...],
    transition_id: str,
) -> None:
    _require(bool(refs), "proof_artifact_refs_required")
    _require(
        all(type(ref) is DurableProofArtifactRefV1 for ref in refs),
        "proof_artifact_ref_invalid",
    )
    for role in _SINGLETON_ROLES:
        _single_ref(refs, role)
    observations = tuple(ref for ref in refs if ref.role is ProofArtifactRole.OBSERVATION)
    _require(bool(observations), "proof_observation_artifact_required")
    for ref in refs:
        if ref.role in _TRANSITION_SCOPED_ROLES:
            _require(ref.transition_id == transition_id, "proof_artifact_transition_mismatch")
    expected_roles = (
        ProofArtifactRole.TRANSITION_RECEIPT,
        ProofArtifactRole.TRANSITION_EVIDENCE_BUNDLE,
        ProofArtifactRole.CONSTITUTIONAL_BINDING,
        ProofArtifactRole.AUTHORITY_ROOT,
        ProofArtifactRole.AUTHORITY_POLICY,
        ProofArtifactRole.AUTHORITY_LINEAGE,
        ProofArtifactRole.PURPOSE_BINDING,
        ProofArtifactRole.AUTHORITY_WITNESS,
        *([ProofArtifactRole.OBSERVATION] * len(observations)),
        ProofArtifactRole.RELEASE_EVIDENCE,
    )
    _require(tuple(ref.role for ref in refs) == expected_roles, "proof_artifact_order_invalid")
    bound_storage = tuple(
        ref.storage_reference
        for ref in refs
        if ref.state is ProofArtifactState.BOUND
    )
    _require(len(bound_storage) == len(set(bound_storage)), "proof_artifact_storage_reused")


def _validate_source_artifact(
    refs: tuple[DurableProofArtifactRefV1, ...],
    role: ProofArtifactRole,
    *,
    source_digest: str | None,
    schema_version: str | None = None,
) -> None:
    ref = _single_ref(refs, role)
    if source_digest is None:
        _require(ref.state is not ProofArtifactState.BOUND, f"{role.value}_source_missing_but_artifact_bound")
        return
    if schema_version is not None:
        _require(ref.schema_version == schema_version, f"{role.value}_artifact_schema_mismatch")
    if ref.state is ProofArtifactState.BOUND:
        _require(ref.artifact_digest == source_digest, f"{role.value}_artifact_digest_mismatch")


def validate_resolved_transition_proof_artifacts(
    bundle: TransitionProofBundleV1,
    resolved_artifact_digests: Mapping[str, str],
) -> None:
    """Require every bound durable reference to resolve to the recorded digest."""

    _require(type(bundle) is TransitionProofBundleV1, "transition_proof_bundle_required")
    _require(type(resolved_artifact_digests) is dict, "resolved_artifact_digests_invalid")
    expected = {
        ref.storage_reference: ref.artifact_digest
        for ref in bundle.artifact_refs
        if ref.state is ProofArtifactState.BOUND
    }
    _require(set(resolved_artifact_digests) == set(expected), "resolved_artifact_set_mismatch")
    for reference, digest in resolved_artifact_digests.items():
        _ref(reference, "resolved_artifact_reference_invalid")
        _digest(digest, "resolved_artifact_digest_invalid")
        _require(digest == expected[reference], "resolved_artifact_digest_mismatch")


def validate_transition_proof_bundle_for_release(
    bundle: TransitionProofBundleV1,
    resolved_artifact_digests: Mapping[str, str],
) -> None:
    """Validate Reference sufficiency for release; this function issues no PERMIT."""

    _require(type(bundle) is TransitionProofBundleV1, "transition_proof_bundle_required")
    _require(bundle.decision is TransitionDecision.PERMIT, "proof_bundle_permit_required")
    _require(
        all(ref.state is ProofArtifactState.BOUND for ref in bundle.artifact_refs),
        "proof_artifacts_incomplete",
    )
    _require(bool(bundle.observation_digests), "bound_observation_required")
    for value, code in (
        (bundle.constitution_digest, "constitution_proof_required"),
        (bundle.constitutional_binding_digest, "constitutional_binding_proof_required"),
        (bundle.authority_root_digest, "authority_root_proof_required"),
        (bundle.authority_policy_digest, "authority_policy_proof_required"),
        (bundle.authority_lineage_digest, "authority_lineage_proof_required"),
        (bundle.purpose_binding_digest, "purpose_binding_proof_required"),
        (bundle.authority_witness_attestation_digest, "authority_witness_proof_required"),
        (bundle.release_evidence_digest, "release_evidence_proof_required"),
    ):
        _require(value is not None, code)
    _require(bundle.authority_policy_version is not None, "authority_policy_version_required")
    _require(bundle.purpose_version is not None, "purpose_version_required")
    validate_resolved_transition_proof_artifacts(bundle, resolved_artifact_digests)

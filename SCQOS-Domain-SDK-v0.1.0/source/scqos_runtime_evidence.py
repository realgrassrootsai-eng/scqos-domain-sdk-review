"""Runtime execution and provenance evidence for SCQOS."""

from __future__ import annotations

import hashlib
import json
import re

from dataclasses import dataclass
from typing import Any, Sequence


SCQOS_RUNTIME_EVIDENCE_VERSION = "scqos_runtime_evidence_v8"

_ALLOWED_IDENTITY_ORIGINS = {
    "cognito_verified",
    "cognito_lab_verified",
    "local_personal_override",
    "guest",
}

_ALLOWED_MODEL_BACKENDS = {
    "together",
    "bedrock_scout",
    "governed_aws",
}

_ALLOWED_RUNTIME_CLOCKS = {
    "server_utc",
}

_ALLOWED_RUNTIME_OBSERVATION_KINDS = {
    "request_received",
}

_ALLOWED_CONTINUITY_REQUIREMENT_BASES = {
    "personal_state_request",
    "personal_state_unresolved",
    "assistant_prior_output",
    "preexisting_evidence",
    "no_inherited_state_dependency",
}

_ALLOWED_CONTINUITY_REQUIREMENT_STATUSES = {
    "required",
    "not_required",
    "unresolved",
}

_ALLOWED_CONTINUITY_DETERMINATION_SOURCES = {
    "server_continuity_classifier",
}

class SCQOSRuntimeEvidenceError(ValueError):
    """Raised when runtime evidence violates its structural contract."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _normalize_required_text(
    value: Any,
    *,
    reason: str,
) -> str:
    if not isinstance(value, str):
        raise SCQOSRuntimeEvidenceError(
            reason=reason
        )

    normalized = value.strip()

    if not normalized:
        raise SCQOSRuntimeEvidenceError(
            reason=reason
        )

    return normalized


def _normalize_optional_text(
    value: Any,
    *,
    reason: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise SCQOSRuntimeEvidenceError(
            reason=reason
        )

    normalized = value.strip()

    return normalized or None

@dataclass(frozen=True, init=False)
class TemporalEvidence:
    """
    Record both caller-claimed time and authoritative runtime time.

    The caller-claimed timestamp is evidence supplied with the request.
    It does not become authoritative merely because it is well formed.

    The runtime observation is captured by the server from its UTC clock
    and records what event that authoritative timestamp describes.
    """

    claimed_observation_timestamp: str | None
    runtime_observed_at: str
    runtime_clock: str
    runtime_observation_kind: str
    authority_valid_from: str | None
    authority_expires_at: str | None
    authority_reference: str | None

    def __init__(
        self,
        *,
        claimed_observation_timestamp: str | None,
        runtime_observed_at: str,
        runtime_clock: str,
        runtime_observation_kind: str,
        authority_valid_from: str | None = None,
        authority_expires_at: str | None = None,
        authority_reference: str | None = None,
    ) -> None:
        normalized_claimed_timestamp = _normalize_optional_text(
            claimed_observation_timestamp,
            reason="claimed_observation_timestamp_invalid",
        )

        normalized_runtime_observed_at = _normalize_required_text(
            runtime_observed_at,
            reason="runtime_observed_at_required",
        )

        normalized_runtime_clock = _normalize_required_text(
            runtime_clock,
            reason="runtime_clock_required",
        ).lower()

        if normalized_runtime_clock not in _ALLOWED_RUNTIME_CLOCKS:
            raise SCQOSRuntimeEvidenceError(
                reason="runtime_clock_invalid"
            )

        normalized_observation_kind = _normalize_required_text(
            runtime_observation_kind,
            reason="runtime_observation_kind_required",
        ).lower()

        if (
            normalized_observation_kind
            not in _ALLOWED_RUNTIME_OBSERVATION_KINDS
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="runtime_observation_kind_invalid"
            )

        object.__setattr__(
            self,
            "claimed_observation_timestamp",
            normalized_claimed_timestamp,
        )
        object.__setattr__(
            self,
            "runtime_observed_at",
            normalized_runtime_observed_at,
        )
        object.__setattr__(
            self,
            "runtime_clock",
            normalized_runtime_clock,
        )
        object.__setattr__(
            self,
            "runtime_observation_kind",
            normalized_observation_kind,
        )
        object.__setattr__(
            self,
            "authority_valid_from",
            _normalize_optional_text(
                authority_valid_from,
                reason="authority_valid_from_invalid",
            ),
        )
        object.__setattr__(
            self,
            "authority_expires_at",
            _normalize_optional_text(
                authority_expires_at,
                reason="authority_expires_at_invalid",
            ),
        )
        object.__setattr__(
            self,
            "authority_reference",
            _normalize_optional_text(
                authority_reference,
                reason="authority_reference_invalid",
            ),
        )

    def to_contract_dict(self) -> dict[str, Any]:
        result = {
            "claimed_observation_timestamp": (
                self.claimed_observation_timestamp
            ),
            "runtime_observed_at": self.runtime_observed_at,
            "runtime_clock": self.runtime_clock,
            "runtime_observation_kind": (
                self.runtime_observation_kind
            ),
        }
        if (
            self.authority_valid_from is not None
            or self.authority_expires_at is not None
            or self.authority_reference is not None
        ):
            result.update({
                "authority_valid_from": self.authority_valid_from,
                "authority_expires_at": self.authority_expires_at,
                "authority_reference": self.authority_reference,
            })
        return result

@dataclass(frozen=True, init=False)
class IdentityProvenanceEvidence:
    """
    Record the explicit origin from which runtime identity was resolved.

    This records provenance only. It does not decide whether Genesis passes.
    """

    transition_id: str
    # Stable Cognito sub; principal_reference retains the username policy key.
    authenticated_subject: str | None
    origin_class: str
    actor_type: str
    session_id: str
    principal_reference: str

    def __init__(
        self,
        *,
        transition_id: str,
        authenticated_subject: str | None = None,
        origin_class: str,
        actor_type: str,
        session_id: str,
        principal_reference: str,
    ) -> None:
        object.__setattr__(
            self, "transition_id",
            _normalize_required_text(
                transition_id, reason="identity_transition_id_required",
            ),
        )
        object.__setattr__(
            self, "authenticated_subject",
            _normalize_optional_text(
                authenticated_subject, reason="identity_authenticated_subject_invalid",
            ),
        )
        normalized_origin = _normalize_required_text(
            origin_class,
            reason="identity_origin_class_required",
        ).lower()

        if normalized_origin not in _ALLOWED_IDENTITY_ORIGINS:
            raise SCQOSRuntimeEvidenceError(
                reason="identity_origin_class_invalid"
            )

        normalized_actor_type = _normalize_required_text(
            actor_type,
            reason="identity_actor_type_required",
        ).lower()

        normalized_session_id = _normalize_required_text(
            session_id,
            reason="identity_session_id_required",
        )

        normalized_principal_reference = (
            _normalize_required_text(
                principal_reference,
                reason="identity_principal_reference_required",
            )
        )

        object.__setattr__(
            self,
            "origin_class",
            normalized_origin,
        )
        object.__setattr__(
            self,
            "actor_type",
            normalized_actor_type,
        )
        object.__setattr__(
            self,
            "session_id",
            normalized_session_id,
        )
        object.__setattr__(
            self,
            "principal_reference",
            normalized_principal_reference,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "authenticated_subject": self.authenticated_subject,
            "origin_class": self.origin_class,
            "actor_type": self.actor_type,
            "session_id": self.session_id,
            "principal_reference": self.principal_reference,
        }

def _normalize_reference_sequence(
    value: Sequence[str] | None,
    *,
    reason: str,
) -> tuple[str, ...]:
    if value is None:
        return ()

    if isinstance(value, (str, bytes)) or not isinstance(
        value,
        Sequence,
    ):
        raise SCQOSRuntimeEvidenceError(
            reason=reason
        )

    normalized: list[str] = []

    for reference in value:
        normalized_reference = _normalize_required_text(
            reference,
            reason=reason,
        )

        if normalized_reference not in normalized:
            normalized.append(normalized_reference)

    return tuple(normalized)

@dataclass(frozen=True, init=False)
class ContinuityRequirementEvidence:
    """
    Record the server-side determination of whether this transition
    depends on state established before the current request.

    This records the continuity requirement and its basis. It does not
    prove that any required references resolved correctly; Reference and
    Alignment evaluate those separate questions.
    """

    inherited_state_required: bool
    requirement_status: str
    requirement_bases: tuple[str, ...]
    determination_source: str

    def __init__(
        self,
        *,
        inherited_state_required: bool,
        requirement_status: str,
        requirement_bases: Sequence[str] | None,
        determination_source: str,
    ) -> None:
        normalized_status = _normalize_required_text(
            requirement_status,
            reason="continuity_requirement_status_required",
        ).lower()

        if normalized_status not in _ALLOWED_CONTINUITY_REQUIREMENT_STATUSES:
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_requirement_status_invalid"
            )
            
        if not isinstance(inherited_state_required, bool):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_required_must_be_boolean"
            )
        
        if (
            normalized_status == "required"
            and inherited_state_required is not True
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_requirement_status_inconsistent"
            )

        if (
            normalized_status == "not_required"
            and inherited_state_required is not False
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_requirement_status_inconsistent"
            )

        if (
            normalized_status == "unresolved"
            and inherited_state_required is not True
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_requirement_status_inconsistent"
            )

        normalized_bases = _normalize_reference_sequence(
            requirement_bases,
            reason="continuity_requirement_basis_invalid",
        )

        if any(
            basis not in _ALLOWED_CONTINUITY_REQUIREMENT_BASES
            for basis in normalized_bases
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_requirement_basis_invalid"
            )

        if inherited_state_required:
            if not normalized_bases:
                raise SCQOSRuntimeEvidenceError(
                    reason="continuity_requirement_basis_required"
                )

            if "no_inherited_state_dependency" in normalized_bases:
                raise SCQOSRuntimeEvidenceError(
                    reason="continuity_requirement_basis_inconsistent"
                )

        elif normalized_bases != (
            "no_inherited_state_dependency",
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_requirement_basis_inconsistent"
            )

        normalized_source = _normalize_required_text(
            determination_source,
            reason="continuity_determination_source_required",
        ).lower()

        if (
            normalized_source
            not in _ALLOWED_CONTINUITY_DETERMINATION_SOURCES
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="continuity_determination_source_invalid"
            )

        object.__setattr__(
            self,
            "inherited_state_required",
            inherited_state_required,
        )
        object.__setattr__(
            self,
            "requirement_status",
            normalized_status,
        )
        object.__setattr__(
            self,
            "requirement_bases",
            normalized_bases,
        )
        object.__setattr__(
            self,
            "determination_source",
            normalized_source,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "inherited_state_required": (
                self.inherited_state_required
            ),
            "requirement_status": self.requirement_status,
            "requirement_bases": self.requirement_bases,
            "determination_source": self.determination_source,
        }

def reference_content_digest(*, role: str, content: str) -> str:
    """Hash exact role/content strings; no stripping or semantic normalization."""
    if not isinstance(role, str) or not isinstance(content, str):
        raise SCQOSRuntimeEvidenceError(reason="reference_content_invalid")
    payload = json.dumps([role, content], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_content_bindings(bindings) -> tuple[tuple[str, str], ...]:
    if bindings is None:
        return ()
    if isinstance(bindings, (str, bytes)) or not isinstance(bindings, Sequence):
        raise SCQOSRuntimeEvidenceError(reason="reference_content_bindings_invalid")
    result = []
    for item in bindings:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise SCQOSRuntimeEvidenceError(reason="reference_content_binding_invalid")
        reference, digest = item
        if not isinstance(reference, str) or not reference.strip() or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SCQOSRuntimeEvidenceError(reason="reference_content_binding_invalid")
        result.append((reference, digest))
    return tuple(result)


@dataclass(frozen=True, init=False)
class ReferenceResolutionEvidence:
    """
    Record which persistent references were requested and which
    actually resolved at the runtime evidence boundary.

    This records requested/resolved IDs plus deterministic role/content
    bindings for the source data admitted into the runtime evidence path.
    The Reference invariant determines what those facts prove.
    """

    required: bool
    requested_references: tuple[str, ...]
    resolved_references: tuple[str, ...]
    consumed_content_digests: tuple[tuple[str, str], ...]
    resolved_content_digests: tuple[tuple[str, str], ...]

    def __init__(
        self,
        *,
        required: bool,
        requested_references: Sequence[str] | None = None,
        resolved_references: Sequence[str] | None = None,
        consumed_content_digests: Sequence[tuple[str, str]] | None = None,
        resolved_content_digests: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        if not isinstance(required, bool):
            raise SCQOSRuntimeEvidenceError(
                reason="reference_required_must_be_boolean"
            )

        object.__setattr__(
            self,
            "required",
            required,
        )
        object.__setattr__(
            self,
            "requested_references",
            _normalize_reference_sequence(
                requested_references,
                reason="requested_reference_invalid",
            ),
        )
        object.__setattr__(
            self,
            "resolved_references",
            _normalize_reference_sequence(
                resolved_references,
                reason="resolved_reference_invalid",
            ),
        )

        object.__setattr__(self, "consumed_content_digests", _normalize_content_bindings(consumed_content_digests))
        object.__setattr__(self, "resolved_content_digests", _normalize_content_bindings(resolved_content_digests))

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "requested_references": self.requested_references,
            "resolved_references": self.resolved_references,
            "consumed_content_digests": self.consumed_content_digests,
            "resolved_content_digests": self.resolved_content_digests,
        }

def execution_request_digest(request: dict) -> str:
    """Commit the server-selected invocation arguments before dispatch."""
    return hashlib.sha256(json.dumps(
        request, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionObservation:
    """Local dispatch/result observation, never deserialized from request/model data.

    The selected model is an ordinary Bedrock Scout profile or a governed
    routing mode; governed service internals and provider identity are not
    attested here.
    """

    transition_id: str
    model_backend: str
    selected_model: str
    request_digest: str
    returned_text_digest: str
    consequence_digest: str
    transformation: str = "hard_filter_reply_v1"

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            value = getattr(self, field)
            if not isinstance(value, str) or not value or value != value.strip():
                raise SCQOSRuntimeEvidenceError(reason=f"execution_observation_{field}_invalid")
        if self.model_backend not in _ALLOWED_MODEL_BACKENDS:
            raise SCQOSRuntimeEvidenceError(reason="execution_observation_backend_invalid")
        for field in ("request_digest", "returned_text_digest", "consequence_digest"):
            if not re.fullmatch(r"[0-9a-f]{64}", getattr(self, field)):
                raise SCQOSRuntimeEvidenceError(reason=f"execution_observation_{field}_invalid")
        if self.transformation != "hard_filter_reply_v1":
            raise SCQOSRuntimeEvidenceError(reason="execution_observation_transformation_invalid")

    def to_contract_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, init=False)
class ModelExecutionEvidence:
    """
    Record what actually happened during model execution.

    Upstream receipts and identifiers are evidence candidates only.
    Their presence here does not prove that their lineage is valid.

    upstream_response_released means the governed upstream service released
    a candidate back to this orchestrator. It does not mean the candidate was
    released to the end user; final chat release is recorded by TransitionReceipt.
    """

    observation: ExecutionObservation | None
    model_backend: str
    succeeded: bool
    status: str
    error_reason: str | None
    submitted_transition_id: str
    produced_consequence_digest: str | None
    returned_transition_id: str | None
    request_id: str | None
    upstream_response_released: bool | None
    decision_receipt_id: str | None
    release_receipt_id: str | None
    consequence_receipt_id: str | None
    evidence_record_id: str | None
    http_status: int | None

    def __init__(
        self,
        *,
        model_backend: str,
        observation: ExecutionObservation | None = None,
        succeeded: bool,
        status: str,
        submitted_transition_id: str,
        produced_consequence_digest: str | None = None,
        error_reason: str | None = None,
        returned_transition_id: str | None = None,
        request_id: str | None = None,
        upstream_response_released: bool | None = None,
        decision_receipt_id: str | None = None,
        release_receipt_id: str | None = None,
        consequence_receipt_id: str | None = None,
        evidence_record_id: str | None = None,
        http_status: int | None = None,
    ) -> None:
        if observation is not None and not isinstance(observation, ExecutionObservation):
            raise SCQOSRuntimeEvidenceError(reason="execution_observation_invalid")
        object.__setattr__(self, "observation", observation)
        normalized_backend = _normalize_required_text(
            model_backend,
            reason="execution_model_backend_required",
        ).lower()

        if normalized_backend not in _ALLOWED_MODEL_BACKENDS:
            raise SCQOSRuntimeEvidenceError(
                reason="execution_model_backend_invalid"
            )

        if not isinstance(succeeded, bool):
            raise SCQOSRuntimeEvidenceError(
                reason="execution_succeeded_must_be_boolean"
            )

        normalized_status = _normalize_required_text(
            status,
            reason="execution_status_required",
        )

        normalized_error_reason = _normalize_optional_text(
            error_reason,
            reason="execution_error_reason_invalid",
        )

        if not succeeded and normalized_error_reason is None:
            raise SCQOSRuntimeEvidenceError(
                reason="failed_execution_requires_error_reason"
            )

        normalized_submitted_transition_id = (
            _normalize_required_text(
                submitted_transition_id,
                reason="submitted_transition_id_required",
            )
        )

        normalized_produced_consequence_digest = (
            _normalize_optional_text(
                produced_consequence_digest,
                reason="produced_consequence_digest_invalid",
            )
        )

        if (
            succeeded
            and normalized_produced_consequence_digest is None
        ):
            raise SCQOSRuntimeEvidenceError(
                reason=(
                    "successful_execution_requires_"
                    "produced_consequence_digest"
                )
            )

        if (
            upstream_response_released is not None
            and not isinstance(
                upstream_response_released,
                bool,
            )
        ):
            raise SCQOSRuntimeEvidenceError(
                reason=(
                    "upstream_response_released_"
                    "must_be_boolean_or_none"
                )
            )

        if http_status is not None and (
            not isinstance(http_status, int)
            or isinstance(http_status, bool)
            or http_status <= 0
        ):
            raise SCQOSRuntimeEvidenceError(
                reason="http_status_must_be_positive_integer_or_none"
            )

        object.__setattr__(
            self,
            "model_backend",
            normalized_backend,
        )
        object.__setattr__(
            self,
            "succeeded",
            succeeded,
        )
        object.__setattr__(
            self,
            "status",
            normalized_status,
        )
        object.__setattr__(
            self,
            "error_reason",
            normalized_error_reason,
        )
        object.__setattr__(
            self,
            "submitted_transition_id",
            normalized_submitted_transition_id,
        )
        object.__setattr__(
            self,
            "produced_consequence_digest",
            normalized_produced_consequence_digest,
        )
        object.__setattr__(
            self,
            "returned_transition_id",
            _normalize_optional_text(
                returned_transition_id,
                reason="returned_transition_id_invalid",
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_optional_text(
                request_id,
                reason="request_id_invalid",
            ),
        )
        object.__setattr__(
            self,
            "upstream_response_released",
            upstream_response_released,
        )
        object.__setattr__(
            self,
            "decision_receipt_id",
            _normalize_optional_text(
                decision_receipt_id,
                reason="decision_receipt_id_invalid",
            ),
        )
        object.__setattr__(
            self,
            "release_receipt_id",
            _normalize_optional_text(
                release_receipt_id,
                reason="release_receipt_id_invalid",
            ),
        )
        object.__setattr__(
            self,
            "consequence_receipt_id",
            _normalize_optional_text(
                consequence_receipt_id,
                reason="consequence_receipt_id_invalid",
            ),
        )
        object.__setattr__(
            self,
            "evidence_record_id",
            _normalize_optional_text(
                evidence_record_id,
                reason="evidence_record_id_invalid",
            ),
        )
        object.__setattr__(
            self,
            "http_status",
            http_status,
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation.to_contract_dict() if self.observation else None,
            "model_backend": self.model_backend,
            "succeeded": self.succeeded,
            "status": self.status,
            "error_reason": self.error_reason,
            "submitted_transition_id": (
                self.submitted_transition_id
            ),
            "produced_consequence_digest": (
                self.produced_consequence_digest
            ),
            "returned_transition_id": (
                self.returned_transition_id
            ),
            "request_id": self.request_id,
            "upstream_response_released": (
                self.upstream_response_released
            ),
            "decision_receipt_id": self.decision_receipt_id,
            "release_receipt_id": self.release_receipt_id,
            "consequence_receipt_id": (
                self.consequence_receipt_id
            ),
            "evidence_record_id": self.evidence_record_id,
            "http_status": self.http_status,
        }


@dataclass(frozen=True, init=False)
class TypedConsequenceProductionEvidenceV1:
    """Prove local production of one exact non-chat typed consequence."""

    CONTRACT_VERSION = "typed_consequence_production_v1"

    transition_id: str
    request_id: str
    consequence_type: str
    producer_id: str
    request_digest: str
    produced_consequence_digest: str
    status: str

    def __init__(
        self,
        *,
        transition_id: str,
        request_id: str,
        consequence_type: str,
        producer_id: str,
        request_digest: str,
        produced_consequence_digest: str,
        status: str = "PRODUCED",
    ) -> None:
        object.__setattr__(
            self,
            "transition_id",
            _normalize_required_text(
                transition_id,
                reason="typed_production_transition_id_required",
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_required_text(
                request_id,
                reason="typed_production_request_id_required",
            ),
        )
        object.__setattr__(
            self,
            "consequence_type",
            _normalize_required_text(
                consequence_type,
                reason="typed_production_consequence_type_required",
            ),
        )
        object.__setattr__(
            self,
            "producer_id",
            _normalize_required_text(
                producer_id,
                reason="typed_production_producer_id_required",
            ),
        )
        for field_name, value in (
            ("request_digest", request_digest),
            ("produced_consequence_digest", produced_consequence_digest),
        ):
            normalized = _normalize_required_text(
                value,
                reason=f"typed_production_{field_name}_required",
            )
            if not re.fullmatch(r"[0-9a-f]{64}", normalized):
                raise SCQOSRuntimeEvidenceError(
                    reason=f"typed_production_{field_name}_invalid"
                )
            object.__setattr__(self, field_name, normalized)

        normalized_status = _normalize_required_text(
            status,
            reason="typed_production_status_required",
        ).upper()
        if normalized_status != "PRODUCED":
            raise SCQOSRuntimeEvidenceError(
                reason="typed_production_status_invalid"
            )
        object.__setattr__(self, "status", normalized_status)

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.CONTRACT_VERSION,
            "transition_id": self.transition_id,
            "request_id": self.request_id,
            "consequence_type": self.consequence_type,
            "producer_id": self.producer_id,
            "request_digest": self.request_digest,
            "produced_consequence_digest": (
                self.produced_consequence_digest
            ),
            "status": self.status,
        }


@dataclass(frozen=True)
class BoundaryReleaseEvidence:
    """Server-selected release admission facts, not proof of delivery or confinement."""

    transition_id: str
    consequence_type: str
    boundary: str
    release_operation: str
    release_destination: str
    release_consequence_digest: str

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            object.__setattr__(self, field, _normalize_required_text(
                getattr(self, field), reason=f"boundary_{field}_required",
            ))

    def to_contract_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True)
class SCQOSRuntimeEvidence:
    """
    Complete runtime evidence supplied to transition evaluation.

    This object carries facts. The eight-invariant evaluator determines
    what those facts prove.
    """

    temporal: TemporalEvidence
    continuity: ContinuityRequirementEvidence
    identity: IdentityProvenanceEvidence
    references: ReferenceResolutionEvidence
    execution: ModelExecutionEvidence | TypedConsequenceProductionEvidenceV1
    boundary: BoundaryReleaseEvidence

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "contract_version": SCQOS_RUNTIME_EVIDENCE_VERSION,
            "temporal": self.temporal.to_contract_dict(),
            "continuity": self.continuity.to_contract_dict(),
            "identity": self.identity.to_contract_dict(),
            "references": self.references.to_contract_dict(),
            "execution": self.execution.to_contract_dict(),
            "boundary": self.boundary.to_contract_dict(),
        }

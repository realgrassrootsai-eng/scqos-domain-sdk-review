"""Semantic binding between proposed consequences and authoritative SCQOS evidence."""

from __future__ import annotations

import re

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class SemanticEvidenceBindingResult:
    """
    Release-admission result for one proposed natural-language consequence.

    This is not a ninth SCQOS invariant.

    The eight invariants establish authoritative runtime truth.
    Semantic Evidence Binding determines whether the proposed consequence
    contradicts that already-established truth before release.
    """

    passed: bool
    reason: str
    checked_claims: tuple[str, ...]
    conflicting_claims: tuple[str, ...]
    evidence_references: tuple[str, ...]

    def __init__(
        self,
        *,
        passed: bool,
        reason: str,
        checked_claims: Sequence[str] | None = None,
        conflicting_claims: Sequence[str] | None = None,
        evidence_references: Sequence[str] | None = None,
    ) -> None:
        if not isinstance(passed, bool):
            raise ValueError(
                "semantic_binding_passed_must_be_boolean"
            )

        normalized_reason = str(reason or "").strip()

        if not normalized_reason:
            raise ValueError(
                "semantic_binding_reason_required"
            )

        normalized_checked_claims = tuple(
            str(item).strip()
            for item in (checked_claims or ())
            if str(item).strip()
        )

        normalized_conflicting_claims = tuple(
            str(item).strip()
            for item in (conflicting_claims or ())
            if str(item).strip()
        )

        normalized_evidence_references = tuple(
            str(item).strip()
            for item in (evidence_references or ())
            if str(item).strip()
        )

        if passed and normalized_conflicting_claims:
            raise ValueError(
                "semantic_binding_pass_cannot_have_conflicts"
            )

        if not passed and not normalized_conflicting_claims:
            raise ValueError(
                "semantic_binding_failure_requires_conflict"
            )

        object.__setattr__(
            self,
            "passed",
            passed,
        )

        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )

        object.__setattr__(
            self,
            "checked_claims",
            normalized_checked_claims,
        )

        object.__setattr__(
            self,
            "conflicting_claims",
            normalized_conflicting_claims,
        )

        object.__setattr__(
            self,
            "evidence_references",
            normalized_evidence_references,
        )


def _normalize_iso_timestamp(
    value: str | None,
) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()

    if not normalized:
        return None

    if normalized.endswith(("Z", "z")):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return None

    return (
        parsed.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def evaluate_semantic_evidence_binding(
    *,
    user_message: str,
    proposed_consequence: str,
    proposal,
    runtime_evidence,
) -> SemanticEvidenceBindingResult:
    """
    Compare governed semantic claims in a proposed consequence against
    authoritative evidence already established for the transition.

    Claim interpretation may use the current user message because a terse
    proposed consequence can inherit its semantic meaning from the request.

    This function does not evaluate the eight SCQOS invariants themselves.
    """

    checked_claims: list[str] = []
    conflicting_claims: list[str] = []
    evidence_references: list[str] = []

    # ------------------------------------------------------------
    # CAUSALITY
    # ------------------------------------------------------------

    digest_pattern = re.compile(
        r"\bproduced_consequence_digest\s*=\s*"
        r"([0-9a-fA-F]{64})\b"
    )

    digest_matches = digest_pattern.findall(
        proposed_consequence or ""
    )

    if digest_matches:
        authoritative_digest = (
            runtime_evidence.execution.produced_consequence_digest
        )

        evidence_reference = (
            "runtime:causality:produced_consequence_digest"
        )

        evidence_references.append(
            evidence_reference
        )

        for claimed_digest in digest_matches:
            checked_claim = (
                "produced_consequence_digest="
                f"{claimed_digest}"
            )

            checked_claims.append(
                checked_claim
            )

            if (
                authoritative_digest is None
                or claimed_digest.lower()
                != authoritative_digest.lower()
            ):
                conflicting_claims.append(
                    checked_claim
                )

    # ------------------------------------------------------------
    # REFERENCE
    # ------------------------------------------------------------

    resolved_reference_pattern = re.compile(
        r"\b(memory:\d+)\s+is\s+(?:a\s+)?"
        r"resolved\s+persistent\s+reference\b",
        re.IGNORECASE,
    )

    resolved_reference_matches = (
        resolved_reference_pattern.findall(
            proposed_consequence or ""
        )
    )

    if resolved_reference_matches:
        authoritative_resolved_references = set(
            runtime_evidence.references.resolved_references
        )

        evidence_reference = (
            "runtime:reference:resolved_references"
        )

        evidence_references.append(
            evidence_reference
        )

        for claimed_reference in resolved_reference_matches:
            checked_claim = (
                f"{claimed_reference} is a resolved "
                "persistent reference"
            )

            checked_claims.append(
                checked_claim
            )

            if (
                claimed_reference
                not in authoritative_resolved_references
            ):
                conflicting_claims.append(
                    checked_claim
                )

    # ------------------------------------------------------------
    # COHERENCE
    # ------------------------------------------------------------

    coherent_ids_pattern = re.compile(
        r"\brequest_id\s*=\s*([A-Za-z0-9._:-]+)"
        r"\s+(?:and|,)\s+"
        r"transition_id\s*=\s*([A-Za-z0-9._:-]+)"
        r"\s+(?:form|forms|constitute|constitutes)\s+"
        r"(?:the\s+|a\s+)?coherent\s+proof\s+chain\b",
        re.IGNORECASE,
    )

    coherent_id_matches = coherent_ids_pattern.findall(
        proposed_consequence or ""
    )

    if coherent_id_matches:
        evidence_references.extend(
            (
                "proposal:coherence:request_id",
                "proposal:coherence:transition_id",
            )
        )

        for (
            claimed_request_id,
            claimed_transition_id,
        ) in coherent_id_matches:
            checked_claim = (
                f"request_id={claimed_request_id} and "
                f"transition_id={claimed_transition_id} "
                "form the coherent proof chain"
            )

            checked_claims.append(
                checked_claim
            )

            if (
                claimed_request_id
                != proposal.request_id
                or claimed_transition_id
                != proposal.transition_id
            ):
                conflicting_claims.append(
                    checked_claim
                )

    # ------------------------------------------------------------
    # BOUNDARY
    # ------------------------------------------------------------

    boundary_claim_pattern = re.compile(
        r"\b([A-Za-z0-9._:-]+)\s+is\s+authorized\s+for\s+"
        r"([A-Za-z0-9._:-]+)\b",
        re.IGNORECASE,
    )

    boundary_claim_matches = boundary_claim_pattern.findall(
        proposed_consequence or ""
    )

    for (
        claimed_consequence,
        claimed_boundary,
    ) in boundary_claim_matches:
        if (
            "_" not in claimed_consequence
            and "_" not in claimed_boundary
        ):
            continue

        checked_claim = (
            f"{claimed_consequence} is authorized for "
            f"{claimed_boundary}"
        )

        checked_claims.append(
            checked_claim
        )

        evidence_references.append(
            "proposal:boundary:authorization"
        )

        if (
            claimed_consequence.lower()
            != proposal.consequence_type.lower()
            or claimed_boundary.lower()
            != proposal.boundary.lower()
        ):
            conflicting_claims.append(
                checked_claim
            )

    # ------------------------------------------------------------
    # GENESIS
    # ------------------------------------------------------------

    runtime_origin_pattern = re.compile(
        r"\b([A-Za-z][A-Za-z0-9_-]*)\s*:\s*"
        r"([A-Za-z0-9._:@-]+)\s+is\s+"
        r"(?:the\s+)?authoritative\s+runtime\s+origin\b",
        re.IGNORECASE,
    )

    runtime_origin_matches = runtime_origin_pattern.findall(
        proposed_consequence or ""
    )

    if runtime_origin_matches:
        identity_evidence = (
            runtime_evidence.identity
        )

        authoritative_principals = {
            identity_evidence.session_id.lower(),
            identity_evidence.principal_reference.lower(),
        }

        if ":" in identity_evidence.principal_reference:
            authoritative_principals.add(
                identity_evidence.principal_reference
                .rsplit(":", 1)[-1]
                .lower()
            )

        evidence_references.extend(
            (
                "runtime:genesis:origin_class",
                "runtime:genesis:actor_type",
                "runtime:genesis:principal_reference",
            )
        )

        for (
            claimed_actor_type,
            claimed_principal,
        ) in runtime_origin_matches:
            checked_claim = (
                f"{claimed_actor_type}: {claimed_principal} "
                "is authoritative runtime origin"
            )

            checked_claims.append(
                checked_claim
            )

            actor_matches = (
                claimed_actor_type.lower()
                == identity_evidence.actor_type.lower()
            )

            principal_matches = (
                claimed_principal.lower()
                in authoritative_principals
            )

            if (
                not actor_matches
                or not principal_matches
            ):
                conflicting_claims.append(
                    checked_claim
                )

    # ------------------------------------------------------------
    # TIME
    #
    # A timestamp only becomes a governed runtime-time claim when
    # the request or response identifies it as authoritative
    # runtime/server time.
    # ------------------------------------------------------------

    runtime_time_context_pattern = re.compile(
        r"\b(?:"
        r"authoritative\s+runtime\s+(?:time|timestamp)"
        r"|runtime\s+(?:time|timestamp)"
        r"|server\s+(?:time|timestamp)"
        r")\b",
        re.IGNORECASE,
    )

    iso_timestamp_pattern = re.compile(
        r"\b"
        r"\d{4}-\d{2}-\d{2}"
        r"T"
        r"\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?"
        r"(?:Z|[+-]\d{2}:\d{2})"
        r"\b",
        re.IGNORECASE,
    )

    time_claim_context = (
        runtime_time_context_pattern.search(
            user_message or ""
        )
        or runtime_time_context_pattern.search(
            proposed_consequence or ""
        )
    )

    if time_claim_context:
        claimed_timestamps = (
            iso_timestamp_pattern.findall(
                proposed_consequence or ""
            )
        )

        if claimed_timestamps:
            authoritative_timestamp = (
                runtime_evidence.temporal.runtime_observed_at
            )

            normalized_authoritative_timestamp = (
                _normalize_iso_timestamp(
                    authoritative_timestamp
                )
            )

            evidence_references.append(
                "runtime:time:runtime_observed_at"
            )

            for claimed_timestamp in claimed_timestamps:
                checked_claim = (
                    "authoritative runtime time="
                    f"{claimed_timestamp}"
                )

                checked_claims.append(
                    checked_claim
                )

                normalized_claimed_timestamp = (
                    _normalize_iso_timestamp(
                        claimed_timestamp
                    )
                )

                if (
                    normalized_claimed_timestamp is None
                    or normalized_authoritative_timestamp is None
                    or normalized_claimed_timestamp
                    != normalized_authoritative_timestamp
                ):
                    conflicting_claims.append(
                        checked_claim
                    )

    # ------------------------------------------------------------
    # RELEASE ADMISSION
    # ------------------------------------------------------------

    if conflicting_claims:
        return SemanticEvidenceBindingResult(
            passed=False,
            reason="semantic_evidence_conflict",
            checked_claims=checked_claims,
            conflicting_claims=conflicting_claims,
            evidence_references=evidence_references,
        )

    return SemanticEvidenceBindingResult(
        passed=True,
        reason="no_semantic_evidence_conflict_detected",
        checked_claims=checked_claims,
        evidence_references=evidence_references,
    )

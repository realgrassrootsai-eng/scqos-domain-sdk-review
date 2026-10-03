"""Constitution v1 authority-lineage contracts.

These contracts prove structural continuity from the SCQOS authority root to
the authority exercised now. They do not authenticate evidence or issue
permission merely because a lineage is well formed.
"""

from dataclasses import dataclass
from typing import Any

from constitutional_binding import (
    ConstitutionalBindingV1,
    ConstitutionalContractError,
    _Contract,
    _canonical_time,
    _digest,
    _ref,
    _require,
)


@dataclass(frozen=True)
class AuthorityLineageStepV1(_Contract):
    """One explicit predecessor/successor authority baton binding."""

    VERSION = "authority_lineage_step_v1"

    sequence: int
    step_id: str
    predecessor_authority_id: str
    predecessor_authority_digest: str
    successor_authority_id: str
    successor_authority_digest: str
    baton_evidence_reference: str
    baton_evidence_digest: str
    effective_at: str

    def __post_init__(self) -> None:
        _require(type(self) is AuthorityLineageStepV1, "exact_contract_type_required")
        _require(type(self.sequence) is int and self.sequence > 0, "lineage_sequence_invalid")
        for value, code in (
            (self.step_id, "lineage_step_id_invalid"),
            (self.predecessor_authority_id, "predecessor_authority_id_invalid"),
            (self.successor_authority_id, "successor_authority_id_invalid"),
            (self.baton_evidence_reference, "baton_evidence_reference_invalid"),
        ):
            _ref(value, code)
        _digest(self.predecessor_authority_digest, "predecessor_authority_digest_invalid")
        _digest(self.successor_authority_digest, "successor_authority_digest_invalid")
        _digest(self.baton_evidence_digest, "baton_evidence_digest_invalid")
        _canonical_time(self.effective_at, "lineage_effective_at_invalid")
        _require(
            (
                self.predecessor_authority_id,
                self.predecessor_authority_digest,
            )
            != (
                self.successor_authority_id,
                self.successor_authority_digest,
            ),
            "authority_self_transfer_invalid",
        )


@dataclass(frozen=True)
class AuthorityLineageV1(_Contract):
    """Unbroken governed lineage from SCQOS root to current authority."""

    VERSION = "authority_lineage_v1"

    lineage_id: str
    constitution_digest: str
    constitutional_binding_digest: str
    authority_root_id: str
    authority_root_digest: str
    authority_policy_digest: str
    current_authority_id: str
    current_authority_digest: str
    steps: tuple[AuthorityLineageStepV1, ...]
    established_at: str

    def __post_init__(self) -> None:
        _require(type(self) is AuthorityLineageV1, "exact_contract_type_required")
        for value, code in (
            (self.lineage_id, "lineage_id_invalid"),
            (self.authority_root_id, "authority_root_id_invalid"),
            (self.current_authority_id, "current_authority_id_invalid"),
        ):
            _ref(value, code)
        for value, code in (
            (self.constitution_digest, "constitution_digest_invalid"),
            (self.constitutional_binding_digest, "constitutional_binding_digest_invalid"),
            (self.authority_root_digest, "authority_root_digest_invalid"),
            (self.authority_policy_digest, "authority_policy_digest_invalid"),
            (self.current_authority_digest, "current_authority_digest_invalid"),
        ):
            _digest(value, code)
        established = _canonical_time(self.established_at, "lineage_established_at_invalid")
        _require(
            type(self.steps) is tuple
            and bool(self.steps)
            and all(type(step) is AuthorityLineageStepV1 for step in self.steps),
            "authority_lineage_steps_required",
        )

        expected_sequence = tuple(range(1, len(self.steps) + 1))
        actual_sequence = tuple(step.sequence for step in self.steps)
        _require(actual_sequence == expected_sequence, "authority_lineage_sequence_gap")

        first = self.steps[0]
        _require(
            (
                first.predecessor_authority_id,
                first.predecessor_authority_digest,
            )
            == (self.authority_root_id, self.authority_root_digest),
            "authority_lineage_root_mismatch",
        )

        seen_step_ids: set[str] = set()
        seen_authorities: set[tuple[str, str]] = {
            (self.authority_root_id, self.authority_root_digest)
        }
        previous_effective = None
        previous = None
        for step in self.steps:
            _require(step.step_id not in seen_step_ids, "duplicate_lineage_step_id")
            seen_step_ids.add(step.step_id)
            successor = (step.successor_authority_id, step.successor_authority_digest)
            _require(successor not in seen_authorities, "authority_lineage_cycle_or_replay")
            seen_authorities.add(successor)
            effective = _canonical_time(step.effective_at, "lineage_effective_at_invalid")
            _require(effective <= established, "lineage_step_after_establishment")
            if previous_effective is not None:
                _require(previous_effective <= effective, "authority_lineage_time_reordered")
            if previous is not None:
                _require(
                    (
                        step.predecessor_authority_id,
                        step.predecessor_authority_digest,
                    )
                    == (
                        previous.successor_authority_id,
                        previous.successor_authority_digest,
                    ),
                    "authority_lineage_predecessor_gap",
                )
            previous_effective = effective
            previous = step

        last = self.steps[-1]
        _require(
            (last.successor_authority_id, last.successor_authority_digest)
            == (self.current_authority_id, self.current_authority_digest),
            "authority_lineage_current_endpoint_mismatch",
        )


def validate_lineage_for_constitutional_binding(
    binding: ConstitutionalBindingV1,
    lineage: AuthorityLineageV1,
) -> None:
    """Bind an authority lineage to the exact active Constitution binding."""

    _require(type(binding) is ConstitutionalBindingV1, "constitutional_binding_required")
    _require(type(lineage) is AuthorityLineageV1, "authority_lineage_required")
    artifact = binding.artifact
    _require(lineage.lineage_id == artifact.lineage_id, "lineage_id_mismatch")
    _require(
        lineage.constitution_digest == artifact.constitution_digest,
        "lineage_constitution_digest_mismatch",
    )
    _require(
        lineage.constitutional_binding_digest == binding.digest,
        "lineage_constitutional_binding_mismatch",
    )
    _require(
        lineage.authority_root_digest == artifact.authority_root_digest,
        "lineage_authority_root_mismatch",
    )
    _require(
        lineage.authority_policy_digest == artifact.authority_policy_digest,
        "lineage_authority_policy_mismatch",
    )

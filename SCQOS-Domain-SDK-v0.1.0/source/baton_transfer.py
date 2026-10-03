"""Constitution v1 authority-baton transfer contracts.

A baton transfer proves structural continuity from one already-qualified
authority lineage to an explicitly extended successor lineage. Supplied durable
evidence references are claims; this module does not authenticate them or grant
permission merely because the contract is well formed.
"""

from dataclasses import dataclass

from authority_lineage import AuthorityLineageV1
from constitutional_binding import (
    _Contract,
    _canonical_time,
    _digest,
    _ref,
    _require,
)


@dataclass(frozen=True)
class BatonTransferV1(_Contract):
    """One explicit, durable handoff from current authority to its successor."""

    VERSION = "baton_transfer_v1"

    transfer_id: str
    constitutional_binding_digest: str
    predecessor_lineage_digest: str
    successor_lineage_digest: str
    predecessor_authority_id: str
    predecessor_authority_digest: str
    successor_authority_id: str
    successor_authority_digest: str
    triggering_change_digest: str
    lineage_step_digest: str
    approval_evidence_reference: str
    approval_evidence_digest: str
    verification_evidence_reference: str
    verification_evidence_digest: str
    effective_at: str
    verified_at: str

    def __post_init__(self) -> None:
        _require(type(self) is BatonTransferV1, "exact_contract_type_required")
        for value, code in (
            (self.transfer_id, "baton_transfer_id_invalid"),
            (self.predecessor_authority_id, "baton_predecessor_authority_id_invalid"),
            (self.successor_authority_id, "baton_successor_authority_id_invalid"),
            (self.approval_evidence_reference, "baton_approval_reference_invalid"),
            (self.verification_evidence_reference, "baton_verification_reference_invalid"),
        ):
            _ref(value, code)
        for value, code in (
            (self.constitutional_binding_digest, "baton_constitutional_binding_digest_invalid"),
            (self.predecessor_lineage_digest, "baton_predecessor_lineage_digest_invalid"),
            (self.successor_lineage_digest, "baton_successor_lineage_digest_invalid"),
            (self.predecessor_authority_digest, "baton_predecessor_authority_digest_invalid"),
            (self.successor_authority_digest, "baton_successor_authority_digest_invalid"),
            (self.triggering_change_digest, "baton_triggering_change_digest_invalid"),
            (self.lineage_step_digest, "baton_lineage_step_digest_invalid"),
            (self.approval_evidence_digest, "baton_approval_digest_invalid"),
            (self.verification_evidence_digest, "baton_verification_digest_invalid"),
        ):
            _digest(value, code)
        effective = _canonical_time(self.effective_at, "baton_effective_at_invalid")
        verified = _canonical_time(self.verified_at, "baton_verified_at_invalid")
        _require(effective <= verified, "baton_verified_before_effective")
        _require(
            (self.predecessor_authority_id, self.predecessor_authority_digest)
            != (self.successor_authority_id, self.successor_authority_digest),
            "baton_self_transfer_invalid",
        )


def validate_baton_transfer(
    predecessor: AuthorityLineageV1,
    successor: AuthorityLineageV1,
    transfer: BatonTransferV1,
) -> None:
    """Require a literal one-step lineage extension; never infer a handoff."""

    _require(type(predecessor) is AuthorityLineageV1, "predecessor_lineage_required")
    _require(type(successor) is AuthorityLineageV1, "successor_lineage_required")
    _require(type(transfer) is BatonTransferV1, "baton_transfer_required")

    _require(predecessor.lineage_id == successor.lineage_id, "baton_lineage_id_mismatch")
    _require(
        predecessor.constitution_digest == successor.constitution_digest,
        "baton_constitution_digest_mismatch",
    )
    _require(
        predecessor.constitutional_binding_digest
        == successor.constitutional_binding_digest
        == transfer.constitutional_binding_digest,
        "baton_constitutional_binding_mismatch",
    )
    _require(
        (predecessor.authority_root_id, predecessor.authority_root_digest)
        == (successor.authority_root_id, successor.authority_root_digest),
        "baton_authority_root_mismatch",
    )
    _require(
        predecessor.authority_policy_digest == successor.authority_policy_digest,
        "baton_policy_change_requires_new_constitutional_binding",
    )
    _require(
        len(successor.steps) == len(predecessor.steps) + 1
        and successor.steps[:-1] == predecessor.steps,
        "baton_successor_must_extend_predecessor_by_one_step",
    )

    step = successor.steps[-1]
    _require(
        (step.predecessor_authority_id, step.predecessor_authority_digest)
        == (predecessor.current_authority_id, predecessor.current_authority_digest),
        "baton_lineage_step_predecessor_mismatch",
    )
    _require(
        (step.successor_authority_id, step.successor_authority_digest)
        == (successor.current_authority_id, successor.current_authority_digest),
        "baton_lineage_step_successor_mismatch",
    )
    _require(
        transfer.predecessor_lineage_digest == predecessor.digest
        and transfer.successor_lineage_digest == successor.digest,
        "baton_lineage_digest_mismatch",
    )
    _require(
        (transfer.predecessor_authority_id, transfer.predecessor_authority_digest)
        == (predecessor.current_authority_id, predecessor.current_authority_digest),
        "baton_predecessor_authority_mismatch",
    )
    _require(
        (transfer.successor_authority_id, transfer.successor_authority_digest)
        == (successor.current_authority_id, successor.current_authority_digest),
        "baton_successor_authority_mismatch",
    )
    _require(transfer.lineage_step_digest == step.digest, "baton_lineage_step_digest_mismatch")
    _require(
        _canonical_time(step.effective_at, "lineage_effective_at_invalid")
        == _canonical_time(transfer.effective_at, "baton_effective_at_invalid"),
        "baton_effective_time_mismatch",
    )

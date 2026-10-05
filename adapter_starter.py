"""Adapter starter: fail-closed implementation of all six DomainAdapter operations."""
from typing import Any, Callable
from scqos_domain_sdk import PreparedTransition, DomainAdapter

class AdapterStarter(DomainAdapter):
    def read_authoritative_state(self) -> dict:
        raise NotImplementedError("Read an authoritative snapshot with a freshness/version marker; return a copy.")

    def normalize_proposal(self, request: Any, before: dict, authority: Any) -> PreparedTransition:
        raise NotImplementedError("Validate exact request types; bind request, before and expected_after to the exact kernel proposal.")

    def collect_authority(self, authority: Any) -> Any:
        raise NotImplementedError("Resolve authority against a trusted issuer or registry; do not treat caller assertions as approval.")

    def evaluate_domain_predicates(self, request: Any, prepared: PreparedTransition, authority: Any, current: dict) -> tuple[str,...]:
        raise NotImplementedError("Check scope, expiry, replay, current state and domain constraints; return failure codes.")

    def execute_consequence(self, request: Any, prepared: PreparedTransition, authority: Any, mark_invoked: Callable[[], None]) -> bool:
        raise NotImplementedError("Atomically repeat guards, consume approval and mutate; mark_invoked immediately before writer invocation.")

    def verify_consequence(self, prepared: PreparedTransition, observed: dict) -> bool:
        raise NotImplementedError("Compare independent observed state with the bound expected result; never assume a write succeeded.")

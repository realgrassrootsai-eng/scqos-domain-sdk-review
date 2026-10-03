"""Deterministic JSON contract encoding; not a signature or RFC 8785 JCS."""

import hashlib
import json
from typing import Any


def canonical_contract_json(payload: Any) -> str:
    """Encode JSON values and tuple sequences without coercing object keys.

    List order, strings and numeric representation remain significant. Callers
    must include their contract version in the payload. No default=str escape.
    """
    def check(value: Any) -> None:
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("contract_object_keys_must_be_strings")
            for item in value.values():
                check(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check(item)
        elif value is not None and type(value) not in (str, bool, int, float):
            raise TypeError("contract_value_not_json")

    check(payload)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def contract_digest(payload: Any) -> str:
    """Return a lowercase SHA-256 hex digest of canonical UTF-8 JSON."""
    return hashlib.sha256(canonical_contract_json(payload).encode("utf-8")).hexdigest()

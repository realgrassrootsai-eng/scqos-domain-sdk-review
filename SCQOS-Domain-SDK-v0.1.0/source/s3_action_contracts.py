"""Typed contract for the isolated governed S3 object-action lab."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
import hashlib
from typing import Any, Sequence

from scqos_contract_digest import contract_digest


class S3ActionContractError(ValueError):
    pass


class S3ObjectOperation(str, Enum):
    PUT_OBJECT = "PUT_OBJECT"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise S3ActionContractError(reason)


def _text(value: Any, reason: str) -> str:
    _require(
        type(value) is str
        and bool(value)
        and value == value.strip(),
        reason,
    )
    return value


def _references(
    value: Sequence[str] | None,
    reason: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    _require(
        not isinstance(value, (str, bytes))
        and isinstance(value, Sequence),
        reason,
    )
    result = []
    for item in value:
        normalized = _text(item, reason)
        _require(normalized not in result, reason)
        result.append(normalized)
    return tuple(result)


@dataclass(frozen=True)
class S3PutObjectActionV1:
    VERSION = "s3_put_object_action_v1"

    transition_id: str
    actor_id: str
    operation: S3ObjectOperation
    bucket_name: str
    object_key: str
    content_type: str
    body_utf8: str
    evidence_refs: tuple[str, ...]
    authorization_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        transition_id: str,
        actor_id: str,
        operation: S3ObjectOperation,
        bucket_name: str,
        object_key: str,
        content_type: str,
        body_utf8: str,
        evidence_refs: Sequence[str] | None = None,
        authorization_refs: Sequence[str] | None = None,
    ) -> None:
        _require(
            type(self) is S3PutObjectActionV1,
            "exact_s3_put_object_action_v1_required",
        )
        _require(
            type(operation) is S3ObjectOperation,
            "s3_object_operation_invalid",
        )
        transition_id = _text(
            transition_id,
            "s3_transition_id_invalid",
        )
        actor_id = _text(actor_id, "s3_actor_id_invalid")
        bucket_name = _text(
            bucket_name,
            "s3_bucket_name_invalid",
        )
        object_key = _text(
            object_key,
            "s3_object_key_invalid",
        )
        content_type = _text(
            content_type,
            "s3_content_type_invalid",
        )
        _require(
            type(body_utf8) is str and bool(body_utf8),
            "s3_body_utf8_invalid",
        )
        _require(
            not object_key.startswith("/")
            and ".." not in object_key.split("/"),
            "s3_object_key_invalid",
        )

        object.__setattr__(self, "transition_id", transition_id)
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "bucket_name", bucket_name)
        object.__setattr__(self, "object_key", object_key)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "body_utf8", body_utf8)
        object.__setattr__(
            self,
            "evidence_refs",
            _references(evidence_refs, "s3_evidence_ref_invalid"),
        )
        object.__setattr__(
            self,
            "authorization_refs",
            _references(
                authorization_refs,
                "s3_authorization_ref_invalid",
            ),
        )

    def to_contract_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.VERSION,
            **{
                field.name: (
                    getattr(self, field.name).value
                    if isinstance(getattr(self, field.name), Enum)
                    else list(getattr(self, field.name))
                    if type(getattr(self, field.name)) is tuple
                    else getattr(self, field.name)
                )
                for field in fields(self)
            },
        }

    @property
    def action_digest(self) -> str:
        return contract_digest(self.to_contract_dict())

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(
            self.body_utf8.encode("utf-8")
        ).hexdigest()

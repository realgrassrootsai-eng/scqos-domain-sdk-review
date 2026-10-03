"""Temporal validation primitives for SCQOS."""

from __future__ import annotations

import datetime


_ALLOWED_CLOCK_SKEW = datetime.timedelta(
    seconds=5
)


def capture_runtime_observation_timestamp() -> str:
    """
    Capture the authoritative current UTC time from the runtime clock.
    """

    return (
        datetime.datetime.now(
            datetime.timezone.utc
        )
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_observation_timestamp(
    value: str | None,
) -> tuple[str | None, str]:
    """
    Parse and normalize a complete timezone-aware ISO-8601 timestamp.

    This function establishes syntactic and timezone validity only.
    It does not determine whether the timestamp is temporally
    admissible relative to an authoritative clock or observation.
    """

    if value is None:
        return None, "missing"

    if not isinstance(value, str):
        return None, "invalid_format"

    raw_value = value.strip()

    if not raw_value:
        return None, "missing"

    try:
        normalized_input = (
            raw_value[:-1] + "+00:00"
            if raw_value.endswith("Z")
            else raw_value
        )

        parsed_time = datetime.datetime.fromisoformat(
            normalized_input
        )

        if (
            "T" not in raw_value
            or parsed_time.tzinfo is None
        ):
            return None, "invalid_format"

        parsed_time = parsed_time.astimezone(
            datetime.timezone.utc
        )

        return (
            parsed_time.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "accepted",
        )

    except (TypeError, ValueError):
        return None, "invalid_format"


def validate_observation_timestamp(
    value: str | None,
) -> tuple[str | None, str]:
    """
    Accept a complete ISO-8601 observation timestamp only when it is
    timezone-aware, valid, and not materially later than the current
    UTC server time.

    This function is intended for validation against the live runtime
    clock. Replay comparisons should instead use a bound authoritative
    observation as their reference.

    Returns:
        (normalized_timestamp, validation_status)
    """

    normalized_timestamp, status = (
        normalize_observation_timestamp(
            value
        )
    )

    if status != "accepted":
        return None, status

    parsed_time = datetime.datetime.fromisoformat(
        normalized_timestamp.replace(
            "Z",
            "+00:00",
        )
    )

    current_utc = datetime.datetime.now(
        datetime.timezone.utc
    )

    if parsed_time > (
        current_utc + _ALLOWED_CLOCK_SKEW
    ):
        return None, "rejected_future_timestamp"

    return normalized_timestamp, "accepted"


def validate_observation_timestamp_against_reference(
    value: str | None,
    *,
    reference_timestamp: str,
) -> tuple[str | None, str]:
    """
    Validate one timestamp relative to a bound authoritative timestamp.

    Unlike live-clock validation, this comparison is deterministic:
    the same value and reference produce the same result regardless
    of when verification is repeated.
    """

    normalized_timestamp, status = (
        normalize_observation_timestamp(
            value
        )
    )

    if status != "accepted":
        return None, status

    normalized_reference, reference_status = (
        normalize_observation_timestamp(
            reference_timestamp
        )
    )

    if reference_status != "accepted":
        return None, "invalid_reference_timestamp"

    parsed_time = datetime.datetime.fromisoformat(
        normalized_timestamp.replace(
            "Z",
            "+00:00",
        )
    )

    parsed_reference = datetime.datetime.fromisoformat(
        normalized_reference.replace(
            "Z",
            "+00:00",
        )
    )

    if parsed_time > (
        parsed_reference + _ALLOWED_CLOCK_SKEW
    ):
        return None, "rejected_future_timestamp"

    return normalized_timestamp, "accepted"

from collections.abc import Mapping
from typing import Any

from member3_validate.enums import SeverityEnum
from member3_validate.schema import ValidatedLogEvent
from member3_validate.timestamp import parse_hdfs_timestamp


def get_field(source: Any, field_name: str, default: Any = None) -> Any:
    """
    Read a field from either a dataclass/object or a dictionary.

    This lets Member 3 work with:
    - Event objects from shared.interfaces
    - dictionaries in tests
    """

    if isinstance(source, Mapping):
        return source.get(field_name, default)

    return getattr(source, field_name, default)


def normalize_severity(severity: object) -> SeverityEnum:
    """
    Convert raw severity into a safe SeverityEnum.
    """

    if not isinstance(severity, str) or not severity.strip():
        return SeverityEnum.UNKNOWN

    normalized = severity.upper().strip()

    try:
        return SeverityEnum(normalized)
    except ValueError:
        return SeverityEnum.UNKNOWN


def apply_severity_mismatch_policy(
    severity: SeverityEnum,
    severity_mismatch: bool
) -> SeverityEnum:
    """
    If Member 2 says the regex severity does not match the message,
    safely escalate weak severity to WARN.

    Example:
    Regex says INFO, but message says "Database connection failed".
    Final severity becomes WARN.
    """

    if not severity_mismatch:
        return severity

    if severity in {
        SeverityEnum.DEBUG,
        SeverityEnum.INFO,
        SeverityEnum.UNKNOWN,
    }:
        return SeverityEnum.WARN

    return severity


def clean_service_name(service_name: object) -> str:
    """
    Make sure service_name is always a non-empty string.
    """

    if isinstance(service_name, str) and service_name.strip():
        return service_name.strip()

    return "unknown"


def clean_remediation(remediation: object) -> str:
    """
    Make sure suggested_remediation is always a non-empty string.
    """

    if isinstance(remediation, str) and remediation.strip():
        return remediation.strip()

    return "investigation_required"


def build_validated_event(event_from_m1: Any, llm_from_m2: Mapping[str, object]) -> ValidatedLogEvent:
    """
    Combine Member 1 output and Member 2 output into one validated object.

    Member 1 gives an Event with:
        raw_text
        line_number
        service_name
        raw_timestamp
        severity
        message

    Member 2 gives:
        suggested_remediation
        severity_mismatch

    Member 3 returns:
        ValidatedLogEvent
    """

    raw_timestamp = get_field(event_from_m1, "raw_timestamp", "")

    if not isinstance(raw_timestamp, str):
        raw_timestamp = ""

    parsed_timestamp, timestamp_fallback_used = parse_hdfs_timestamp(raw_timestamp)

    raw_severity = get_field(event_from_m1, "severity", "UNKNOWN")
    severity = normalize_severity(raw_severity)

    severity_mismatch = llm_from_m2.get("severity_mismatch", False)

    if not isinstance(severity_mismatch, bool):
        severity_mismatch = False

    final_severity = apply_severity_mismatch_policy(
        severity=severity,
        severity_mismatch=severity_mismatch
    )

    validated_event = ValidatedLogEvent(
        service_name=clean_service_name(get_field(event_from_m1, "service_name", "unknown")),
        timestamp=parsed_timestamp,
        error_severity=final_severity,
        suggested_remediation=clean_remediation(
            llm_from_m2.get("suggested_remediation")
        ),
        timestamp_fallback_used=timestamp_fallback_used,
        severity_mismatch=severity_mismatch
    )

    return validated_event


def to_final_output(validated_event: ValidatedLogEvent) -> dict:
    """
    Return only the final JSON fields needed by Member 4.
    """

    return {
        "service_name": validated_event.service_name,
        "timestamp": validated_event.timestamp.isoformat(),
        "error_severity": validated_event.error_severity.value,
        "suggested_remediation": validated_event.suggested_remediation
    }


def validate_event_for_output(event_from_m1: Any, llm_from_m2: Mapping[str, object]) -> dict:
    """
    Main function for Member 4 to call.

    Input:
        Event from Member 1
        LLM result from Member 2

    Output:
        Final JSON-ready dictionary
    """

    validated_event = build_validated_event(event_from_m1, llm_from_m2)
    return to_final_output(validated_event)
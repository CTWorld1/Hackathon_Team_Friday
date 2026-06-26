"""Assemble + validate the final event from regex (M1) and LLM (M2) fields.

This is where "syntactically perfect JSON" is enforced (via the pydantic model in
:mod:`schema`). The validator:

- maps M1's raw severity token onto the :class:`SeverityEnum` (unknown -> UNKNOWN),
- parses M1's ``raw_timestamp`` to a real ``datetime`` (with safe fallback),
- applies the severity-mismatch policy from M2 (escalate to at least WARN),
- defaults a missing/blank remediation to ``investigation_required``,
- validates the assembled object against the schema.

Inputs are plain dicts: ``event_from_m1`` is a :class:`~shared.interfaces.Event`,
``llm_from_m2`` is the ``{suggested_remediation, severity_mismatch}`` payload.
"""

from member3_validate.enums import SeverityEnum
from member3_validate.schema import ValidatedLogEvent
from member3_validate.timestamp import parse_hdfs_timestamp

#: Tolerant aliases for severity tokens that aren't exact enum members.
_SEVERITY_ALIASES = {
    "WARNING": "WARN",
    "ERR": "ERROR",
    "CRIT": "CRITICAL",
    "FATAL ERROR": "FATAL",
}

#: Ordering used by the mismatch policy. UNKNOWN sits low so a flagged mismatch
#: escalates it to WARN, matching the "don't trust the regex level" intent.
_SEVERITY_RANK = {
    SeverityEnum.DEBUG: 0,
    SeverityEnum.INFO: 1,
    SeverityEnum.UNKNOWN: 1,
    SeverityEnum.WARN: 2,
    SeverityEnum.ERROR: 3,
    SeverityEnum.CRITICAL: 4,
    SeverityEnum.FATAL: 5,
}


def _coerce_severity(raw):
    """Map a raw severity token onto SeverityEnum; unknown/blank -> UNKNOWN."""
    if not raw:
        return SeverityEnum.UNKNOWN
    token = str(raw).strip().upper()
    token = _SEVERITY_ALIASES.get(token, token)
    try:
        return SeverityEnum(token)
    except ValueError:
        return SeverityEnum.UNKNOWN


def _apply_mismatch_policy(severity, mismatch):
    """If M2 flagged a mismatch, escalate anything below WARN up to WARN."""
    if mismatch and _SEVERITY_RANK.get(severity, 1) < _SEVERITY_RANK[SeverityEnum.WARN]:
        return SeverityEnum.WARN
    return severity


def build_validated_event(event_from_m1, llm_from_m2):
    """Assemble + validate a :class:`ValidatedLogEvent` from M1 + M2 fields.

    Raises ``pydantic.ValidationError`` if the assembled object is invalid (the
    caller — Member 4 — catches this to repair/retry or dead-letter).
    """
    service_name = (event_from_m1.get("service_name") or "").strip() or "unknown"

    timestamp, fallback_used = parse_hdfs_timestamp(event_from_m1.get("raw_timestamp", ""))

    mismatch = bool(llm_from_m2.get("severity_mismatch", False))
    severity = _apply_mismatch_policy(_coerce_severity(event_from_m1.get("severity")), mismatch)

    remediation = llm_from_m2.get("suggested_remediation")
    if not isinstance(remediation, str) or not remediation.strip():
        remediation = "investigation_required"

    return ValidatedLogEvent(
        service_name=service_name,
        timestamp=timestamp,
        error_severity=severity,
        suggested_remediation=remediation.strip(),
        timestamp_fallback_used=fallback_used,
        severity_mismatch=mismatch,
    )


def to_final_output(validated):
    """Reduce a validated event to the M3 -> M4 contract (exactly four keys)."""
    return {
        "service_name": validated.service_name,
        "timestamp": validated.timestamp.isoformat(),
        "error_severity": validated.error_severity.value,
        "suggested_remediation": validated.suggested_remediation,
    }


def validate_event_for_output(event_from_m1, llm_from_m2):
    """Convenience: assemble, validate, and reduce to the final output dict."""
    return to_final_output(build_validated_event(event_from_m1, llm_from_m2))

"""Event -> {suggested_remediation, severity_mismatch}.

The LLM is asked only for a remediation + a yes/no ``is_failure`` (see
:mod:`prompt`). ``severity_mismatch`` is then computed deterministically here:

    mismatch = is_failure AND the regex severity is under-labeled (INFO/DEBUG/
               UNKNOWN/empty)

i.e. the model says the text describes a failure, but the upstream label was too
low. For WARN/ERROR/FATAL/CRITICAL the label already reflects the severity, so
mismatch is always False — no 2B-model guesswork, no false positives.

The external contract returned to Member 3 is unchanged:
``{suggested_remediation, severity_mismatch}``. Stateless: one event in, one dict
out, no history.
"""

import logging

from shared.interfaces import Event
from member2_llm.client import chat_json
from member2_llm.prompt import build_remediation_messages

logger = logging.getLogger(__name__)

#: Severity labels that are "too low" — a detected failure under one of these is a
#: mismatch that Member 3 escalates (to at least WARN).
UNDER_LABELED = {"", "INFO", "DEBUG", "UNKNOWN"}

#: External fallback (pipeline contract shape) used when the LLM layer can't run.
FALLBACK = {
    "suggested_remediation": "investigation_required",
    "severity_mismatch": False,
}


def _compute_mismatch(is_failure, severity) -> bool:
    """True only when a detected failure sits under an INFO/DEBUG/UNKNOWN label."""
    return bool(is_failure) and (severity or "").strip().upper() in UNDER_LABELED


def remediate(message: str, severity: str) -> dict:
    """Return ``{suggested_remediation, severity_mismatch}`` for one event.

    Stateless: sends only the current message to the model, then derives the
    mismatch flag from the model's ``is_failure`` and the given severity.
    """
    payload = chat_json(build_remediation_messages(message))
    return {
        "suggested_remediation": payload["suggested_remediation"],
        "severity_mismatch": _compute_mismatch(payload.get("is_failure", False), severity),
    }


def remediate_event(event: Event) -> dict:
    """Remediate a Member 1 Event (a TypedDict / plain dict at runtime)."""
    message = event.get("message") or event.get("raw_text") or ""
    severity = event.get("severity") or ""
    return remediate(message, severity)


def remediate_or_fallback(event: Event) -> dict:
    try:
        return remediate_event(event)
    except Exception as exc:  # keep the pipeline alive if the LLM layer fails
        logger.warning("[remediate] falling back for line %s: %s",
                       event.get("line_number") if hasattr(event, "get") else "?", exc)
        return dict(FALLBACK)

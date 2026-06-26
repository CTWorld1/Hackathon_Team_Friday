import logging

from shared.interfaces import Event
from member2_llm.client import FALLBACK, chat_json
from member2_llm.prompt import build_remediation_messages

logger = logging.getLogger(__name__)


def remediate(message: str, severity: str) -> dict:
	"""Return the LLM remediation payload for one log event message.

	The function is stateless and sends only the current message plus severity.
	"""

	messages = build_remediation_messages(message=message, severity=severity)
	return chat_json(messages)


def remediate_event(event: Event) -> dict:
	"""Remediate a Member 1 Event.

	``Event`` is a TypedDict (a plain ``dict`` at runtime), so fields are read with
	dict access. Falls back to ``raw_text`` when ``message`` is empty.
	"""
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

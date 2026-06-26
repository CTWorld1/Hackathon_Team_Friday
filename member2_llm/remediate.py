from collections.abc import Mapping

from member2_llm.client import FALLBACK, chat_json
from member2_llm.prompt import build_remediation_messages


def _extract_message_and_severity(event: Mapping[str, object]) -> tuple[str, str]:
	message = event.get("message")
	if not isinstance(message, str) or not message.strip():
		message = event.get("raw_text")

	severity = event.get("severity")

	if not isinstance(message, str) or not message.strip():
		raise ValueError("event must include a non-empty message or raw_text field")

	if not isinstance(severity, str) or not severity.strip():
		raise ValueError("event must include a non-empty severity field")

	return message.strip(), severity.strip()


def remediate(message: str, severity: str) -> dict:
	"""Return the LLM remediation payload for one log event message.

	The function is stateless and sends only the current message plus severity.
	"""

	messages = build_remediation_messages(message=message, severity=severity)
	return chat_json(messages)


def remediate_event(event: Mapping[str, object]) -> dict:
	message, severity = _extract_message_and_severity(event)
	return remediate(message, severity)


def remediate_or_fallback(event: Mapping[str, object]) -> dict:
	try:
		return remediate_event(event)
	except Exception:
		return dict(FALLBACK)

from shared.interfaces import Event
from member2_llm.client import FALLBACK, chat_json
from member2_llm.prompt import build_remediation_messages


def remediate(message: str, severity: str) -> dict:
	"""Return the LLM remediation payload for one log event message.

	The function is stateless and sends only the current message plus severity.
	"""

	messages = build_remediation_messages(message=message, severity=severity)
	return chat_json(messages)


def remediate_event(event: Event) -> dict:
	return remediate(event.message, event.severity)


def remediate_or_fallback(event: Event) -> dict:
	try:
		return remediate_event(event)
	except Exception:
		return dict(FALLBACK)

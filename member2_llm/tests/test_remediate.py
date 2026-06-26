from shared.interfaces import Event

import member2_llm.remediate as remediate_module


def test_remediate_event_uses_event_message_and_severity(monkeypatch):
    captured = {}

    def fake_chat_json(messages):
        captured["messages"] = messages
        return {
            "suggested_remediation": "Investigate the database connection failure.",
            "severity_mismatch": True,
        }

    monkeypatch.setattr(remediate_module, "chat_json", fake_chat_json)

    event = Event(
        raw_text="INFO Database connection failed after 3 retries",
        line_number=1,
        service_name="db.service",
        raw_timestamp="250626 120000",
        severity="INFO",
        message="Database connection failed after 3 retries",
    )

    result = remediate_module.remediate_event(event)

    assert result == {
        "suggested_remediation": "Investigate the database connection failure.",
        "severity_mismatch": True,
    }
    assert captured["messages"][-1]["role"] == "user"
    assert "Regex-derived severity: INFO" in captured["messages"][-1]["content"]


def test_remediate_or_fallback_returns_fallback_on_failure(monkeypatch):
    def fake_chat_json(messages):
        raise ValueError("bad output")

    monkeypatch.setattr(remediate_module, "chat_json", fake_chat_json)

    event = Event(
        raw_text="INFO Service status report received from node worker-04",
        line_number=2,
        service_name="worker.service",
        raw_timestamp="250626 120001",
        severity="INFO",
        message="Service status report received from node worker-04",
    )

    assert remediate_module.remediate_or_fallback(event) == remediate_module.FALLBACK
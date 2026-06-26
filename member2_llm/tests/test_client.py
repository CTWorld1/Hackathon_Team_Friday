import member2_llm.client as client


def test_chat_json_parses_code_fenced_json(monkeypatch):
    def fake_chat(**kwargs):
        assert kwargs["model"] == client.MODEL
        assert kwargs["format"] == "json"
        assert kwargs["options"]["temperature"] == 0
        return {
            "message": {
                "content": "```json\n{\"suggested_remediation\": \"Restart the service.\", \"severity_mismatch\": false}\n```"
            }
        }

    monkeypatch.setattr(client.ollama, "chat", fake_chat)

    result = client.chat_json([{"role": "user", "content": "test"}])

    assert result == {
        "suggested_remediation": "Restart the service.",
        "severity_mismatch": False,
    }


def test_chat_json_returns_fallback_for_invalid_payload(monkeypatch):
    def fake_chat(**kwargs):
        return {
            "message": {
                "content": "{\"suggested_remediation\": \"\", \"severity_mismatch\": \"no\"}"
            }
        }

    monkeypatch.setattr(client.ollama, "chat", fake_chat)

    result = client.chat_json([{"role": "user", "content": "test"}], retries=1)

    assert result == client.FALLBACK


def test_chat_json_returns_fallback_on_exception(monkeypatch):
    def fake_chat(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(client.ollama, "chat", fake_chat)

    result = client.chat_json([{"role": "user", "content": "test"}], retries=1)

    assert result == client.FALLBACK
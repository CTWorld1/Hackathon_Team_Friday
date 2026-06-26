from member2_llm.prompt import build_remediation_messages


def test_build_remediation_messages_uses_expected_contract():
    messages = build_remediation_messages(
        "Database connection failed after 3 retries",
        "INFO",
    )

    assert len(messages) == 8
    assert messages[0]["role"] == "system"
    assert "Severity labels are DEBUG, INFO, WARN, ERROR, and FATAL." in messages[0]["content"]

    assert messages[-1] == {
        "role": "user",
        "content": "Log message: Database connection failed after 3 retries\nRegex-derived severity: INFO",
    }

    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"
    assert messages[4]["role"] == "assistant"
    assert messages[5]["role"] == "user"
    assert messages[6]["role"] == "assistant"
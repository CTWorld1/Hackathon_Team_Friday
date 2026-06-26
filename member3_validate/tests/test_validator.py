from member3_validate.validator import (
    build_validated_event,
    to_final_output,
    validate_event_for_output,
)


def test_build_validated_event():
    event_from_m1 = {
        "raw_text": "081109 204900 700 ERROR dfs.DataNode: IOException while receiving block",
        "line_number": 13,
        "service_name": "dfs.DataNode",
        "raw_timestamp": "081109 204900",
        "severity": "ERROR",
        "message": "IOException while receiving block"
    }

    llm_from_m2 = {
        "suggested_remediation": "Check DataNode network connectivity.",
        "severity_mismatch": False
    }

    validated = build_validated_event(event_from_m1, llm_from_m2)
    output = to_final_output(validated)

    assert output["service_name"] == "dfs.DataNode"
    assert output["timestamp"] == "2008-11-09T20:49:00"
    assert output["error_severity"] == "ERROR"
    assert output["suggested_remediation"] == "Check DataNode network connectivity."


def test_validate_event_for_output():
    event_from_m1 = {
        "raw_text": "081109 204900 700 ERROR dfs.DataNode: IOException while receiving block",
        "line_number": 13,
        "service_name": "dfs.DataNode",
        "raw_timestamp": "081109 204900",
        "severity": "ERROR",
        "message": "IOException while receiving block"
    }

    llm_from_m2 = {
        "suggested_remediation": "Check DataNode network connectivity.",
        "severity_mismatch": False
    }

    output = validate_event_for_output(event_from_m1, llm_from_m2)

    assert output == {
        "service_name": "dfs.DataNode",
        "timestamp": "2008-11-09T20:49:00",
        "error_severity": "ERROR",
        "suggested_remediation": "Check DataNode network connectivity."
    }


def test_severity_mismatch_escalates_info_to_warn():
    event_from_m1 = {
        "raw_text": "081109 204900 700 INFO dfs.DataNode: IOException while receiving block",
        "line_number": 13,
        "service_name": "dfs.DataNode",
        "raw_timestamp": "081109 204900",
        "severity": "INFO",
        "message": "IOException while receiving block"
    }

    llm_from_m2 = {
        "suggested_remediation": "Investigate the IOException.",
        "severity_mismatch": True
    }

    output = validate_event_for_output(event_from_m1, llm_from_m2)

    assert output["error_severity"] == "WARN"


def test_missing_remediation_falls_back():
    event_from_m1 = {
        "raw_text": "081109 204900 700 ERROR dfs.DataNode: IOException while receiving block",
        "line_number": 13,
        "service_name": "dfs.DataNode",
        "raw_timestamp": "081109 204900",
        "severity": "ERROR",
        "message": "IOException while receiving block"
    }

    llm_from_m2 = {
        "severity_mismatch": False
    }

    output = validate_event_for_output(event_from_m1, llm_from_m2)

    assert output["suggested_remediation"] == "investigation_required"


def test_bad_severity_becomes_unknown():
    event_from_m1 = {
        "raw_text": "081109 204900 700 BAD dfs.DataNode: Something happened",
        "line_number": 13,
        "service_name": "dfs.DataNode",
        "raw_timestamp": "081109 204900",
        "severity": "BAD",
        "message": "Something happened"
    }

    llm_from_m2 = {
        "suggested_remediation": "investigation_required",
        "severity_mismatch": False
    }

    output = validate_event_for_output(event_from_m1, llm_from_m2)

    assert output["error_severity"] == "UNKNOWN"

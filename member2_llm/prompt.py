SYSTEM_PROMPT = """You are a stateless log triage tool.
You receive one log message and one regex-derived severity label.
You do not remember previous messages.
Return ONLY a valid JSON object with exactly two keys:
    "suggested_remediation": one short sentence grounded in the message text
    "severity_mismatch": true only when the message text contradicts the given severity label
Severity labels are DEBUG, INFO, WARN, ERROR, and FATAL.
If the message is ambiguous, keep severity_mismatch false.
If you cannot infer a remediation from the message, use investigation_required.
No explanation. No markdown. No extra text."""

FEW_SHOT_EXAMPLES = [
    {
                "message": "INFO Heartbeat received from node worker-04",
                "severity": "INFO",
                "output": '{"suggested_remediation": "No action required; this is a routine heartbeat event.", "severity_mismatch": false}'
    },
    {
                "message": "WARN Disk usage at 91% on /dev/sda1, threshold is 90%",
                "severity": "WARN",
                "output": '{"suggested_remediation": "Free disk space on /dev/sda1 or expand storage.", "severity_mismatch": false}'
    },
    {
                "message": "INFO Database connection failed after 3 retries",
                "severity": "INFO",
                "output": '{"suggested_remediation": "Investigate the database connection failure and retry path.", "severity_mismatch": true}'
    }
]

def build_remediation_messages(message: str, severity: str) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example in FEW_SHOT_EXAMPLES:
        user_turn = f"Log message: {example['message']}\nRegex-derived severity: {example['severity']}"
        messages.append({"role": "user", "content": user_turn})
        messages.append({"role": "assistant", "content": example["output"]})
    user_query = f"Log message: {message}\nRegex-derived severity: {severity}"
    messages.append({"role": "user", "content": user_query})
    return messages
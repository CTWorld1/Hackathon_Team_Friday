"""Prompt templates for the remediation + failure-detection step.

Format-agnostic by design: the model reasons over an abstract log message, so it
works across log sources (HDFS, Hadoop, Linux, HPC, syslog, app logs).

The model is asked ONLY for two things it does well, even at 2B:
  - a one-sentence remediation grounded in the message, and
  - a simple yes/no "is this a failure?".

It is deliberately NOT asked to compare the message against a severity label — a
2B model is unreliable at that relative judgement. The ``severity_mismatch`` flag
is computed deterministically in code (see :mod:`remediate`) from ``is_failure``
plus the regex-derived severity.

Message shape: the ``message`` handed in is M1's extracted body (the level token is
already stripped into ``severity``), so the few-shot example messages omit the
leading level token to match real input.
"""

SYSTEM_PROMPT = """You are a stateless log triage tool.
You receive ONE log message. You do not remember previous messages.

Return ONLY a valid JSON object with exactly these two keys, and nothing else:
    "suggested_remediation": one short, actionable sentence grounded ONLY in the
        message text. If you cannot infer a remediation, use "investigation_required".
    "is_failure": true if the message describes a failure, error, exception, crash,
        corruption, timeout, or outage; false if it is benign, routine, purely
        informational, or a success.

No explanation. No markdown. No extra text."""

# Balanced: 3 benign + 3 failure, drawn from diverse log sources so failure
# detection generalizes rather than memorizing one format.
FEW_SHOT_EXAMPLES = [
    {
        # HDFS, benign
        "message": "PacketResponder 1 for block blk_38865049064139660 terminating",
        "output": '{"suggested_remediation": "No action required; this is a routine block lifecycle event.", "is_failure": false}',
    },
    {
        # app, failure
        "message": "Database connection failed after 3 retries",
        "output": '{"suggested_remediation": "Investigate the database connectivity and the retry path.", "is_failure": true}',
    },
    {
        # Linux, benign
        "message": "session opened for user cyrus by (uid=0)",
        "output": '{"suggested_remediation": "No action required; this is a routine session start.", "is_failure": false}',
    },
    {
        # HDFS, failure
        "message": "writeBlock received exception java.io.IOException: Connection reset by peer",
        "output": '{"suggested_remediation": "Investigate the peer connection that was reset and retry the transfer.", "is_failure": true}',
    },
    {
        # Hadoop, benign
        "message": "Created MRAppMaster for application appattempt_1445144423722_0020_000001",
        "output": '{"suggested_remediation": "No action required; this is a routine application start.", "is_failure": false}',
    },
    {
        # syslog/kernel, failure
        "message": "Out of memory: killed process 1234 (java)",
        "output": '{"suggested_remediation": "Increase the memory limit or fix the memory leak in the affected process.", "is_failure": true}',
    },
]


def build_remediation_messages(message: str) -> list[dict]:
    """Build the chat message list: system prompt + few-shot turns + the query.

    Message-only: the model never sees the severity label (the mismatch decision
    is made in code), which keeps its task to the simple yes/no it handles well.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": f"Log message: {example['message']}"})
        messages.append({"role": "assistant", "content": example["output"]})
    messages.append({"role": "user", "content": f"Log message: {message}"})
    return messages

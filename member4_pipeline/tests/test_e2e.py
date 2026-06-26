"""End-to-end pipeline test.

Exercises the real chain reader -> prefilter -> M1 parse -> M2 LLM -> M3 validate
-> M4 output. Per team decision the LLM is NOT mocked: this test calls the real
gemma2:2b via Ollama and is skipped when Ollama / the model is not available.
"""

import json

import pytest

from member4_pipeline import config
from member4_pipeline.deadletter import DeadLetterLog
from member4_pipeline.main import run_pipeline

REQUIRED_KEYS = {"service_name", "timestamp", "error_severity", "suggested_remediation"}

# A tiny multi-service log: 2 noise lines that must be filtered, 2 anomalies kept.
SAMPLE_LOG = """\
081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_1 terminating
081109 203807 222 INFO dfs.FSNamesystem: heartbeat received from node worker-04
081109 204900 700 ERROR dfs.DataNode: IOException while receiving block blk_2
081109 210000 512 WARN dfs.DataNode$DataXceiver: Got exception while serving blk_3 to peer
"""


def _ollama_ready(model=config.MODEL):
    """Return True only if Ollama is up and ``model`` is present."""
    try:
        import ollama
    except ImportError:
        return False
    try:
        listing = ollama.list()
    except Exception:
        return False
    models = getattr(listing, "models", None)
    if models is None and isinstance(listing, dict):
        models = listing.get("models", [])
    names = []
    for m in models or []:
        name = getattr(m, "model", None) or getattr(m, "name", None)
        if name is None and isinstance(m, dict):
            name = m.get("model") or m.get("name")
        if name:
            names.append(name)
    return any(model in n for n in names)


pytestmark = pytest.mark.skipif(
    not _ollama_ready(),
    reason="Ollama + {} not available; e2e needs a live model.".format(config.MODEL),
)


def test_e2e_produces_valid_ndjson(tmp_path):
    log_file = tmp_path / "in.log"
    log_file.write_text(SAMPLE_LOG)
    dead_letter = DeadLetterLog(tmp_path / "dead.ndjson")

    with dead_letter:
        records = list(run_pipeline(str(log_file), dead_letter))

    # The two anomaly lines survive the prefilter; the two INFO/heartbeat lines do not.
    assert len(records) == 2, records

    for record in records:
        assert set(record.keys()) == REQUIRED_KEYS
        # Each record is genuinely serializable as one webhook-ready JSON object.
        round_tripped = json.loads(json.dumps(record))
        assert round_tripped == record
        assert record["service_name"]
        assert record["suggested_remediation"]
        # Timestamps parsed to ISO 8601 by M3.
        assert record["timestamp"].startswith("2008-11-09T")

    severities = {r["error_severity"] for r in records}
    assert "ERROR" in severities

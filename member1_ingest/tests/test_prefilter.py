"""Tests for the pre-filter: reject noise, keep anomalies, default-KEEP."""

from member1_ingest.prefilter import should_keep, prefilter


def test_rejects_info_and_debug():
    assert should_keep("081109 203615 148 INFO dfs.DataNode: terminating") is False
    assert should_keep("081109 203615 148 DEBUG dfs.DataNode: tick") is False


def test_rejects_healthcheck_and_heartbeat():
    assert should_keep("200101 000000 1 INFO svc: healthcheck ok") is False
    assert should_keep("200101 000000 1 monitor: heartbeat") is False


def test_keeps_error_warn_fatal():
    assert should_keep("081109 210000 512 ERROR dfs.DataNode: boom") is True
    assert should_keep("081109 210000 512 WARN dfs.DataNode: slow") is True
    assert should_keep("081109 210000 512 FATAL dfs.NameNode: dead") is True
    assert should_keep("081109 210000 512 CRITICAL dfs.NameNode: dead") is True


def test_keep_keyword_overrides_reject():
    """INFO-tagged line whose body says Exception must still be KEPT."""
    line = "081109 210000 512 INFO dfs.DataNode: caught Exception while reading"
    assert should_keep(line) is True


def test_keeps_failure_keywords_regardless_of_level():
    assert should_keep("081109 210000 1 INFO svc: block is corrupt") is True
    assert should_keep("081109 210000 1 INFO svc: write failed") is True


def test_default_keep_on_ambiguous():
    """No known token either way -> keep (missing a crash is worse)."""
    assert should_keep("081109 210000 1 svc: some unfamiliar event") is True


def test_word_boundary_avoids_false_reject():
    """'information' contains 'info' but must not be rejected as INFO."""
    assert should_keep("081109 210000 1 svc: gathering information about peer") is True


def test_prefilter_stream_keeps_only_survivors():
    lines = [
        (1, "081109 203615 148 INFO dfs.DataNode: terminating"),      # reject
        (2, "081109 210000 512 ERROR dfs.DataNode: boom"),            # keep
        (3, "081109 210001 1 DEBUG svc: tick"),                       # reject
        (4, "081109 210002 1 INFO svc: caught Exception"),            # keep (override)
        (5, "081109 210003 1 svc: mystery event"),                   # keep (ambiguous)
    ]
    kept = list(prefilter(lines))
    assert [ln for ln, _ in kept] == [2, 4, 5]


def test_custom_keyword_lists_override_defaults():
    line = "081109 210000 1 NOTICE svc: please look"
    # Default: NOTICE is unknown -> ambiguous -> keep.
    assert should_keep(line) is True
    # Custom reject list flags NOTICE as noise.
    assert should_keep(line, reject_keywords=("NOTICE",)) is False

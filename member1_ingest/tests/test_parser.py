"""Tests for the deterministic parser, including the pid-is-not-timestamp trap."""

from shared.interfaces import Event
from member1_ingest.parser import parse_line, parse

# Canonical HDFS-style sample line (Docs/Group_Roles.md reference format).
SAMPLE = (
    "081109 203615 148 INFO dfs.DataNode$PacketResponder: "
    "PacketResponder 1 for block blk_38865049064139660 terminating"
)


def test_parses_all_fields():
    event = parse_line(7, SAMPLE)
    assert isinstance(event, Event)
    assert event.line_number == 7
    assert event.raw_text == SAMPLE
    assert event.service_name == "dfs.DataNode$PacketResponder"
    assert event.severity == "INFO"
    assert event.raw_timestamp == "081109 203615"
    assert event.message == (
        "PacketResponder 1 for block blk_38865049064139660 terminating"
    )


def test_pid_is_not_part_of_timestamp():
    """The #1 parsing bug: the pid (148) must NOT be folded into the timestamp."""
    event = parse_line(1, SAMPLE)
    # date + time only — exactly two tokens.
    assert event.raw_timestamp == "081109 203615"
    assert "148" not in event.raw_timestamp
    assert len(event.raw_timestamp.split()) == 2


def test_message_can_contain_colons():
    line = (
        "081109 204005 35 INFO dfs.FSNamesystem: BLOCK* NameSystem.addStoredBlock: "
        "blockMap updated: 10.251.73.220:50010 is added to blk_7128370237687728475"
    )
    event = parse_line(2, line)
    assert event.service_name == "dfs.FSNamesystem"
    assert event.raw_timestamp == "081109 204005"
    assert event.severity == "INFO"
    # component is split at the FIRST colon; the rest (with its colons) is message.
    assert event.message.startswith("BLOCK* NameSystem.addStoredBlock:")
    assert "10.251.73.220:50010" in event.message


def test_error_line_levels():
    line = "081109 210000 512 ERROR dfs.DataNode: connection to peer failed"
    event = parse_line(3, line)
    assert event.severity == "ERROR"
    assert event.service_name == "dfs.DataNode"
    assert event.message == "connection to peer failed"


def test_unmatched_line_is_not_dropped():
    """Non-matching lines flow through as 'unknown', never dropped."""
    junk = "this line does not match the expected log format at all"
    event = parse_line(99, junk)
    assert event.service_name == "unknown"
    assert event.raw_timestamp == ""
    assert event.severity == ""
    assert event.message == junk
    assert event.raw_text == junk
    assert event.line_number == 99


def test_parse_stream_preserves_order_and_count():
    lines = [
        (1, SAMPLE),
        (2, "garbage line"),
        (3, "081109 210000 512 ERROR dfs.DataNode: failed"),
    ]
    events = list(parse(lines))
    assert [e.line_number for e in events] == [1, 2, 3]
    assert events[0].severity == "INFO"
    assert events[1].service_name == "unknown"
    assert events[2].severity == "ERROR"

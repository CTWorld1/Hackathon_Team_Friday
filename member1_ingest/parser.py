"""Deterministic regex parsing — extracts 3 of the 4 fields, no LLM.

Turns ``(line_number, raw_text)`` tuples into :class:`~shared.interfaces.Event`
dicts. This is the hybrid design's fast path: the regex pulls ``service_name``,
``raw_timestamp`` and ``severity`` so the LLM only ever handles remediation.

Two non-negotiables (Docs/Group_Roles.md):
- The pid that follows the time is NEVER folded into ``raw_timestamp``. The
  pattern captures it in its own group precisely so it can be ignored here.
- A line that does not match the pattern is NOT dropped. It flows through with
  ``service_name="unknown"`` and the full line as its message.

Events are plain ``dict``s (typed as :class:`~shared.interfaces.Event`) so M2 and
M3 can consume them directly with dict access.
"""

from shared.interfaces import Event
from member1_ingest.patterns import DEFAULT_LOG_PATTERN


def parse_line(line_number, raw_text, pattern=DEFAULT_LOG_PATTERN):
    """Build an :class:`Event` dict from a single ``(line_number, raw_text)``.

    On a match: ``raw_timestamp`` is ``"<date> <time>"`` (pid excluded),
    ``service_name`` is the component, ``severity`` is the level token, and
    ``message`` is the body after the component's colon.

    On no match: ``service_name="unknown"``, ``raw_timestamp=""``,
    ``severity=""`` and ``message`` is the whole line — never dropped.
    """
    match = pattern.match(raw_text)
    if match is None:
        return Event(
            raw_text=raw_text,
            line_number=line_number,
            service_name="unknown",
            raw_timestamp="",
            severity="",
            message=raw_text,
        )

    groups = match.groupdict()
    # date + time ONLY. The pid (groups["pid"]) is intentionally discarded.
    raw_timestamp = "{date} {time}".format(date=groups["date"], time=groups["time"])
    return Event(
        raw_text=raw_text,
        line_number=line_number,
        service_name=groups["component"],
        raw_timestamp=raw_timestamp,
        severity=groups["level"],
        message=groups["message"],
    )


def parse(lines, pattern=DEFAULT_LOG_PATTERN):
    """Map a stream of ``(line_number, raw_text)`` tuples to ``Event`` dicts.

    Stays a generator so the reader -> prefilter -> parser chain remains
    streaming end to end.
    """
    for line_number, raw_text in lines:
        yield parse_line(line_number, raw_text, pattern=pattern)

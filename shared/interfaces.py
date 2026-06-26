"""Interface contracts shared between pipeline stages.

These are the seams every member codes against. Lock these shapes early; do not
change a field without telling the members on both sides of the seam.

Two shapes flow through the pipeline:

- ``Event``           — produced by Member 1 (ingest/parse), consumed by M2 (LLM)
                        and M3 (validation).
- ``ValidatedOutput`` — produced by Member 3 (validation), consumed by M4 (output).
                        Owned by Member 3; defined there when that work lands.

Reference pipeline flow (see Docs/Group_Roles.md)::

    reader -> prefilter -> parser  =>  Event  =>  LLM  =>  validate  =>  output
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """A single, independent log event produced by Member 1.

    One log line in, one ``Event`` out. Each event is self-contained — there is
    no cross-line state, which is what satisfies "each line treated
    independently, no interference."

    Fields (the M1 -> M2/M3 contract):
        raw_text:       the original log line, verbatim (newline stripped).
        line_number:    1-based position of the line in the source stream.
        service_name:   the component field (e.g. ``dfs.DataNode$PacketResponder``);
                        ``"unknown"`` when the line does not match the pattern.
        raw_timestamp:  date + time tokens ONLY (e.g. ``"081109 203615"``). The pid
                        that follows the time is deliberately NOT included here.
                        Member 3's ``timestamp.py`` parses this to ISO 8601.
        severity:       the raw level token (``INFO``/``WARN``/``ERROR``/...), as it
                        appeared in the line; ``""`` when unmatched.
        message:        the message body after the component's colon; falls back to
                        the full ``raw_text`` when the line does not match.
    """

    raw_text: str
    line_number: int
    service_name: str
    raw_timestamp: str
    severity: str
    message: str

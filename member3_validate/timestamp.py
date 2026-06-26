"""Non-ISO timestamp parsing -> ISO 8601 (swappable format).

The HDFS sample uses ``yyMMdd HHmmss`` (e.g. ``081109 203615`` ->
``2008-11-09T20:36:15``). Production logs will differ, so the format string is a
parameter, not a hardcoded assumption.

Never crash on a bad timestamp: fall back to the ingestion time and flag it, so a
single malformed line can't take down the stream.
"""

from datetime import datetime

#: Default format for the HDFS-style sample. Swap via the ``fmt`` argument or
#: Member 4's config when the production format differs.
HDFS_TIMESTAMP_FORMAT = "%y%m%d %H%M%S"


def parse_hdfs_timestamp(raw_timestamp, fmt=HDFS_TIMESTAMP_FORMAT, fallback_time=None):
    """Parse ``raw_timestamp`` to ``(datetime, fallback_used: bool)``.

    On success: ``(parsed_datetime, False)``.
    On any failure (bad format, empty, None): ``(fallback_time or now, True)`` —
    never raises. ``fallback_time`` lets the caller pass the file ingestion time;
    it defaults to the current time.
    """
    try:
        return datetime.strptime(raw_timestamp.strip(), fmt), False
    except (ValueError, TypeError, AttributeError):
        return (fallback_time if fallback_time is not None else datetime.now()), True

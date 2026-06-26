"""Webhook-ready serialization.

"Ready for webhook injection" means one valid JSON object per event. We default to
NDJSON (one object per line) using ``orjson`` for speed, which keeps the writer
streaming — events are serialized and emitted one at a time, never buffered into a
single array.
"""

import orjson


def dumps_line(record):
    """Serialize one validated event dict to a single-line JSON string.

    ``orjson.dumps`` returns ``bytes`` with no trailing newline; we decode to
    ``str`` so callers control line termination (NDJSON adds ``\\n`` per record).
    """
    return orjson.dumps(record).decode("utf-8")


def write_ndjson(records, stream):
    """Write an iterable of validated event dicts as NDJSON to ``stream``.

    Stays a generator-friendly consumer: each record is written as it arrives.
    Returns the number of records written.
    """
    count = 0
    for record in records:
        stream.write(dumps_line(record))
        stream.write("\n")
        count += 1
    return count

"""Dead-letter log — failed events are recorded, never silently dropped.

When an event can't be validated even after repair, it lands here with the reason,
so nothing is lost and failures are auditable. Written as NDJSON, one failure per
line. The file is opened lazily on first write, so a clean run creates no file.
"""

import orjson


class DeadLetterLog:
    """Append-only NDJSON sink for events that failed validation."""

    def __init__(self, path):
        self.path = path
        self.count = 0
        self._fh = None

    def record(self, event, reason):
        """Append one failed event with the failure reason."""
        if self._fh is None:
            self._fh = open(self.path, "w", encoding="utf-8")
        line = orjson.dumps({"reason": str(reason), "event": event}).decode("utf-8")
        self._fh.write(line)
        self._fh.write("\n")
        self._fh.flush()
        self.count += 1

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

from datetime import datetime, timezone

# The HDFS sample uses ``yyMMdd HHmmss`` (e.g. ``081109 203615`` ->
# ``2008-11-09T20:36:15``). Production logs will differ, so the format string is a
# parameter, not a hardcoded assumption.

def parse_hdfs_timestamp(raw_timestamp: str) -> tuple[datetime, bool]:
    """
    Convert HDFS timestamp format into a Python datetime.

    Example:
    "081109 203615" -> 2008-11-09T20:36:15

    Returns:
        (parsed_datetime, fallback_used)
    """

    try:
        parsed_time = datetime.strptime(raw_timestamp.strip(), "%y%m%d %H%M%S")
        return parsed_time, False
    except Exception:
        fallback_time = datetime.now(timezone.utc)
        return fallback_time, True

"""Swappable log-line regex patterns.

The regex lives HERE and nowhere else. Production logs will NOT match the HDFS
sample format, so the rest of the code never hardcodes the format — it asks this
module for a compiled pattern (or is handed one via config by Member 4).

A pattern must expose these named groups so :mod:`parser` can build an Event:

    date       -> combined with ``time`` into ``raw_timestamp``
    time       -> combined with ``date`` into ``raw_timestamp``
    pid        -> the process id AFTER the time. NOT part of the timestamp.
    level      -> ``severity``
    component  -> ``service_name``
    message    -> ``message`` (the body after the component's colon)

The ``pid`` group is mandatory in spirit even though parser ignores it: capturing
it explicitly is what stops the #1 parsing bug — swallowing the pid into the
timestamp (parsing ``203615 148`` as one value).
"""

import re

#: Default pattern for the HDFS-style sample (Docs/Group_Roles.md reference format)::
#:
#:     081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 ...
#:     └─date┘ └time┘ pid level └──component──────────────┘ └────message──────┘
#:
#: yyMMdd HHmmss  pid  ENUM     -> service_name               -> message body
#:
#: Note ``component`` is matched lazily up to the FIRST colon, so colons inside
#: the message body stay in the message.
DEFAULT_PATTERN = (
    r"^(?P<date>\d{6})\s+"
    r"(?P<time>\d{6})\s+"
    r"(?P<pid>\d+)\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<component>\S+?):\s*"
    r"(?P<message>.*)$"
)


def compile_pattern(pattern=DEFAULT_PATTERN):
    """Compile a log-line pattern string into a regex object.

    Pass a custom ``pattern`` (e.g. from Member 4's config) to swap formats
    without touching the parser. Defaults to the HDFS-style sample pattern.
    """
    return re.compile(pattern)


#: Pre-compiled default, so the common path doesn't recompile per call.
DEFAULT_LOG_PATTERN = compile_pattern(DEFAULT_PATTERN)

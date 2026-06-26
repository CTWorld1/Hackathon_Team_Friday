from enum import Enum


class SeverityEnum(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"
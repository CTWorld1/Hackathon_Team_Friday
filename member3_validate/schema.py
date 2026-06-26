from datetime import datetime

from pydantic import BaseModel, Field

from member3_validate.enums import SeverityEnum


class ValidatedLogEvent(BaseModel):
    service_name: str = Field(min_length=1)
    timestamp: datetime
    error_severity: SeverityEnum
    suggested_remediation: str = Field(min_length=1)

    timestamp_fallback_used: bool = False
    severity_mismatch: bool = False
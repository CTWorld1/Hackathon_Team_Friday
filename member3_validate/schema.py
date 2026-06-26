from datetime import datetime

from pydantic import BaseModel, Field

from member3_validate.enums import SeverityEnum


class ValidatedLogEvent(BaseModel):
    """
    Final validated log event before Member 4 writes it out.

    This combines:
    - service_name from Member 1
    - timestamp parsed by Member 3
    - error_severity from Member 1, cleaned by Member 3
    - suggested_remediation from Member 2
    """

    service_name: str = Field(min_length=1)
    timestamp: datetime
    error_severity: SeverityEnum
    suggested_remediation: str = Field(min_length=1)

    # Internal flags for debugging/quality checking.
    # These do not have to appear in the final JSON output.
    timestamp_fallback_used: bool = False
    severity_mismatch: bool = False
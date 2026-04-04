"""Domain entity LogEntry — unified polymorphic audit record."""

from __future__ import annotations

import datetime
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------
# UUID v4 format: 8-4-4-4-12 hex characters with hyphens (36 characters)
# --------------------------------------------------------------------------
_UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class EventType(str, Enum):
    """String enumeration of audit log event types."""

    CHAT_REQUEST = "chat_request"
    GUARDRAIL_INCIDENT = "guardrail_incident"
    SYSTEM_ERROR = "system_error"


class LogEntryCreate(BaseModel):
    """Schema for creating a log record (without id and created_at)."""

    trace_id: str
    event_type: EventType
    payload: dict[str, Any]

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id(cls, v: str) -> str:
        """[SRE_MARKER] — invalid trace_id will break log correlation."""
        if not _UUID_V4_RE.match(v):
            raise ValueError(
                "trace_id must be a valid UUID v4 string (36 chars with dashes)"
            )
        return v

    @field_validator("payload")
    @classmethod
    def _validate_payload_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        """[SRE_MARKER] — empty payload in an audit log is useless."""
        if len(v) == 0:
            raise ValueError("payload must contain at least one key")
        return v


from app.domain.utils.time import _utc_now


class LogEntry(LogEntryCreate):
    """Complete audit log domain entity (immutable)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    created_at: datetime.datetime = Field(default_factory=_utc_now)

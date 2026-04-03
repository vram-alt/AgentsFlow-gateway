"""Доменная сущность LogEntry — единая полиморфная запись аудита."""

from __future__ import annotations

import datetime
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------
# UUID v4 формат: 8-4-4-4-12 hex символов с дефисами (36 символов)
# --------------------------------------------------------------------------
_UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class EventType(str, Enum):
    """Строковое перечисление типов событий аудит-лога."""

    CHAT_REQUEST = "chat_request"
    GUARDRAIL_INCIDENT = "guardrail_incident"
    SYSTEM_ERROR = "system_error"


class LogEntryCreate(BaseModel):
    """Схема для создания записи лога (без id и created_at)."""

    trace_id: str
    event_type: EventType
    payload: dict[str, Any]

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id(cls, v: str) -> str:
        """[SRE_MARKER] — невалидный trace_id сломает корреляцию логов."""
        if not _UUID_V4_RE.match(v):
            raise ValueError(
                "trace_id must be a valid UUID v4 string (36 chars with dashes)"
            )
        return v

    @field_validator("payload")
    @classmethod
    def _validate_payload_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        """[SRE_MARKER] — пустой payload в аудит-логе бесполезен."""
        if len(v) == 0:
            raise ValueError("payload must contain at least one key")
        return v


def _utc_now() -> datetime.datetime:
    """Фабрика: возвращает текущее timezone-aware UTC время при каждом вызове."""
    return datetime.datetime.now(datetime.timezone.utc)


class LogEntry(LogEntryCreate):
    """Полная доменная сущность аудит-лога (иммутабельная)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    created_at: datetime.datetime = Field(default_factory=_utc_now)

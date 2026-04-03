"""
Pydantic V2 DTO: UnifiedResponse и UsageInfo.

Стандартизированное представление ответа от LLM-провайдера.
Спецификация: unified_response_spec.md
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class UsageInfo(BaseModel):
    """Вложенная frozen-модель статистики токенов."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: StrictInt = Field(..., ge=0)
    completion_tokens: StrictInt = Field(..., ge=0)
    total_tokens: StrictInt = Field(..., ge=0)


class UnifiedResponse(BaseModel):
    """Frozen DTO для стандартизированного ответа от LLM-провайдера."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    content: str
    model: str
    usage: Optional[UsageInfo] = None
    provider_raw: dict[str, Any] = Field(default_factory=dict)
    guardrail_blocked: bool = False
    guardrail_details: Optional[dict[str, Any]] = None

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id_is_uuid_v4(cls, v: str) -> str:
        try:
            parsed = uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError(f"trace_id must be a valid UUID v4, got: {v!r}")
        if parsed.version != 4:
            raise ValueError(f"trace_id must be UUID v4, got version {parsed.version}")
        return v

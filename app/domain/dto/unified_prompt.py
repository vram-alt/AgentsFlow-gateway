"""
Pydantic V2 DTO: UnifiedPrompt and MessageItem.

Standardized representation of a user request to an LLM provider.
Specification: unified_prompt_spec.md
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageItem(BaseModel):
    """Nested frozen model for a conversation message."""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class UnifiedPrompt(BaseModel):
    """Frozen DTO for a standardized request to an LLM provider."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    model: str
    messages: list[MessageItem] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    guardrail_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

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

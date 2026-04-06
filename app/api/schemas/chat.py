"""
Pydantic V2 schemas for POST /api/chat/send request/response.

Spec: app/api/routes/chat_spec.md
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MessageItem(BaseModel):
    """Single message in the conversation."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /api/chat/send."""

    model: str
    messages: list[MessageItem] = Field(..., min_length=1)
    provider_name: str = "portkey"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    guardrail_ids: list[str] = Field(default_factory=list)


class UsageInfo(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    """Success response for POST /api/chat/send.

    [YEL] usage typed as Optional[UsageInfo] instead of Optional[dict[str, Any]]
    for stronger validation. Falls back to dict for backward compatibility.
    """

    trace_id: str
    content: str
    model: str
    usage: Optional[UsageInfo | dict[str, Any]] = None
    guardrail_blocked: bool
    guardrail_details: Optional[dict[str, Any]] = None


# Re-export from common to maintain backward compatibility
from app.api.schemas.common import ErrorResponse as ErrorResponse  # noqa: F401

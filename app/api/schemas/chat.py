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
    """Success response for POST /api/chat/send."""

    trace_id: str
    content: str
    model: str
    usage: Optional[dict[str, Any]] = None
    guardrail_blocked: bool


class ErrorResponse(BaseModel):
    """Error response for POST /api/chat/send."""

    trace_id: str
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

"""Common Pydantic V2 schemas shared across API endpoints.

Centralizes ErrorResponse to eliminate duplication in chat.py, policies.py, providers.py.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Error response with trace_id for distributed tracing."""

    trace_id: str
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

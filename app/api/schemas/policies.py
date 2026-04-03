"""
Pydantic V2 schemas for policies CRUD endpoints.

Spec: app/api/routes/policies_spec.md
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PolicyCreateRequest(BaseModel):
    """Request body for POST /api/policies/."""

    name: str
    body: dict[str, Any]
    provider_name: str = "portkey"


class PolicyUpdateRequest(BaseModel):
    """Request body for PUT /api/policies/{policy_id}."""

    name: Optional[str] = None
    body: Optional[dict[str, Any]] = None


class SyncRequest(BaseModel):
    """Request body for POST /api/policies/sync."""

    provider_name: str = "portkey"


class ErrorResponse(BaseModel):
    """Error response with trace_id for distributed tracing."""

    trace_id: str
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

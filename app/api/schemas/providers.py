"""
Pydantic V2 schemas for providers CRUD endpoints.

Spec: app/api/routes/providers_spec.md
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ProviderCreateRequest(BaseModel):
    """Request body for POST /api/providers/."""

    name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    base_url: str

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


class ProviderUpdateRequest(BaseModel):
    """Request body for PUT /api/providers/{provider_id}."""

    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


# Re-export from common to maintain backward compatibility
from app.api.schemas.common import ErrorResponse as ErrorResponse  # noqa: F401

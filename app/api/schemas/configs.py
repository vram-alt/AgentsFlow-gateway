"""
Pydantic V2 schemas for configs CRUD endpoints.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ConfigCreateRequest(BaseModel):
    """Request body for POST /api/configs/."""

    name: str
    config: dict[str, Any]
    is_default: int = 0
    provider_name: str = "portkey"


class ConfigUpdateRequest(BaseModel):
    """Request body for PUT /api/configs/{slug}."""

    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[str] = None

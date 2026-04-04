"""
Router: Application settings management.

Provides GET/PUT endpoints for runtime configuration like DEMO_MODE.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.middleware.auth import get_current_user

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class DemoModeRequest(BaseModel):
    """Request body for PUT /api/settings/demo-mode."""

    enabled: bool


@router.get("/demo-mode")
async def get_demo_mode(
    _current_user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/settings/demo-mode — current demo mode status."""
    enabled = os.environ.get("DEMO_MODE", "").lower() in ("true", "1", "yes")
    return {"enabled": enabled}


@router.put("/demo-mode")
async def set_demo_mode(
    body: DemoModeRequest,
    _current_user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """PUT /api/settings/demo-mode — toggle demo mode at runtime.

    Sets the DEMO_MODE environment variable for the current process.
    Note: This change is not persisted across restarts.
    """
    if body.enabled:
        os.environ["DEMO_MODE"] = "true"
    else:
        os.environ.pop("DEMO_MODE", None)

    return {"enabled": body.enabled, "message": "Demo mode updated successfully"}

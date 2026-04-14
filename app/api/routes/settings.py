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
from app.config import get_settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class DemoModeRequest(BaseModel):
    """Request body for PUT /api/settings/demo-mode."""

    enabled: bool


def _effective_demo_mode_enabled() -> bool:
    """Return the effective demo-mode value used by the app at runtime.

    Priority order matches the adapter behavior:
    1. Explicit `DEMO_MODE` process env override (`true` or `false`)
    2. Fallback to the configured value loaded from `.env`
    """
    env_value = os.environ.get("DEMO_MODE")
    if env_value is not None:
        return env_value.lower() in ("true", "1", "yes")
    try:
        return bool(get_settings().demo_mode)
    except Exception:
        return False


@router.get("/demo-mode")
async def get_demo_mode(
    _current_user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/settings/demo-mode — current effective demo mode status."""
    return {"enabled": _effective_demo_mode_enabled()}


@router.put("/demo-mode")
async def set_demo_mode(
    body: DemoModeRequest,
    _current_user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """PUT /api/settings/demo-mode — toggle demo mode at runtime.

    Sets an explicit `DEMO_MODE` process override for the current process.
    Note: This change is not persisted across restarts.
    """
    os.environ["DEMO_MODE"] = "true" if body.enabled else "false"

    return {
        "enabled": _effective_demo_mode_enabled(),
        "message": "Demo mode updated successfully",
    }

"""
Router: Portkey Config management — CRUD, toggle, guardrails and integrations listing.

[SRE_MARKER] /integrations and /guardrails MUST be declared BEFORE /{slug}.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_config_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.configs import ConfigCreateRequest, ConfigUpdateRequest
from app.api.utils import (
    gateway_error_response,
    internal_error_response,
    is_gateway_error,
    serialize,
)
from app.services.config_service import ConfigService

router = APIRouter(prefix="/api/configs", tags=["Configs"])


# ── GET /api/configs/ ────────────────────────────────────────────────
@router.get("/")
async def list_configs(
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """List all configs from Portkey."""
    try:
        result = await config_service.list_configs()
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── POST /api/configs/ ───────────────────────────────────────────────
@router.post("/", status_code=201)
async def create_config(
    body: ConfigCreateRequest,
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Create a new config on Portkey."""
    try:
        result = await config_service.create_config(
            name=body.name,
            config_body=body.config,
            is_default=body.is_default,
            provider_name=body.provider_name,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=201, content=serialize(result))


# ── GET /api/configs/integrations — MUST be BEFORE /{slug} ───────────
@router.get("/integrations")
async def list_integrations(
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """List LLM integrations from Portkey."""
    try:
        result = await config_service.list_integrations()
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── GET /api/configs/guardrails — MUST be BEFORE /{slug} ─────────────
@router.get("/guardrails")
async def list_guardrails(
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """List guardrails from Portkey (for config UI selection)."""
    try:
        result = await config_service.list_guardrails()
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── GET /api/configs/{slug} ──────────────────────────────────────────
@router.get("/{slug}")
async def retrieve_config(
    slug: str,
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Retrieve a specific config from Portkey."""
    try:
        result = await config_service.retrieve_config(slug=slug)
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── PUT /api/configs/{slug} ──────────────────────────────────────────
@router.put("/{slug}")
async def update_config(
    slug: str,
    body: ConfigUpdateRequest,
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Update an existing config on Portkey."""
    try:
        result = await config_service.update_config(
            slug=slug,
            name=body.name,
            config_body=body.config,
            status=body.status,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── DELETE /api/configs/{slug} ────────────────────────────────────────
@router.delete("/{slug}")
async def delete_config(
    slug: str,
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Delete a config from Portkey."""
    try:
        result = await config_service.delete_config(slug=slug)
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content={"status": "deleted"})


# ── PATCH /api/configs/{slug}/toggle ──────────────────────────────────
@router.patch("/{slug}/toggle")
async def toggle_config(
    slug: str,
    config_service: ConfigService = Depends(get_config_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Toggle config status between active and inactive."""
    try:
        result = await config_service.toggle_config(slug=slug)
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))

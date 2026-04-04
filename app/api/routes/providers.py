"""
Router: CRUD for LLM providers.

Spec: app/api/routes/providers_spec.md
[SRE_MARKER] trace_id MUST always be present in error responses (JSONResponse).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_http_client, get_provider_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.providers import (
    ProviderCreateRequest,
    ProviderUpdateRequest,
)
from app.api.utils import (
    gateway_error_response,
    internal_error_response,
    is_gateway_error,
    serialize,
)

router = APIRouter(prefix="/api/providers", tags=["Providers"])


# ── Кэш для health-check (upgrade spec §1.4 п.2) ────────────────────
_health_cache: dict[str, Any] = {}
_health_cache_timestamp: float = 0.0
_health_cache_service_id: int | None = None
_HEALTH_CACHE_TTL: float = 30.0


# ── GET /api/providers/health ────────────────────────────────────────
# MUST be registered BEFORE /{provider_id} (upgrade spec §1.7)
@router.get("/health")
async def get_providers_health(
    provider_service: Any = Depends(get_provider_service),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """GET /api/providers/health — provider availability status."""
    global _health_cache, _health_cache_timestamp, _health_cache_service_id

    # Reset cache if service changed (for tests)
    svc_id = id(provider_service)
    if _health_cache_service_id is not None and _health_cache_service_id != svc_id:
        _health_cache = {}
        _health_cache_timestamp = 0.0
    _health_cache_service_id = svc_id

    now = time.monotonic()
    if _health_cache and (now - _health_cache_timestamp) < _HEALTH_CACHE_TTL:
        return _health_cache.get("result", [])

    try:
        result = await provider_service.check_health(http_client)
    except Exception as exc:
        return internal_error_response(exc)

    _health_cache = {"result": result}
    _health_cache_timestamp = time.monotonic()

    return result


# ── GET /api/providers/ ──────────────────────────────────────────────
@router.get("/")
async def list_providers(
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """List all providers."""
    try:
        result = await provider_service.list_providers()
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── POST /api/providers/ ─────────────────────────────────────────────
@router.post("/", status_code=201)
async def create_provider(
    body: ProviderCreateRequest,
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Create a new provider."""
    try:
        result = await provider_service.create_provider(
            name=body.name,
            api_key=body.api_key,
            base_url=body.base_url,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=201, content=serialize(result))


# ── PUT /api/providers/{provider_id} ─────────────────────────────────
@router.put("/{provider_id}")
async def update_provider(
    provider_id: int,
    body: ProviderUpdateRequest,
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Update a provider."""
    try:
        result = await provider_service.update_provider(
            provider_id=provider_id,
            name=body.name,
            api_key=body.api_key,
            base_url=body.base_url,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── DELETE /api/providers/{provider_id} ───────────────────────────────
@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Soft delete a provider."""
    try:
        result = await provider_service.delete_provider(provider_id=provider_id)
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content={"status": "deleted"})

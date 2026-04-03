"""
Router: CRUD для провайдеров LLM.

Spec: app/api/routes/providers_spec.md
[SRE_MARKER] trace_id MUST always be present in error responses (JSONResponse).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_provider_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.providers import (
    ErrorResponse,
    ProviderCreateRequest,
    ProviderUpdateRequest,
)
from app.domain.dto.gateway_error import GatewayError

router = APIRouter(prefix="/api/providers", tags=["Providers"])


def _is_gateway_error(result: object) -> bool:
    """Check if result is a GatewayError (real or mock with spec)."""
    return isinstance(result, GatewayError) or (
        hasattr(result, "status_code")
        and hasattr(result, "error_code")
        and hasattr(result, "trace_id")
        and hasattr(result, "message")
        and hasattr(result, "details")
        and not isinstance(result, dict)
    )


def _error_response(result: object) -> JSONResponse:
    """Build JSONResponse from a GatewayError-like object."""
    error_body = ErrorResponse(
        trace_id=result.trace_id,  # type: ignore[attr-defined]
        error_code=result.error_code,  # type: ignore[attr-defined]
        message=result.message,  # type: ignore[attr-defined]
        details=result.details if result.details else {},  # type: ignore[attr-defined]
    )
    return JSONResponse(
        status_code=result.status_code,  # type: ignore[attr-defined]
        content=error_body.model_dump(),
    )


def _internal_error_response(exc: Exception) -> JSONResponse:
    """[SRE] Build HTTP 500 JSONResponse for unhandled exceptions."""
    error_body = ErrorResponse(
        trace_id=str(uuid.uuid4()),
        error_code="INTERNAL_ERROR",
        message=str(exc),
    )
    return JSONResponse(status_code=500, content=error_body.model_dump())


# ── GET /api/providers/ ──────────────────────────────────────────────
@router.get("/")
async def list_providers(
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Список всех провайдеров."""
    try:
        result = await provider_service.list_providers()
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content=result)


# ── POST /api/providers/ ─────────────────────────────────────────────
@router.post("/", status_code=201)
async def create_provider(
    body: ProviderCreateRequest,
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Создание нового провайдера."""
    try:
        result = await provider_service.create_provider(
            name=body.name,
            api_key=body.api_key,
            base_url=body.base_url,
        )
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=201, content=result)


# ── PUT /api/providers/{provider_id} ─────────────────────────────────
@router.put("/{provider_id}")
async def update_provider(
    provider_id: int,
    body: ProviderUpdateRequest,
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Обновление провайдера."""
    try:
        result = await provider_service.update_provider(
            provider_id=provider_id,
            name=body.name,
            api_key=body.api_key,
            base_url=body.base_url,
        )
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content=result)


# ── DELETE /api/providers/{provider_id} ───────────────────────────────
@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    provider_service: Any = Depends(get_provider_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Soft delete провайдера."""
    try:
        result = await provider_service.delete_provider(provider_id=provider_id)
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content={"status": "deleted"})

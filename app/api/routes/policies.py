"""
Router: CRUD для политик безопасности (Guardrails) и синхронизация с облаком.

Spec: app/api/routes/policies_spec.md
[SRE_MARKER] trace_id MUST always be present in error responses (JSONResponse).
[SRE_MARKER] /sync route MUST be declared BEFORE /{policy_id} to avoid capture.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_policy_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.policies import (
    ErrorResponse,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    SyncRequest,
)
from app.domain.dto.gateway_error import GatewayError
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/api/policies", tags=["Policies"])


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


# ── GET /api/policies/ ───────────────────────────────────────────────
@router.get("/")
async def list_policies(
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Список всех активных политик."""
    try:
        result = await policy_service.list_policies()
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content=result)


# ── POST /api/policies/ ─────────────────────────────────────────────
@router.post("/", status_code=201)
async def create_policy(
    body: PolicyCreateRequest,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Создание новой политики."""
    try:
        result = await policy_service.create_policy(
            name=body.name,
            body=body.body,
            provider_name=body.provider_name,
        )
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=201, content=result)


# ── POST /api/policies/sync — MUST be BEFORE /{policy_id} ───────────
@router.post("/sync")
async def sync_policies(
    body: SyncRequest,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Синхронизация политик из облака провайдера."""
    try:
        result = await policy_service.sync_policies_from_provider(
            provider_name=body.provider_name,
        )
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content=result)


# ── PUT /api/policies/{policy_id} ───────────────────────────────────
@router.put("/{policy_id}")
async def update_policy(
    policy_id: int,
    body: PolicyUpdateRequest,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Обновление политики."""
    try:
        result = await policy_service.update_policy(
            policy_id=policy_id,
            name=body.name,
            body=body.body,
        )
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content=result)


# ── DELETE /api/policies/{policy_id} ─────────────────────────────────
@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: int,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Soft delete политики."""
    try:
        result = await policy_service.delete_policy(policy_id=policy_id)
    except Exception as exc:
        return _internal_error_response(exc)

    if _is_gateway_error(result):
        return _error_response(result)

    return JSONResponse(status_code=200, content={"status": "deleted"})

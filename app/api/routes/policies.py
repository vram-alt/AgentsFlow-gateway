"""
Router: CRUD for security policies (Guardrails) and cloud sync.

Spec: app/api/routes/policies_spec.md
[SRE_MARKER] trace_id MUST always be present in error responses (JSONResponse).
[SRE_MARKER] /sync route MUST be declared BEFORE /{policy_id} to avoid capture.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_policy_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.policies import (
    PolicyCreateRequest,
    PolicyUpdateRequest,
    SyncRequest,
)
from app.api.utils import (
    gateway_error_response,
    internal_error_response,
    is_gateway_error,
    serialize,
)
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/api/policies", tags=["Policies"])


# ── GET /api/policies/ ───────────────────────────────────────────────
@router.get("/")
async def list_policies(
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """List all active policies."""
    try:
        result = await policy_service.list_policies()
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── POST /api/policies/ ─────────────────────────────────────────────
@router.post("/", status_code=201)
async def create_policy(
    body: PolicyCreateRequest,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Create a new policy."""
    try:
        result = await policy_service.create_policy(
            name=body.name,
            body=body.body,
            provider_name=body.provider_name,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=201, content=serialize(result))


# ── POST /api/policies/sync — MUST be BEFORE /{policy_id} ───────────
@router.post("/sync")
async def sync_policies(
    body: SyncRequest,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Sync policies from cloud provider."""
    try:
        result = await policy_service.sync_policies_from_provider(
            provider_name=body.provider_name,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── PUT /api/policies/{policy_id} ───────────────────────────────────
@router.put("/{policy_id}")
async def update_policy(
    policy_id: int,
    body: PolicyUpdateRequest,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Update a policy."""
    try:
        result = await policy_service.update_policy(
            policy_id=policy_id,
            name=body.name,
            body=body.body,
        )
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content=serialize(result))


# ── DELETE /api/policies/{policy_id} ─────────────────────────────────
@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: int,
    policy_service: PolicyService = Depends(get_policy_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Soft delete a policy."""
    try:
        result = await policy_service.delete_policy(policy_id=policy_id)
    except Exception as exc:
        return internal_error_response(exc)

    if is_gateway_error(result):
        return gateway_error_response(result)

    return JSONResponse(status_code=200, content={"status": "deleted"})

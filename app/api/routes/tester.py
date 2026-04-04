"""Testing Console module router.

Specification: app/api/routes/tester_spec.md
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_tester_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.tester import (
    TesterProxyRequest,
    TesterProxyResponse,
)
from app.domain.dto.gateway_error import GatewayError
from app.services.tester_service import TesterService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/tester",
    tags=["Tester"],
)

# ── Static form schema (§2.4) ───────────────────────────────────────

_FORM_SCHEMA: dict[str, Any] = {
    "fields": [
        {
            "name": "provider_name",
            "type": "select",
            "label": "Provider",
            "required": True,
            "default": "portkey",
            "options": ["portkey"],
        },
        {
            "name": "model",
            "type": "text",
            "label": "Model",
            "required": True,
            "default": None,
            "options": None,
        },
        {
            "name": "prompt",
            "type": "textarea",
            "label": "Prompt",
            "required": True,
            "default": None,
            "options": None,
        },
        {
            "name": "temperature",
            "type": "number",
            "label": "Temperature",
            "required": False,
            "default": 0.7,
            "options": None,
        },
        {
            "name": "max_tokens",
            "type": "number",
            "label": "Max Tokens",
            "required": False,
            "default": 1024,
            "options": None,
        },
    ]
}


@router.get("/schema")
async def get_tester_schema(
    _user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/tester/schema — static JSON form schema (§2)."""
    return _FORM_SCHEMA


@router.post("/proxy")
async def post_tester_proxy(
    request: TesterProxyRequest,
    tester_service: TesterService = Depends(get_tester_service),
    _user: str = Depends(get_current_user),
) -> Any:
    """POST /api/tester/proxy — proxy request to provider (§3)."""
    result = await tester_service.proxy_request(
        provider_name=request.provider_name,
        method=request.method,
        path=request.path,
        body=request.body,
        headers=request.headers,
    )

    if isinstance(result, GatewayError):
        return JSONResponse(
            status_code=result.status_code,
            content={
                "trace_id": result.trace_id,
                "error_code": result.error_code,
                "message": result.message,
            },
        )

    return result

"""
Router: POST /api/chat/send — send a prompt to the LLM via the gateway (Mode A).

Spec: app/api/routes/chat_spec.md
[SRE_MARKER] trace_id MUST always be present in both success and error responses.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_chat_service
from app.api.middleware.auth import get_current_user
from app.api.schemas.chat import ChatRequest, ChatResponse, ErrorResponse
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_response import UnifiedResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/send", response_model=ChatResponse)
async def send_chat(
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    _current_user: str = Depends(get_current_user),
) -> JSONResponse:
    """Send a prompt to the LLM via the gateway."""

    result = await chat_service.send_chat_message(
        model=body.model,
        messages=[m.model_dump() for m in body.messages],
        provider_name=body.provider_name,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        guardrail_ids=body.guardrail_ids,
    )

    if isinstance(result, GatewayError):
        error_body = ErrorResponse(
            trace_id=result.trace_id,
            error_code=result.error_code,
            message=result.message,
            details=result.details,
        )
        return JSONResponse(
            status_code=result.status_code,
            content=error_body.model_dump(),
        )

    # result is UnifiedResponse (or mock with same attrs)
    # Convert usage to dict to avoid cross-module Pydantic model mismatch
    # (unified_response.UsageInfo vs chat.UsageInfo)
    usage_raw = result.usage
    if usage_raw is not None and hasattr(usage_raw, "model_dump"):
        usage_data = usage_raw.model_dump()
    else:
        usage_data = usage_raw  # already a dict or None
    chat_response = ChatResponse(
        trace_id=result.trace_id,
        content=result.content,
        model=result.model,
        usage=usage_data,
        guardrail_blocked=result.guardrail_blocked,
    )
    return JSONResponse(status_code=200, content=chat_response.model_dump())

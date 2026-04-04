"""
Event log router — HTTP handlers for viewing logs and statistics.

Specification: app/api/routes/logs_spec.md
Addendum: app/api/routes/logs_upgrade_spec.md
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.dependencies.di import get_chat_service, get_log_service
from app.api.middleware.auth import get_current_user
from app.api.utils import serialize
from app.domain.dto.gateway_error import GatewayError
from app.services.log_service import LogService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["Logs"])

# ── Rate-limit for replay (§3.4) ────────────────────────────────────────
_replay_rate_limit: dict[str, list[float]] = {}
_replay_rate_limit_app_id: int | None = None
_REPLAY_MAX_PER_MINUTE = 10


def _check_replay_rate_limit(user: str, app_id: int | None = None) -> bool:
    """Check rate-limit for replay. Returns True if limit exceeded."""
    global _replay_rate_limit, _replay_rate_limit_app_id

    # Reset rate-limiter on app change (for tests with different TestClient)
    if (
        app_id is not None
        and _replay_rate_limit_app_id is not None
        and _replay_rate_limit_app_id != app_id
    ):
        _replay_rate_limit.clear()
    _replay_rate_limit_app_id = app_id

    now = time.monotonic()
    if user not in _replay_rate_limit:
        _replay_rate_limit[user] = []

    # Remove entries older than 60 seconds
    _replay_rate_limit[user] = [ts for ts in _replay_rate_limit[user] if now - ts < 60]

    if len(_replay_rate_limit[user]) >= _REPLAY_MAX_PER_MINUTE:
        return True

    _replay_rate_limit[user].append(now)
    return False


# ── Private helpers for replay (God Method refactoring) ────────────────


def _extract_replay_params(
    log_entry: Any,
) -> tuple[Any, dict[str, Any], str] | JSONResponse:
    """§3.5 steps 5-6: Extract and validate replay parameters from the log record.

    Returns:
        Tuple (chat_request, payload_dict, provider_name) on success,
        or JSONResponse on validation failure.
    """
    from app.api.schemas.chat import ChatRequest

    payload = log_entry.payload
    if isinstance(payload, str):
        payload = json.loads(payload)

    prompt_data = payload.get("prompt", {})

    chat_request = ChatRequest(
        model=prompt_data.get("model", ""),
        messages=prompt_data.get("messages", []),
        temperature=prompt_data.get("temperature"),
        max_tokens=prompt_data.get("max_tokens"),
        guardrail_ids=prompt_data.get("guardrail_ids", []),
    )

    # [YEL-8] Extract provider_name from original payload instead of hardcoding
    provider_name = prompt_data.get("provider_name", "portkey")
    if isinstance(payload.get("provider_name"), str):
        provider_name = payload["provider_name"]

    return chat_request, payload, provider_name


async def _execute_replay(
    chat_service: Any,
    chat_request: Any,
    provider_name: str,
) -> JSONResponse | dict[str, Any]:
    """§3.5 steps 8-10: Execute replay via ChatService and build the response."""
    result = await chat_service.send_chat_message(
        model=chat_request.model,
        messages=[
            {"role": m.role, "content": m.content} for m in chat_request.messages
        ],
        provider_name=provider_name,
        temperature=chat_request.temperature,
        max_tokens=chat_request.max_tokens,
        guardrail_ids=chat_request.guardrail_ids,
    )

    # §3.5 step 9: Handle GatewayError
    if isinstance(result, GatewayError):
        return JSONResponse(
            status_code=result.status_code,
            content={
                "trace_id": result.trace_id,
                "error_code": result.error_code,
                "message": result.message,
            },
        )

    # §3.5 step 10: Successful response
    return {
        "trace_id": result.trace_id,
        "content": result.content,
        "model": result.model,
        "usage": result.usage,
        "guardrail_blocked": result.guardrail_blocked,
    }


# ── Log serialization helper ────────────────────────────────────────────


def _serialize_logs(logs: Any) -> list[dict[str, Any]]:
    """Convert a list of LogEntryModel to JSON-compatible dicts.

    Parses payload from JSON string to dict for the frontend.
    """
    result = serialize(logs)
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and isinstance(item.get("payload"), str):
                try:
                    item["payload"] = json.loads(item["payload"])
                except (json.JSONDecodeError, TypeError):
                    pass
    return result


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/")
async def get_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """Paginated list of log events.

    Upgrade §1: if trace_id is provided — calls get_logs_by_trace_id,
    ignoring limit/offset/event_type.
    """
    try:
        # §1.4: If trace_id is provided
        if trace_id is not None and trace_id.strip():
            # §1.3: UUID v4 validation
            try:
                parsed = uuid.UUID(trace_id)
            except ValueError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Invalid trace_id format, expected UUID v4"},
                )
            return _serialize_logs(await log_service.get_logs_by_trace_id(trace_id))

        result = await log_service.get_logs(
            limit=limit, offset=offset, event_type=event_type
        )
        return _serialize_logs(result)
    except RuntimeError:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )


@router.get("/stats")
async def get_log_stats(
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """Event statistics for the dashboard."""
    try:
        result = await log_service.get_log_stats()
        return result
    except RuntimeError:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )


@router.get("/export")
async def export_logs(
    event_type: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """GET /api/logs/export — CSV export (upgrade spec §2)."""
    try:
        csv_generator = log_service.export_logs(event_type=event_type, limit=limit)
        return StreamingResponse(
            csv_generator,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=logs_export.csv",
            },
        )
    except Exception as exc:
        logger.error("Export error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )


@router.post("/{log_id}/replay")
async def replay_log(
    log_id: int,
    request: Request,
    log_service: LogService = Depends(get_log_service),
    chat_service: Any = Depends(get_chat_service),
    current_user: str = Depends(get_current_user),
) -> Any:
    """POST /api/logs/{id}/replay — replay a chat request (upgrade spec §3)."""
    # §3.4: Rate-limit
    if _check_replay_rate_limit(current_user, app_id=id(request.app)):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded for replay requests"},
        )

    try:
        # §3.5 step 2: Fetch the log record
        log_entry = await log_service.get_log_by_id(log_id)
        if log_entry is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "Log entry not found"},
            )

        # §3.5 step 4: Check event type
        if log_entry.event_type != "chat_request":
            return JSONResponse(
                status_code=400,
                content={"detail": "Only chat_request logs can be replayed"},
            )

        # §3.5 steps 5-6: Extract and validate parameters
        try:
            extraction = _extract_replay_params(log_entry)
            if isinstance(extraction, JSONResponse):
                return extraction
            chat_request, payload, provider_name = extraction
        except Exception as exc:
            # [YEL-4] Log suppressed exception for debugging
            logger.warning(
                "Replay data extraction failed for log_id=%s: %s", log_id, exc
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Original request data is incomplete for replay"},
            )

        # §3.5 step 7: Log the replay event
        logger.info(
            "Replay started: log_id=%s user=%s is_replay=true",
            log_id,
            current_user,
        )

        # §3.5 steps 8-10: Execute replay and return result
        return await _execute_replay(chat_service, chat_request, provider_name)

    except Exception as exc:
        logger.error("Replay error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


@router.get("/{trace_id}")
async def get_logs_by_trace_id(
    trace_id: str,
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """All events for a specific trace_id."""
    try:
        result = await log_service.get_logs_by_trace_id(trace_id)
        return _serialize_logs(result)
    except RuntimeError:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

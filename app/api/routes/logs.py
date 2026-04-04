"""
Роутер журнала событий — HTTP-обработчики для просмотра логов и статистики.

Спецификация: app/api/routes/logs_spec.md
Дополнение: app/api/routes/logs_upgrade_spec.md
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
from app.services.log_service import LogService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["Logs"])

# ── Rate-limit для replay (§3.4) ────────────────────────────────────────
_replay_rate_limit: dict[str, list[float]] = {}
_replay_rate_limit_app_id: int | None = None
_REPLAY_MAX_PER_MINUTE = 10


def _check_replay_rate_limit(user: str, app_id: int | None = None) -> bool:
    """Проверяет rate-limit для replay. Возвращает True если лимит превышен."""
    global _replay_rate_limit, _replay_rate_limit_app_id

    # Сбрасываем rate-limiter при смене app (для тестов с разными TestClient)
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

    # Удаляем записи старше 60 секунд
    _replay_rate_limit[user] = [ts for ts in _replay_rate_limit[user] if now - ts < 60]

    if len(_replay_rate_limit[user]) >= _REPLAY_MAX_PER_MINUTE:
        return True

    _replay_rate_limit[user].append(now)
    return False


@router.get("/")
async def get_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """Постраничный список событий журнала.

    Upgrade §1: если trace_id передан — вызывает get_logs_by_trace_id,
    игнорируя limit/offset/event_type.
    """
    try:
        # §1.4: Если trace_id передан
        if trace_id is not None and trace_id.strip():
            # §1.3: Валидация UUID v4
            try:
                parsed = uuid.UUID(trace_id)
            except ValueError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Invalid trace_id format, expected UUID v4"},
                )
            return await log_service.get_logs_by_trace_id(trace_id)

        result = await log_service.get_logs(
            limit=limit, offset=offset, event_type=event_type
        )
        return result
    except RuntimeError:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )


@router.get("/stats")
async def get_log_stats(
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """Статистика событий для дашборда."""
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
    """GET /api/logs/export — CSV-экспорт (upgrade spec §2)."""
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
    """POST /api/logs/{id}/replay — повтор чат-запроса (upgrade spec §3)."""
    # §3.4: Rate-limit
    if _check_replay_rate_limit(current_user, app_id=id(request.app)):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded for replay requests"},
        )

    try:
        # §3.5 п.2: Получить запись лога
        log_entry = await log_service.get_log_by_id(log_id)
        if log_entry is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "Log entry not found"},
            )

        # §3.5 п.4: Проверить тип события
        if log_entry.event_type != "chat_request":
            return JSONResponse(
                status_code=400,
                content={"detail": "Only chat_request logs can be replayed"},
            )

        # §3.5 п.5: Извлечь параметры из payload
        try:
            payload = log_entry.payload
            if isinstance(payload, str):
                payload = json.loads(payload)

            prompt_data = payload.get("prompt", {})

            # §3.5 п.6: Валидация через Pydantic-схему
            from app.api.schemas.chat import ChatRequest

            chat_request = ChatRequest(
                model=prompt_data.get("model", ""),
                messages=prompt_data.get("messages", []),
                temperature=prompt_data.get("temperature"),
                max_tokens=prompt_data.get("max_tokens"),
                guardrail_ids=prompt_data.get("guardrail_ids", []),
            )
        except Exception as exc:
            # [YEL-4] Log suppressed exception for debugging
            logger.warning(
                "Replay data extraction failed for log_id=%s: %s", log_id, exc
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Original request data is incomplete for replay"},
            )

        # §3.5 п.7: Логировать replay-событие
        logger.info(
            "Replay started: log_id=%s user=%s is_replay=true",
            log_id,
            current_user,
        )

        # §3.5 п.8: Call ChatService
        # [YEL-8] Extract provider_name from original payload instead of hardcoding
        from app.domain.dto.gateway_error import GatewayError

        provider_name = prompt_data.get("provider_name", "portkey")
        if isinstance(payload.get("provider_name"), str):
            provider_name = payload["provider_name"]

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

        # §3.5 п.9: Обработка GatewayError
        if isinstance(result, GatewayError):
            return JSONResponse(
                status_code=result.status_code,
                content={
                    "trace_id": result.trace_id,
                    "error_code": result.error_code,
                    "message": result.message,
                },
            )

        # §3.5 п.10: Успешный ответ
        return {
            "trace_id": result.trace_id,
            "content": result.content,
            "model": result.model,
            "usage": result.usage,
            "guardrail_blocked": result.guardrail_blocked,
        }

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
    """Все события по конкретному trace_id."""
    try:
        result = await log_service.get_logs_by_trace_id(trace_id)
        return result
    except RuntimeError:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

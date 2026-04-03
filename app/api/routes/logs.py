"""
Роутер журнала событий — HTTP-обработчики для просмотра логов и статистики.

Спецификация: app/api/routes/logs_spec.md
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_log_service
from app.api.middleware.auth import get_current_user
from app.services.log_service import LogService

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("/")
async def get_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    log_service: LogService = Depends(get_log_service),
    _current_user: str = Depends(get_current_user),
) -> Any:
    """Постраничный список событий журнала."""
    try:
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

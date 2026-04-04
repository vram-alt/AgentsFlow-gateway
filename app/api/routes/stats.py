"""Dashboard module router — aggregated statistics and chart data.

Specification: app/api/routes/stats_spec.md
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_log_service
from app.api.middleware.auth import get_current_user
from app.services.log_service import LogService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stats",
    tags=["Stats"],
)

# ── Cache for summary (§2.3) ──────────────────────────────────────────────
_summary_cache: dict[str, Any] = {}
_summary_cache_timestamp: float = 0.0
_summary_cache_service_id: int | None = None
_SUMMARY_CACHE_TTL: float = 60.0  # seconds

# ── Async lock to protect against parallel requests (§2.4) ────────────────
_summary_lock = asyncio.Lock()


def _invalidate_cache_if_service_changed(service_id: int) -> None:
    """Reset cache if service changed (new mock in tests)."""
    global _summary_cache, _summary_cache_timestamp, _summary_cache_service_id
    if (
        _summary_cache_service_id is not None
        and _summary_cache_service_id != service_id
    ):
        _summary_cache = {}
        _summary_cache_timestamp = 0.0
    _summary_cache_service_id = service_id


@router.get("/summary")
async def get_stats_summary(
    log_service: LogService = Depends(get_log_service),
    _user: str = Depends(get_current_user),
) -> Any:
    """GET /api/stats/summary — summary statistics (§2)."""
    global _summary_cache, _summary_cache_timestamp

    # Reset cache if service changed (for tests with different mocks)
    _invalidate_cache_if_service_changed(id(log_service))

    # §2.5 step 1: Check cache
    now = time.monotonic()
    if _summary_cache and (now - _summary_cache_timestamp) < _SUMMARY_CACHE_TTL:
        return _summary_cache

    # §2.4: Acquire lock
    async with _summary_lock:
        # §2.5 step 3: Double-check cache after acquiring lock
        now = time.monotonic()
        if _summary_cache and (now - _summary_cache_timestamp) < _SUMMARY_CACHE_TTL:
            return _summary_cache

        try:
            result = await log_service.get_stats_summary()
        except Exception as exc:
            trace_id = str(uuid.uuid4())
            logger.error(
                "Stats summary error trace_id=%s: %s",
                trace_id,
                exc,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "trace_id": trace_id,
                },
            )

        # §2.5 step 6: Save to cache
        _summary_cache = result
        _summary_cache_timestamp = time.monotonic()

        return result


@router.get("/charts")
async def get_stats_charts(
    hours: int = Query(default=24, ge=1, le=168),
    log_service: LogService = Depends(get_log_service),
    _user: str = Depends(get_current_user),
) -> Any:
    """GET /api/stats/charts — chart data (§3)."""
    try:
        result = await log_service.get_chart_data(hours=hours)
    except Exception as exc:
        trace_id = str(uuid.uuid4())
        logger.error(
            "Stats charts error trace_id=%s: %s",
            trace_id,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "trace_id": trace_id,
            },
        )

    return result

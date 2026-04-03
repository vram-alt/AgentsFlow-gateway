"""
FastAPI application entry point.

Spec: app/main_spec.md
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_adapter
from app.api.routes.chat import router as chat_router
from app.api.routes.logs import router as logs_router
from app.api.routes.policies import router as policies_router
from app.api.routes.providers import router as providers_router
from app.api.routes.webhook import router as webhook_router
from app.config import get_settings
from app.domain.dto.gateway_error import GatewayError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (§3)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Асинхронный менеджер жизненного цикла приложения."""
    # ── Startup (§3.1) ────────────────────────────────────────────────
    _settings = get_settings()
    logging.basicConfig(level=logging.INFO)

    # Автоматическое создание таблиц при старте
    # [SRE_MARKER] Fail-fast: если БД недоступна — завершить процесс
    try:
        from app.infrastructure.database.models import Base
        from app.infrastructure.database.session import engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified successfully")
    except Exception as exc:
        logger.critical("Database initialization failed: %s", exc)
        sys.exit(1)

    logger.info("AI Gateway started successfully")

    yield

    # ── Shutdown (§3.2) ───────────────────────────────────────────────
    # Закрыть HTTP-адаптер
    try:
        adapter = get_adapter()
        await adapter.close()
    except Exception as exc:
        logger.warning("Error closing adapter: %s", exc)

    # Закрыть пул соединений БД
    try:
        from app.infrastructure.database.session import engine

        await engine.dispose()
    except Exception as exc:
        logger.warning("Error disposing DB engine: %s", exc)

    logger.info("AI Gateway shut down")


# ---------------------------------------------------------------------------
# Создание приложения (§2)
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Gateway Adapter",
    description="Phase 3 POC — Intelligent proxy for LLM providers",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Глобальные обработчики исключений (§5)
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """§5.1 + §5.2: Обработка GatewayError (если брошен) и catch-all.

    GatewayError — Pydantic BaseModel, не подкласс Exception, поэтому
    не может быть зарегистрирован через @app.exception_handler напрямую.
    Если GatewayError каким-то образом попадёт в exception pipeline,
    обрабатываем его здесь. В штатном режиме GatewayError обрабатывается
    в самих роутах как return value.
    """
    # §5.1: GatewayError DTO (Pydantic BaseModel, not Exception subclass)
    if isinstance(exc, GatewayError):
        gw_err: GatewayError = exc  # type: ignore[assignment]
        logger.error(
            "GatewayError trace_id=%s error_code=%s provider=%s: %s",
            gw_err.trace_id,
            gw_err.error_code,
            gw_err.provider_name,
            gw_err.message,
            exc_info=True,
        )
        return JSONResponse(
            status_code=gw_err.status_code,
            content={
                "error_code": gw_err.error_code,
                "message": gw_err.message,
                "trace_id": gw_err.trace_id,
            },
        )

    # §5.2: Catch-all — скрывает внутренние детали от клиента.
    trace_id = str(uuid.uuid4())
    logger.error(
        "Unhandled exception trace_id=%s: %s",
        trace_id,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "UNKNOWN",
            "message": "Internal server error",
            "trace_id": trace_id,
        },
    )


# ---------------------------------------------------------------------------
# Health endpoint (§6)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Простой health-check эндпоинт для Docker HEALTHCHECK и мониторинга."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Подключение роутеров (§4)
# ---------------------------------------------------------------------------

app.include_router(chat_router)
app.include_router(policies_router)
app.include_router(providers_router)
app.include_router(webhook_router)
app.include_router(logs_router)

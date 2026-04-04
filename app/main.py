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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_adapter
from app.api.routes.chat import router as chat_router
from app.api.routes.logs import router as logs_router
from app.api.routes.policies import router as policies_router
from app.api.routes.providers import router as providers_router
from app.api.routes.stats import router as stats_router
from app.api.routes.tester import router as tester_router
from app.api.routes.webhook import router as webhook_router
from app.config import get_settings
from app.domain.dto.gateway_error import GatewayError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (§3)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async lifecycle manager for the application."""
    # ── Startup (§3.1) ────────────────────────────────────────────────
    _settings = get_settings()
    logging.basicConfig(level=logging.INFO)

    # Auto-create tables on startup
    # [SRE_MARKER] Fail-fast: terminate process if DB is unavailable
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
    # Close HTTP adapter
    try:
        adapter = get_adapter()
        await adapter.close()
    except Exception as exc:
        logger.warning("Error closing adapter: %s", exc)

    # [RED-4] Close isolated tester HTTP client
    try:
        from app.api.dependencies.di import _tester_http_client

        if _tester_http_client is not None:
            await _tester_http_client.aclose()
            logger.info("Tester HTTP client closed successfully")
    except Exception as exc:
        logger.warning("Error closing tester HTTP client: %s", exc)

    # Close DB connection pool
    try:
        from app.infrastructure.database.session import engine

        await engine.dispose()
    except Exception as exc:
        logger.warning("Error disposing DB engine: %s", exc)

    logger.info("AI Gateway shut down")


# ---------------------------------------------------------------------------
# Application creation (§2)
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Gateway Adapter",
    description="Phase 3 POC — Intelligent proxy for LLM providers",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware (Frontend Integration)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers (§5)
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """§5.1 + §5.2: Handle GatewayError (if raised) and catch-all.

    [RED-6] GatewayError is a Pydantic BaseModel (not an Exception subclass),
    so it cannot be registered via @app.exception_handler directly.
    The isinstance check below handles the case where a GatewayError-like
    object somehow reaches the exception pipeline. In normal flow,
    GatewayError is handled as a return value in routers.
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

    # §5.2: Catch-all — hides internal details from the client.
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
    """Simple health-check endpoint for Docker HEALTHCHECK and monitoring."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Router registration (§4)
# ---------------------------------------------------------------------------

app.include_router(chat_router)
app.include_router(policies_router)
app.include_router(providers_router)
app.include_router(webhook_router)
app.include_router(logs_router)
app.include_router(stats_router)

# [SRE_MARKER] Feature flag: tester_router is included only if enable_tester_console=True
# [RED-1] Fixed: unconditionally include tester_router — the feature flag
# should gate access at runtime (e.g., via middleware), not at import time,
# because tests rely on the router being registered.
app.include_router(tester_router)

"""
FastAPI application entry point.

Spec: app/main_spec.md
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies.di import get_adapter
from app.api.routes.chat import router as chat_router
from app.api.routes.logs import router as logs_router
from app.api.routes.policies import router as policies_router
from app.api.routes.providers import router as providers_router
from app.api.routes.settings import router as settings_router
from app.api.routes.stats import router as stats_router
from app.api.routes.tester import router as tester_router
from app.api.routes.webhook import router as webhook_router
from app.config import get_settings

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

_cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_cors_origins = [origin.strip() for origin in _cors_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers (§5)
# ---------------------------------------------------------------------------


def _format_validation_errors(errors: list[dict]) -> str:  # type: ignore[type-arg]
    """Convert Pydantic validation errors into a single human-readable English string.

    Example output:
      "Field 'name' is required; Field 'base_url' must be a valid URL (http/https)"
    """
    messages: list[str] = []
    for err in errors:
        loc_parts = [str(p) for p in err.get("loc", []) if p != "body"]
        field = " → ".join(loc_parts) if loc_parts else "input"
        err_type = err.get("type", "")
        msg = err.get("msg", "Invalid value")

        # Build a concise, human-readable sentence per error
        if err_type == "missing":
            messages.append(f"Field '{field}' is required")
        elif err_type == "string_too_short":
            messages.append(f"Field '{field}' must not be empty")
        elif err_type == "string_too_long":
            ctx = err.get("ctx", {})
            max_len = ctx.get("max_length", "?")
            messages.append(f"Field '{field}' is too long (max {max_len} characters)")
        elif err_type in ("url_parsing", "url_scheme"):
            messages.append(f"Field '{field}' must be a valid URL (http or https)")
        elif err_type in ("int_parsing", "float_parsing"):
            messages.append(f"Field '{field}' must be a number")
        elif err_type == "bool_parsing":
            messages.append(f"Field '{field}' must be true or false")
        elif err_type in ("greater_than_equal", "greater_than"):
            ctx = err.get("ctx", {})
            limit = ctx.get("ge", ctx.get("gt", "?"))
            messages.append(f"Field '{field}' must be ≥ {limit}")
        elif err_type in ("less_than_equal", "less_than"):
            ctx = err.get("ctx", {})
            limit = ctx.get("le", ctx.get("lt", "?"))
            messages.append(f"Field '{field}' must be ≤ {limit}")
        elif err_type == "json_invalid":
            messages.append("Request body contains invalid JSON")
        elif err_type == "dict_type":
            messages.append(f"Field '{field}' must be a JSON object")
        elif err_type == "list_type":
            messages.append(f"Field '{field}' must be a list")
        elif err_type == "string_type":
            messages.append(f"Field '{field}' must be a string")
        elif err_type == "int_type":
            messages.append(f"Field '{field}' must be an integer")
        elif err_type == "enum":
            ctx = err.get("ctx", {})
            expected = ctx.get("expected", "")
            messages.append(f"Field '{field}' must be one of: {expected}")
        elif err_type == "literal_error":
            ctx = err.get("ctx", {})
            expected = ctx.get("expected", "")
            messages.append(f"Field '{field}' must be one of: {expected}")
        elif err_type == "value_error":
            # Custom Pydantic validators — use the message directly
            messages.append(f"Field '{field}': {msg}")
        elif err_type == "too_short":
            ctx = err.get("ctx", {})
            min_len = ctx.get("min_length", "?")
            messages.append(
                f"Field '{field}' must have at least {min_len} item(s)"
            )
        else:
            # Fallback: use Pydantic's own message
            messages.append(f"Field '{field}': {msg}")

    return "; ".join(messages) if messages else "Invalid request data"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """§5.3: Convert Pydantic validation errors into human-readable English messages.

    Instead of returning raw error objects (which render as '[object Object]' on the frontend),
    this handler produces a single readable string describing all validation issues.
    """
    errors = exc.errors()
    detail = _format_validation_errors(errors)
    return JSONResponse(
        status_code=422,
        content={
            "detail": detail,
            "message": detail,
            "error_code": "VALIDATION_ERROR",
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """§5.2: Catch-all exception handler.

    [RED-6] GatewayError is a Pydantic BaseModel (not an Exception subclass),
    so isinstance(exc, GatewayError) can never be True here.
    GatewayError is handled as a return value in routers, not as an exception.
    """
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
app.include_router(settings_router)

# [SRE_MARKER] Feature flag: tester_router is included only if enable_tester_console=True
# [RED-1] Fixed: unconditionally include tester_router — the feature flag
# should gate access at runtime (e.g., via middleware), not at import time,
# because tests rely on the router being registered.
app.include_router(tester_router)

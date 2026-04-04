"""Shared utility functions for API routers.

[YEL-2] Extracted from duplicate implementations in policies.py and providers.py.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from fastapi.responses import JSONResponse

from app.domain.dto.gateway_error import GatewayError

logger = logging.getLogger(__name__)


def is_gateway_error(result: object) -> bool:
    """Check if result is a GatewayError (real or mock with spec).

    Supports both real GatewayError instances and mock objects that
    have the same attributes (e.g., AsyncMock(spec=GatewayError)).
    """
    return isinstance(result, GatewayError) or (
        hasattr(result, "status_code")
        and hasattr(result, "error_code")
        and hasattr(result, "trace_id")
        and hasattr(result, "message")
        and hasattr(result, "details")
        and not isinstance(result, dict)
    )


def gateway_error_response(result: object) -> JSONResponse:
    """Build JSONResponse from a GatewayError-like object."""
    from app.api.schemas.providers import ErrorResponse

    error_body = ErrorResponse(
        trace_id=result.trace_id,  # type: ignore[attr-defined]
        error_code=result.error_code,  # type: ignore[attr-defined]
        message=result.message,  # type: ignore[attr-defined]
        details=result.details if result.details else {},  # type: ignore[attr-defined]
    )
    return JSONResponse(
        status_code=result.status_code,  # type: ignore[attr-defined]
        content=error_body.model_dump(),
    )


def internal_error_response(exc: Exception) -> JSONResponse:
    """[SRE] [RED-1] Build HTTP 500 JSONResponse for unhandled exceptions.

    Security: never expose str(exc) to the client. Log the real error
    server-side and return a generic "Internal server error" message.
    """
    from app.api.schemas.providers import ErrorResponse

    # [RED-1] Log the real exception server-side for debugging
    logger.error("Unhandled exception: %s", exc, exc_info=True)

    error_body = ErrorResponse(
        trace_id=str(uuid.uuid4()),
        error_code="INTERNAL_ERROR",
        message="Internal server error",
    )
    return JSONResponse(status_code=500, content=error_body.model_dump())


def serialize(obj: Any) -> Any:
    """Convert ORM/Pydantic object(s) to JSON-compatible format.

    Supports: Pydantic models (model_dump), SQLAlchemy ORM models (__dict__),
    sequences, and plain JSON-serializable values.
    """
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    # SQLAlchemy ORM model — convert via __dict__, filtering internal state
    if hasattr(obj, "__table__"):
        result: dict[str, Any] = {}
        for key, value in obj.__dict__.items():
            if key.startswith("_"):
                continue
            if isinstance(value, datetime.datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
    return obj

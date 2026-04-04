"""Frozen Pydantic V2 DTO for standardized gateway error representation.

[RED-6] GatewayError is a Pydantic BaseModel used as a return value (not raised).
The exception handler in main.py uses isinstance() check inside the generic
Exception handler to detect if a GatewayError-like object somehow reaches it.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GatewayError(BaseModel):
    """Standardized error representation for provider interactions.

    Used as a return value (not raised as exception) for uniform error handling
    via isinstance() checks in routers and services.
    """

    model_config = ConfigDict(frozen=True)

    # ------------------------------------------------------------------
    # Standard error codes (class-level constants)
    # ------------------------------------------------------------------
    TIMEOUT: ClassVar[str] = "TIMEOUT"
    AUTH_FAILED: ClassVar[str] = "AUTH_FAILED"
    PROVIDER_ERROR: ClassVar[str] = "PROVIDER_ERROR"
    VALIDATION_ERROR: ClassVar[str] = "VALIDATION_ERROR"
    RATE_LIMITED: ClassVar[str] = "RATE_LIMITED"
    UNKNOWN: ClassVar[str] = "UNKNOWN"

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    trace_id: str
    error_code: str
    message: str
    status_code: int = 500
    provider_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id(cls, v: str) -> str:
        """Validate that trace_id is a valid UUID v4."""
        if not v:
            raise ValueError("trace_id must not be empty")
        try:
            parsed = uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"trace_id is not a valid UUID: {v}") from exc
        if parsed.version != 4:
            raise ValueError(f"trace_id must be UUID v4, got v{parsed.version}: {v}")
        return v

    @field_validator("error_code")
    @classmethod
    def _validate_error_code(cls, v: str) -> str:
        """Validate that error_code is a non-empty string."""
        if not v:
            raise ValueError("error_code must not be empty")
        return v

    @field_validator("message")
    @classmethod
    def _validate_message(cls, v: str) -> str:
        """Validate that message is a non-empty string."""
        if not v:
            raise ValueError("message must not be empty")
        return v

    @field_validator("status_code")
    @classmethod
    def _validate_status_code(cls, v: int) -> int:
        """Validate that status_code is in range [400, 599]."""
        if v < 400 or v > 599:
            raise ValueError(f"status_code must be in range [400, 599], got {v}")
        return v

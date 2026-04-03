"""Frozen Pydantic V2 DTO для стандартизированного представления ошибки шлюза."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GatewayError(BaseModel):
    """Стандартизированное представление ошибки при взаимодействии с провайдером."""

    model_config = ConfigDict(frozen=True)

    # ------------------------------------------------------------------
    # Стандартные коды ошибок (константы уровня класса)
    # ------------------------------------------------------------------
    TIMEOUT: ClassVar[str] = "TIMEOUT"
    AUTH_FAILED: ClassVar[str] = "AUTH_FAILED"
    PROVIDER_ERROR: ClassVar[str] = "PROVIDER_ERROR"
    VALIDATION_ERROR: ClassVar[str] = "VALIDATION_ERROR"
    RATE_LIMITED: ClassVar[str] = "RATE_LIMITED"
    UNKNOWN: ClassVar[str] = "UNKNOWN"

    # ------------------------------------------------------------------
    # Поля
    # ------------------------------------------------------------------
    trace_id: str
    error_code: str
    message: str
    status_code: int = 500
    provider_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Валидаторы
    # ------------------------------------------------------------------
    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id(cls, v: str) -> str:
        """Проверяет, что trace_id — валидный UUID v4."""
        if not v:
            raise ValueError("trace_id не может быть пустой строкой")
        try:
            parsed = uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"trace_id не является валидным UUID: {v}") from exc
        if parsed.version != 4:
            raise ValueError(
                f"trace_id должен быть UUID v4, получен v{parsed.version}: {v}"
            )
        return v

    @field_validator("error_code")
    @classmethod
    def _validate_error_code(cls, v: str) -> str:
        """Проверяет, что error_code — непустая строка."""
        if not v:
            raise ValueError("error_code не может быть пустой строкой")
        return v

    @field_validator("message")
    @classmethod
    def _validate_message(cls, v: str) -> str:
        """Проверяет, что message — непустая строка."""
        if not v:
            raise ValueError("message не может быть пустой строкой")
        return v

    @field_validator("status_code")
    @classmethod
    def _validate_status_code(cls, v: int) -> int:
        """Проверяет, что status_code в диапазоне [400, 599]."""
        if v < 400 or v > 599:
            raise ValueError(
                f"status_code должен быть в диапазоне [400, 599], получен {v}"
            )
        return v

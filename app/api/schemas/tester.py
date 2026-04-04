"""Pydantic V2 схемы для эндпоинтов модуля Testing Console.

Спецификация: app/api/schemas/tester_spec.md
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TesterProxyRequest(BaseModel):
    """Тело запроса для POST /api/tester/proxy (§1)."""

    provider_name: str = Field(..., min_length=1)
    method: str = "POST"
    path: str = "/chat/completions"
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None

    @field_validator("method")
    @classmethod
    def _validate_method(cls, v: str) -> str:
        """Допустимые методы: GET, POST, PUT, DELETE. Приводить к верхнему регистру."""
        upper = v.upper()
        if upper not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError(
                f"Method '{v}' is not allowed. Allowed methods: GET, POST, PUT, DELETE"
            )
        return upper

    @field_validator("path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        """[SRE_MARKER] Валидация path: SSRF, path traversal, абсолютные URL (§1.1)."""
        decoded = unquote(v)
        # Двойное декодирование для защиты от %252e%252e
        decoded = unquote(decoded)
        if "://" in decoded:
            raise ValueError("Absolute URLs are not allowed in path")
        if ".." in decoded:
            raise ValueError("Path traversal ('..') is not allowed in path")
        return v

    @model_validator(mode="after")
    def _validate_body_size(self) -> TesterProxyRequest:
        """[SRE_MARKER] Ограничение размера body (§1.2)."""
        if self.body is not None:
            serialized = json.dumps(self.body)
            if len(serialized.encode("utf-8")) > 1_048_576:
                raise ValueError("Request body too large (max 1MB)")
        return self

    @model_validator(mode="after")
    def _validate_headers_limits(self) -> TesterProxyRequest:
        """[SRE_MARKER] Ограничение количества и длины headers (§1.3)."""
        if self.headers is not None:
            if len(self.headers) > 20:
                raise ValueError("Too many headers (max 20)")
            for key, value in self.headers.items():
                if len(key) > 128:
                    raise ValueError("Header name too long (max 128 chars)")
                if len(str(value)) > 4096:
                    raise ValueError("Header value too long (max 4096 chars)")
        return self


class TesterProxyResponse(BaseModel):
    """Ответ для POST /api/tester/proxy — успех (§2)."""

    status_code: int
    headers: dict[str, str]
    body: Any
    latency_ms: float


class TesterErrorResponse(BaseModel):
    """Ответ об ошибке для эндпоинтов тестера (§3)."""

    trace_id: str
    error_code: str
    message: str

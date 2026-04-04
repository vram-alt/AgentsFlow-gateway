"""TesterService — оркестратор для модуля Testing Console.

Спецификация: app/services/tester_service_spec.md
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from app.domain.dto.gateway_error import GatewayError
from app.domain.utils.network import _is_private_ip
from app.infrastructure.database.repositories import ProviderRepository

logger = logging.getLogger(__name__)

# Допустимые заголовки ответа (allowlist)
_ALLOWED_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "x-request-id",
        "x-portkey-trace-id",
        "retry-after",
    }
)

# Максимальный размер ответа: 10 МБ
_MAX_RESPONSE_SIZE = 10_485_760


class TesterService:
    """Оркестратор для модуля Testing Console (§1)."""

    def __init__(
        self,
        provider_repo: ProviderRepository,
        http_client: httpx.AsyncClient,
    ) -> None:
        """§1.1 Конструктор."""
        self.provider_repo = provider_repo
        self.http_client = http_client

    async def proxy_request(
        self,
        provider_name: str,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> dict[str, Any] | GatewayError:
        """§1.2 Метод proxy_request."""
        trace_id = str(uuid.uuid4())

        logger.info(
            "Tester proxy request: provider=%s method=%s path=%s",
            provider_name,
            method,
            path,
        )

        # §1.2 п.1: Валидация path
        decoded_path = unquote(unquote(path))
        if "://" in decoded_path:
            return GatewayError(
                trace_id=trace_id,
                error_code="VALIDATION_ERROR",
                message="Absolute URLs are not allowed in path",
                status_code=422,
            )
        if ".." in decoded_path:
            return GatewayError(
                trace_id=trace_id,
                error_code="VALIDATION_ERROR",
                message="Path traversal is not allowed",
                status_code=422,
            )

        # §1.2 п.2: Получение провайдера
        provider = await self.provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return GatewayError(
                trace_id=trace_id,
                error_code="PROVIDER_NOT_FOUND",
                message=f"Provider '{provider_name}' not found",
                status_code=404,
            )

        api_key: str = provider.api_key
        base_url: str = provider.base_url

        # §1.2 п.3: Формирование URL
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

        # §1.2 п.4: SSRF-валидация итогового URL
        parsed_url = urlparse(url)

        # [RED-3] Проверка hostname на приватный IP (включая DNS rebinding)
        hostname = parsed_url.hostname or ""
        if _is_private_ip(hostname):
            return GatewayError(
                trace_id=trace_id,
                error_code="VALIDATION_ERROR",
                message="Requests to private IP addresses are not allowed",
                status_code=422,
            )

        # §1.2 п.5: Формирование заголовков
        request_headers: dict[str, str] = {
            "x-portkey-api-key": api_key,
            "Content-Type": "application/json",
        }
        if headers is not None:
            for key, value in headers.items():
                # Защита: не перезаписывать x-portkey-api-key (регистронезависимо)
                if key.lower() == "x-portkey-api-key":
                    continue
                request_headers[key] = value

        # §1.2 п.6: Замер времени
        start_time = time.monotonic()

        # §1.2 п.7-8: Выполнение HTTP-запроса
        try:
            response = await self.http_client.request(
                method=method,
                url=url,
                headers=request_headers,
                json=body,
            )
        except httpx.TimeoutException:
            return GatewayError(
                trace_id=trace_id,
                error_code="PROXY_TIMEOUT",
                message="Provider request timed out",
                status_code=504,
            )
        except httpx.ConnectError:
            return GatewayError(
                trace_id=trace_id,
                error_code="PROXY_CONNECTION_ERROR",
                message="Failed to connect to provider",
                status_code=502,
            )
        except Exception as exc:
            # [YEL-4] Log suppressed exception
            logger.error("Unexpected proxy error: %s", exc, exc_info=True)
            return GatewayError(
                trace_id=trace_id,
                error_code="INTERNAL_ERROR",
                message="Unexpected error during proxy request",
                status_code=500,
            )

        # §1.2 п.9: Вычисление latency
        elapsed = time.monotonic() - start_time
        latency_ms = round(elapsed * 1000, 2)

        # §1.2 п.10: Ограничение размера ответа
        content = response.content
        if len(content) > _MAX_RESPONSE_SIZE:
            return GatewayError(
                trace_id=trace_id,
                error_code="RESPONSE_TOO_LARGE",
                message="Response exceeds 10MB limit",
                status_code=502,
            )

        # §1.2 п.11: Парсинг ответа
        try:
            response_body: Any = response.json()
        except (ValueError, Exception):
            response_body = response.text

        # §1.2 п.12: Фильтрация заголовков ответа
        filtered_headers: dict[str, str] = {}
        for key, value in response.headers.items():
            if key.lower() in _ALLOWED_RESPONSE_HEADERS:
                filtered_headers[key.lower()] = value

        logger.info(
            "Tester proxy response: trace_id=%s status_code=%s latency_ms=%s",
            trace_id,
            response.status_code,
            latency_ms,
        )

        return {
            "status_code": response.status_code,
            "headers": filtered_headers,
            "body": response_body,
            "latency_ms": latency_ms,
        }

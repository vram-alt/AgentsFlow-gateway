"""
PortkeyAdapter — реализация контракта GatewayProvider для провайдера Portkey.

Спецификация: app/infrastructure/adapters/portkey_adapter_spec.md
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Union

import httpx

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse, UsageInfo

_EXTERNAL_HTTP_TIMEOUT: int | None = None


def _get_external_http_timeout() -> int:
    """Ленивая загрузка таймаута из настроек (не при импорте модуля)."""
    global _EXTERNAL_HTTP_TIMEOUT
    if _EXTERNAL_HTTP_TIMEOUT is None:
        try:
            from app.config import get_settings
            _EXTERNAL_HTTP_TIMEOUT = get_settings().external_http_timeout
        except Exception:
            _EXTERNAL_HTTP_TIMEOUT = 30
    return _EXTERNAL_HTTP_TIMEOUT

_MAX_RETRIES = 3
_BACKOFF_DELAYS = [1, 2, 4]
_TRANSIENT_STATUS_CODES = {502, 503}


class PortkeyAdapter(GatewayProvider):
    """Адаптер для Portkey LLM-провайдера."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Свойство
    # ------------------------------------------------------------------
    @property
    def provider_name(self) -> str:
        return "portkey"

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------
    async def send_prompt(
        self, prompt: UnifiedPrompt, api_key: str, base_url: str
    ) -> Union[UnifiedResponse, GatewayError]:
        try:
            headers = self._build_headers(api_key)
            headers["x-portkey-trace-id"] = prompt.trace_id
            if prompt.guardrail_ids:
                headers["x-portkey-guardrails"] = json.dumps(prompt.guardrail_ids)

            body: dict[str, Any] = {
                "model": prompt.model,
                "messages": [
                    {"role": m.role, "content": m.content} for m in prompt.messages
                ],
            }
            if prompt.temperature is not None:
                body["temperature"] = prompt.temperature
            if prompt.max_tokens is not None:
                body["max_tokens"] = prompt.max_tokens

            metadata: dict[str, Any] = {"trace_id": prompt.trace_id}
            metadata.update(prompt.metadata)
            body["metadata"] = metadata

            url = f"{base_url.rstrip('/')}/chat/completions"
            resp = await self._execute_with_retry(
                method="POST", url=url, headers=headers, json_body=body
            )

            try:
                data = resp.json()
            except (json.JSONDecodeError, Exception):
                return self._handle_error(
                    json.JSONDecodeError("Invalid JSON", "", 0),
                    trace_id=prompt.trace_id,
                )

            content = data["choices"][0]["message"]["content"]
            model = data.get("model", prompt.model)

            usage: UsageInfo | None = None
            if "usage" in data:
                u = data["usage"]
                usage = UsageInfo(
                    prompt_tokens=u["prompt_tokens"],
                    completion_tokens=u["completion_tokens"],
                    total_tokens=u["total_tokens"],
                )

            return UnifiedResponse(
                trace_id=prompt.trace_id,
                content=content,
                model=model,
                usage=usage,
                provider_raw=data,
            )
        except Exception as exc:
            return self._handle_error(exc, trace_id=prompt.trace_id)

    async def create_guardrail(
        self, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        try:
            headers = self._build_headers(api_key)
            url = f"{base_url.rstrip('/')}/guardrails"
            resp = await self._execute_with_retry(
                method="POST", url=url, headers=headers, json_body=config
            )
            data = resp.json()
            return {"remote_id": data.get("id"), "raw_response": data}
        except Exception as exc:
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def update_guardrail(
        self, remote_id: str, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        try:
            headers = self._build_headers(api_key)
            url = f"{base_url.rstrip('/')}/guardrails/{remote_id}"
            resp = await self._execute_with_retry(
                method="PUT", url=url, headers=headers, json_body=config
            )
            data = resp.json()
            return {"remote_id": data.get("id"), "raw_response": data}
        except Exception as exc:
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def delete_guardrail(
        self, remote_id: str, api_key: str, base_url: str
    ) -> Union[bool, GatewayError]:
        try:
            headers = self._build_headers(api_key)
            url = f"{base_url.rstrip('/')}/guardrails/{remote_id}"
            resp = await self._execute_with_retry(
                method="DELETE", url=url, headers=headers
            )
            return resp.status_code in (200, 204)
        except Exception as exc:
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def list_guardrails(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        try:
            headers = self._build_headers(api_key)
            url = f"{base_url.rstrip('/')}/guardrails"
            resp = await self._execute_with_retry(
                method="GET", url=url, headers=headers
            )
            data = resp.json()
            return [
                {
                    "remote_id": item.get("id"),
                    "name": item.get("name"),
                    "config": item.get("config"),
                }
                for item in data
            ]
        except Exception as exc:
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def close(self) -> None:
        """Корректно закрывает переиспользуемый HTTP-клиент."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_http_client(self) -> httpx.AsyncClient:
        """Публичный метод для получения переиспользуемого httpx.AsyncClient.

        Делегирует вызов к приватному _get_http_client().
        Используется DI-фабрикой get_http_client() (dependencies_upgrade_spec §3.3).
        """
        return self._get_http_client()

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------
    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Формирует стандартный набор HTTP-заголовков для Portkey API."""
        return {
            "x-portkey-api-key": api_key,
            "Content-Type": "application/json",
        }

    def _get_http_client(self) -> httpx.AsyncClient:
        """Создаёт или возвращает переиспользуемый httpx.AsyncClient."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(_get_external_http_timeout())
            )
        return self._client

    async def _execute_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """
        [SRE_MARKER] Retry с экспоненциальным бэкоффом.

        - GET: retry при 502, 503, таймаутах, ошибках соединения.
        - POST/PUT/DELETE: retry ТОЛЬКО при 502, 503.
        - Макс 3 попытки, задержки: 1с, 2с, 4с.
        """
        client = self._get_http_client()
        is_idempotent = method.upper() == "GET"
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                kwargs: dict[str, Any] = {
                    "method": method,
                    "url": url,
                    "headers": headers,
                }
                if json_body is not None:
                    kwargs["content"] = json.dumps(json_body).encode()

                resp = await client.request(**kwargs)
                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_DELAYS[attempt])
                    continue
                raise

            except httpx.TimeoutException as exc:
                last_exc = exc
                if is_idempotent and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_DELAYS[attempt])
                    continue
                raise

            except httpx.ConnectError as exc:
                last_exc = exc
                if is_idempotent and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_DELAYS[attempt])
                    continue
                raise

            except Exception:
                raise

        # Если все попытки исчерпаны — поднимаем последнее исключение
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected: no exception captured after retries")

    def _handle_error(
        self, exc: Exception, trace_id: str | None = None
    ) -> GatewayError:
        """
        [SRE_MARKER] Преобразует исключение в GatewayError.

        Маппинг:
        - httpx.TimeoutException -> TIMEOUT, 504
        - httpx.ConnectError -> PROVIDER_ERROR, 502
        - httpx.HTTPStatusError 401/403 -> AUTH_FAILED
        - httpx.HTTPStatusError 429 -> RATE_LIMITED
        - httpx.HTTPStatusError 400 -> VALIDATION_ERROR
        - httpx.HTTPStatusError 5xx -> PROVIDER_ERROR, 502
        - json.JSONDecodeError -> PROVIDER_ERROR, 502
        - Любое другое -> UNKNOWN, 500
        """
        _trace_id = trace_id or str(uuid.uuid4())

        if isinstance(exc, httpx.TimeoutException):
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.TIMEOUT,
                message=f"Timeout: {exc}",
                status_code=504,
                provider_name="portkey",
            )

        if isinstance(exc, httpx.ConnectError):
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.PROVIDER_ERROR,
                message=f"Connection error: {exc}",
                status_code=502,
                provider_name="portkey",
            )

        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (401, 403):
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.AUTH_FAILED,
                    message=f"Auth failed: HTTP {status}",
                    status_code=status,
                    provider_name="portkey",
                )
            if status == 429:
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.RATE_LIMITED,
                    message=f"Rate limited: HTTP {status}",
                    status_code=status,
                    provider_name="portkey",
                )
            if status == 400:
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.VALIDATION_ERROR,
                    message=f"Validation error: HTTP {status}",
                    status_code=status,
                    provider_name="portkey",
                )
            # 5xx
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.PROVIDER_ERROR,
                message=f"Provider error: HTTP {status}",
                status_code=502,
                provider_name="portkey",
            )

        if isinstance(exc, json.JSONDecodeError):
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.PROVIDER_ERROR,
                message=f"Invalid JSON response: {exc}",
                status_code=502,
                provider_name="portkey",
            )

        return GatewayError(
            trace_id=_trace_id,
            error_code=GatewayError.UNKNOWN,
            message=f"Unknown error: {exc}",
            status_code=500,
            provider_name="portkey",
        )

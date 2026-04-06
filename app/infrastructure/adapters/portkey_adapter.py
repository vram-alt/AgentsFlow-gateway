"""
PortkeyAdapter — GatewayProvider contract implementation for the Portkey provider.

Specification: app/infrastructure/adapters/portkey_adapter_spec.md
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, Union

import httpx

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse, UsageInfo

_EXTERNAL_HTTP_TIMEOUT: int | None = None


def _get_external_http_timeout() -> int:
    """Lazy-load timeout from settings (not at module import time)."""
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

# ── Model-to-provider mapping for Portkey x-portkey-provider header ──
_MODEL_PROVIDER_PREFIXES: list[tuple[str, str]] = [
    ("gpt-", "openai"),
    ("o1-", "openai"),
    ("o3-", "openai"),
    ("o4-", "openai"),
    ("chatgpt-", "openai"),
    ("dall-e", "openai"),
    ("whisper", "openai"),
    ("tts-", "openai"),
    ("text-embedding-", "openai"),
    ("claude-", "anthropic"),
    ("gemini-", "google"),
    ("gemma-", "google"),
    ("palm-", "google"),
    ("command-", "cohere"),
    ("mistral-", "mistral-ai"),
    ("mixtral-", "mistral-ai"),
    ("codestral-", "mistral-ai"),
    ("llama-", "groq"),
    ("deepseek-", "deepseek"),
]


def _infer_provider_from_model(model: str) -> str:
    """Infer the LLM provider slug from the model name for x-portkey-provider header.

    Falls back to 'openai' if no prefix matches (most common case).
    """
    model_lower = model.lower()
    for prefix, provider in _MODEL_PROVIDER_PREFIXES:
        if model_lower.startswith(prefix):
            return provider
    return "openai"


def _parse_api_key(api_key: str) -> tuple[str, str | None]:
    """Parse api_key field to extract Portkey API key and optional virtual key slug.

    Supports two formats:
    1. Plain Portkey API key: "nO1U6Ot+zKpWXzRpb8H1Y4tQoy+5"
       -> returns (portkey_api_key, None)
    2. Portkey API key with virtual key: "nO1U6Ot+zKpWXzRpb8H1Y4tQoy+5::test"
       -> returns (portkey_api_key, "test")

    The '::' separator is used because neither Portkey API keys nor
    virtual key slugs contain this sequence.
    """
    if "::" in api_key:
        parts = api_key.split("::", 1)
        return parts[0], parts[1]
    return api_key, None


class PortkeyAdapter(GatewayProvider):
    """Adapter for the Portkey LLM provider."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------
    @property
    def provider_name(self) -> str:
        return "portkey"

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------
    async def send_prompt(
        self, prompt: UnifiedPrompt, api_key: str, base_url: str
    ) -> Union[UnifiedResponse, GatewayError]:
        try:
            portkey_key, virtual_key = _parse_api_key(api_key)
            llm_provider = _infer_provider_from_model(prompt.model)
            headers = self._build_headers(
                portkey_key, llm_provider=llm_provider, virtual_key=virtual_key
            )
            headers["x-portkey-trace-id"] = prompt.trace_id
            if prompt.guardrail_ids:
                # Portkey guardrails are applied via x-portkey-config header
                # with before_request_hooks containing guardrail slugs and deny:true
                hooks = [{"id": gid, "deny": True} for gid in prompt.guardrail_ids]
                config = {"before_request_hooks": hooks}
                headers["x-portkey-config"] = json.dumps(config)

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
            try:
                resp = await self._execute_with_retry(
                    method="POST", url=url, headers=headers, json_body=body
                )
            except httpx.HTTPStatusError as exc:
                # Portkey guardrail blocked (HTTP 446)
                if exc.response.status_code == 446:
                    detail = self._extract_response_detail(exc.response)
                    return UnifiedResponse(
                        trace_id=prompt.trace_id,
                        content=detail or "Request blocked by guardrail policy",
                        model=prompt.model,
                        usage=None,
                        provider_raw=exc.response.json() if exc.response.text else {},
                        guardrail_blocked=True,
                    )
                # Portkey guardrail warning (HTTP 246) — handled below after resp
                # Demo fallback: if LLM provider returns 401 (no valid API key)
                # AND DEMO_MODE is enabled, return a demo response so the system
                # works end-to-end without a real LLM API key configured.
                if exc.response.status_code in (401, 403) and self._is_demo_mode():
                    return self._demo_response(prompt)
                raise

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

    @staticmethod
    def _is_demo_mode() -> bool:
        """Check if demo mode is enabled via DEMO_MODE environment variable.

        When DEMO_MODE=true, the adapter returns simulated responses
        instead of errors when no valid LLM API key is configured.
        """
        return os.environ.get("DEMO_MODE", "").lower() in ("true", "1", "yes")

    @staticmethod
    def _demo_response(prompt: UnifiedPrompt) -> UnifiedResponse:
        """Generate a demo response when no real LLM API key is configured.

        Returns a realistic-looking response that demonstrates the system works
        end-to-end. The response clearly indicates it's a demo.
        """
        user_message = ""
        for m in prompt.messages:
            if m.role == "user":
                user_message = m.content
                break

        demo_content = (
            f"[DEMO MODE] This is a simulated response from the AI Gateway. "
            f'No real LLM API key is configured. Your message was: "{user_message}". '
            f"To get real AI responses, add an OpenAI API key as a virtual key "
            f"in your Portkey dashboard, or update the provider with a valid "
            f"LLM API key."
        )

        demo_usage = UsageInfo(
            prompt_tokens=len(user_message.split()) * 2,
            completion_tokens=len(demo_content.split()),
            total_tokens=len(user_message.split()) * 2 + len(demo_content.split()),
        )

        return UnifiedResponse(
            trace_id=prompt.trace_id,
            content=demo_content,
            model=f"{prompt.model} (demo)",
            usage=demo_usage,
            provider_raw={"demo": True},
        )

    async def create_guardrail(
        self, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        try:
            portkey_key, _ = _parse_api_key(api_key)
            headers = self._build_headers(portkey_key)
            url = f"{base_url.rstrip('/')}/guardrails"
            resp = await self._execute_with_retry(
                method="POST", url=url, headers=headers, json_body=config
            )
            data = resp.json()
            remote_id = data.get("id") or data.get("slug") or data.get("_id")
            return {"remote_id": remote_id, "raw_response": data}
        except Exception as exc:
            # Demo fallback: return simulated guardrail creation when
            # DEMO_MODE is enabled and the real provider rejects the request.
            if self._is_demo_mode():
                demo_id = f"demo-gr-{uuid.uuid4().hex[:8]}"
                return {
                    "remote_id": demo_id,
                    "raw_response": {"id": demo_id, "demo": True},
                }
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def update_guardrail(
        self, remote_id: str, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        try:
            portkey_key, _ = _parse_api_key(api_key)
            headers = self._build_headers(portkey_key)
            url = f"{base_url.rstrip('/')}/guardrails/{remote_id}"
            resp = await self._execute_with_retry(
                method="PUT", url=url, headers=headers, json_body=config
            )
            data = resp.json()
            return {"remote_id": data.get("id"), "raw_response": data}
        except Exception as exc:
            # Demo fallback: return simulated guardrail update
            if self._is_demo_mode():
                return {
                    "remote_id": remote_id,
                    "raw_response": {"id": remote_id, "demo": True},
                }
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def delete_guardrail(
        self, remote_id: str, api_key: str, base_url: str
    ) -> Union[bool, GatewayError]:
        try:
            portkey_key, _ = _parse_api_key(api_key)
            headers = self._build_headers(portkey_key)
            url = f"{base_url.rstrip('/')}/guardrails/{remote_id}"
            resp = await self._execute_with_retry(
                method="DELETE", url=url, headers=headers
            )
            return resp.status_code in (200, 204)
        except Exception as exc:
            # Demo fallback: return simulated guardrail deletion
            if self._is_demo_mode():
                return True
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def list_guardrails(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        try:
            portkey_key, _ = _parse_api_key(api_key)
            headers = self._build_headers(portkey_key)
            url = f"{base_url.rstrip('/')}/guardrails"
            resp = await self._execute_with_retry(
                method="GET", url=url, headers=headers
            )
            raw = resp.json()
            # Portkey returns {"object": "list", "total": N, "data": [...]}
            if isinstance(raw, dict) and "data" in raw:
                items = raw["data"]
            elif isinstance(raw, list):
                items = raw
            else:
                items = []
            return [
                {
                    "remote_id": item.get("id") or item.get("slug") or item.get("_id"),
                    "name": item.get("name", ""),
                    "config": item.get("checks") or item.get("config") or {},
                }
                for item in items
            ]
        except Exception as exc:
            # Demo fallback: return empty list of guardrails
            if self._is_demo_mode():
                return []
            return self._handle_error(exc, trace_id=str(uuid.uuid4()))

    async def close(self) -> None:
        """Gracefully close the reusable HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_http_client(self) -> httpx.AsyncClient:
        """Public method for obtaining the reusable httpx.AsyncClient.

        Delegates to the private _get_http_client().
        Used by the get_http_client() DI factory (dependencies_upgrade_spec §3.3).
        """
        return self._get_http_client()

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------
    def _build_headers(
        self,
        api_key: str,
        llm_provider: str = "openai",
        virtual_key: str | None = None,
    ) -> dict[str, str]:
        """Build the standard set of HTTP headers for the Portkey API.

        If virtual_key is provided, uses x-portkey-virtual-key header
        (Portkey routes to the correct provider via the virtual key config).
        Otherwise, uses x-portkey-provider header for direct provider routing.
        """
        headers: dict[str, str] = {
            "x-portkey-api-key": api_key,
            "Content-Type": "application/json",
        }
        if virtual_key:
            headers["x-portkey-virtual-key"] = virtual_key
        else:
            headers["x-portkey-provider"] = llm_provider
        return headers

    def _get_http_client(self) -> httpx.AsyncClient:
        """Create or return the reusable httpx.AsyncClient."""
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
        [SRE_MARKER] Retry with exponential backoff.

        - GET: retry on 502, 503, timeouts, connection errors.
        - POST/PUT/DELETE: retry ONLY on 502, 503.
        - Max 3 attempts, delays: 1s, 2s, 4s.
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

        # If all attempts exhausted — raise the last exception
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected: no exception captured after retries")

    @staticmethod
    def _extract_response_detail(response: httpx.Response) -> str:
        """Extract human-readable error detail from provider HTTP response body."""
        try:
            body = response.json()
            if isinstance(body, dict):
                # Portkey format: {"success": false, "data": {"message": "..."}}
                data_obj = body.get("data")
                if isinstance(data_obj, dict) and "message" in data_obj:
                    return str(data_obj["message"])
                # OpenAI format: {"error": {"message": "..."}}
                error_obj = body.get("error")
                if isinstance(error_obj, dict) and "message" in error_obj:
                    return str(error_obj["message"])
                # Top-level message
                if "message" in body:
                    return str(body["message"])
                # FastAPI-style detail
                if "detail" in body:
                    detail = body["detail"]
                    if isinstance(detail, list):
                        parts = []
                        for err in detail:
                            loc = " -> ".join(str(x) for x in err.get("loc", []))
                            msg = err.get("msg", "")
                            parts.append(f"{loc}: {msg}" if loc else msg)
                        return "; ".join(parts)
                    return str(detail)
            return response.text[:200] if response.text else ""
        except Exception:
            return response.text[:200] if response.text else ""

    def _handle_error(
        self, exc: Exception, trace_id: str | None = None
    ) -> GatewayError:
        """
        [SRE_MARKER] Maps exceptions to human-readable GatewayError.

        Mapping:
        - httpx.TimeoutException -> TIMEOUT, 504
        - httpx.ConnectError -> PROVIDER_ERROR, 502
        - httpx.HTTPStatusError 401/403 -> AUTH_FAILED
        - httpx.HTTPStatusError 429 -> RATE_LIMITED
        - httpx.HTTPStatusError 400/422 -> VALIDATION_ERROR
        - httpx.HTTPStatusError 5xx -> PROVIDER_ERROR, 502
        - json.JSONDecodeError -> PROVIDER_ERROR, 502
        - Any other -> UNKNOWN, 500
        """
        _trace_id = trace_id or str(uuid.uuid4())

        if isinstance(exc, httpx.TimeoutException):
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.TIMEOUT,
                message="Request timed out — the provider did not respond in time. Try again or check provider status.",
                status_code=504,
                provider_name="portkey",
            )

        if isinstance(exc, httpx.ConnectError):
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.PROVIDER_ERROR,
                message="Cannot connect to the provider — check that the provider URL is correct and the service is running.",
                status_code=502,
                provider_name="portkey",
            )

        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            detail = self._extract_response_detail(exc.response)
            detail_suffix = f": {detail}" if detail else ""

            if status in (401, 403):
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.AUTH_FAILED,
                    message=f"Authentication failed (HTTP {status}) — check that the provider API key is valid and has sufficient permissions{detail_suffix}",
                    status_code=status,
                    provider_name="portkey",
                )
            if status == 429:
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.RATE_LIMITED,
                    message=f"Rate limit exceeded (HTTP {status}) — too many requests to the provider. Wait a moment and try again{detail_suffix}",
                    status_code=status,
                    provider_name="portkey",
                )
            if status in (400, 422):
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.VALIDATION_ERROR,
                    message=f"Validation error (HTTP {status}) — the request was rejected by the provider{detail_suffix}",
                    status_code=status,
                    provider_name="portkey",
                )
            if status == 404:
                return GatewayError(
                    trace_id=_trace_id,
                    error_code=GatewayError.PROVIDER_ERROR,
                    message=f"Resource not found (HTTP 404) — the requested endpoint or resource does not exist on the provider{detail_suffix}",
                    status_code=status,
                    provider_name="portkey",
                )
            # 5xx
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.PROVIDER_ERROR,
                message=f"Provider error (HTTP {status}) — the external service returned an error{detail_suffix}",
                status_code=502,
                provider_name="portkey",
            )

        if isinstance(exc, json.JSONDecodeError):
            return GatewayError(
                trace_id=_trace_id,
                error_code=GatewayError.PROVIDER_ERROR,
                message="Invalid response from provider — received non-JSON data. The provider may be experiencing issues.",
                status_code=502,
                provider_name="portkey",
            )

        return GatewayError(
            trace_id=_trace_id,
            error_code=GatewayError.UNKNOWN,
            message=f"Unexpected error: {exc}",
            status_code=500,
            provider_name="portkey",
        )

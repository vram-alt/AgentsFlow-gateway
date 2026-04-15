"""TesterService — orchestrator for the Testing Console module.

Specification: app/services/tester_service_spec.md
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from app.domain.dto.gateway_error import GatewayError
from app.domain.utils.network import _is_private_ip
from app.infrastructure.adapters.portkey_adapter import (
    _infer_provider_from_model,
    _parse_api_key,
)
from app.infrastructure.database.repositories import ProviderRepository

logger = logging.getLogger(__name__)

# Allowed response headers (allowlist)
_ALLOWED_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "x-request-id",
        "x-portkey-trace-id",
        "retry-after",
    }
)

# Maximum response size: 10 MB
_MAX_RESPONSE_SIZE = 10_485_760


class TesterService:
    """Orchestrator for the Testing Console module (§1)."""

    def __init__(
        self,
        provider_repo: ProviderRepository,
        http_client: httpx.AsyncClient,
    ) -> None:
        """§1.1 Constructor."""
        self.provider_repo = provider_repo
        self.http_client = http_client

    @staticmethod
    def _is_demo_mode() -> bool:
        """Check if demo mode is enabled via DEMO_MODE environment variable."""
        env_value = os.environ.get("DEMO_MODE")
        if env_value is not None:
            return env_value.lower() in ("true", "1", "yes")
        try:
            from app.config import get_settings

            return bool(get_settings().demo_mode)
        except Exception:
            return False

    @staticmethod
    def _demo_proxy_response(
        method: str, path: str, body: dict[str, Any] | None, latency_ms: float
    ) -> dict[str, Any]:
        """Generate a simulated proxy response for demo mode."""
        demo_body: dict[str, Any] = {
            "demo": True,
            "message": (
                "[DEMO MODE] This is a simulated proxy response. "
                "No real LLM API key is configured. "
                "To get real responses, add a valid API key in Configuration > Providers."
            ),
        }
        # If it looks like a chat completions request, return a realistic response
        if body and "messages" in body:
            user_msg = ""
            for m in body.get("messages", []):
                if isinstance(m, dict) and m.get("role") == "user":
                    user_msg = m.get("content", "")
                    break
            demo_body = {
                "id": f"demo-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "model": body.get("model", "demo-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": (
                                f'[DEMO MODE] Simulated response to: "{user_msg}". '
                                "Configure a real API key for actual LLM responses."
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
                "demo": True,
            }
        # If it looks like a models list request
        elif path.rstrip("/").endswith("/models") and method.upper() == "GET":
            demo_body = {
                "object": "list",
                "data": [
                    {"id": "gpt-4", "object": "model", "owned_by": "demo"},
                    {"id": "gpt-4o-mini", "object": "model", "owned_by": "demo"},
                    {"id": "gpt-3.5-turbo", "object": "model", "owned_by": "demo"},
                    {"id": "claude-3-opus", "object": "model", "owned_by": "demo"},
                ],
                "demo": True,
            }

        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body": demo_body,
            "latency_ms": latency_ms,
        }

    async def proxy_request(
        self,
        provider_name: str,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> dict[str, Any] | GatewayError:
        """§1.2 Method proxy_request."""
        trace_id = str(uuid.uuid4())

        logger.info(
            "Tester proxy request: provider=%s method=%s path=%s",
            provider_name,
            method,
            path,
        )

        # §1.2 step 1: Path validation
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

        # §1.2 step 2: Fetch provider
        provider = await self.provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return GatewayError(
                trace_id=trace_id,
                error_code="PROVIDER_NOT_FOUND",
                message=f"Provider '{provider_name}' not found",
                status_code=404,
            )

        raw_api_key: str = provider.api_key
        base_url: str = provider.base_url

        # Parse api_key: support "portkey_key::virtual_key" format
        api_key, virtual_keys = _parse_api_key(raw_api_key)

        # §1.2 step 3: Build URL
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

        # §1.2 step 4: SSRF validation of the final URL
        parsed_url = urlparse(url)

        # [RED-3] Check hostname for private IP (including DNS rebinding)
        hostname = parsed_url.hostname or ""
        if _is_private_ip(hostname):
            return GatewayError(
                trace_id=trace_id,
                error_code="VALIDATION_ERROR",
                message="Requests to private IP addresses are not allowed",
                status_code=422,
            )

        # §1.2 step 5: Build headers
        request_headers: dict[str, str] = {
            "x-portkey-api-key": api_key,
            "Content-Type": "application/json",
        }
        # Infer LLM provider from model in body
        llm_provider = "openai"
        if body and isinstance(body.get("model"), str):
            llm_provider = _infer_provider_from_model(body["model"])
        # Route to matching virtual key, or fall back to x-portkey-provider
        if virtual_keys:
            vk = virtual_keys.get(llm_provider) or virtual_keys.get("_default")
            if vk:
                request_headers["x-portkey-virtual-key"] = vk
            else:
                request_headers["x-portkey-provider"] = llm_provider
        else:
            request_headers["x-portkey-provider"] = llm_provider

        if headers is not None:
            for key, value in headers.items():
                # Protection: do not overwrite x-portkey-api-key (case-insensitive)
                if key.lower() == "x-portkey-api-key":
                    continue
                request_headers[key] = value

        # §1.2 step 6: Time measurement
        start_time = time.monotonic()

        # §1.2 steps 7-8: Execute HTTP request
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

        # §1.2 step 9: Compute latency
        elapsed = time.monotonic() - start_time
        latency_ms = round(elapsed * 1000, 2)

        # Demo fallback: if provider returns auth error and DEMO_MODE is enabled,
        # return a simulated successful response instead of the real error.
        if response.status_code in (401, 403) and self._is_demo_mode():
            return self._demo_proxy_response(method, path, body, latency_ms)

        # §1.2 step 10: Response size limit
        content = response.content
        if len(content) > _MAX_RESPONSE_SIZE:
            return GatewayError(
                trace_id=trace_id,
                error_code="RESPONSE_TOO_LARGE",
                message="Response exceeds 10MB limit",
                status_code=502,
            )

        # §1.2 step 11: Parse response
        try:
            response_body: Any = response.json()
        except (ValueError, Exception):
            response_body = response.text

        # §1.2 step 12: Filter response headers
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

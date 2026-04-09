"""
Unit tests for PortkeyAdapter (TDD Red phase).
Specification: portkey_adapter_spec.md
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import MessageItem, UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse
from app.infrastructure.adapters.portkey_adapter import PortkeyAdapter

# --- Константы ---
API_KEY = "pk-test-key-1234567890"
BASE_URL = "https://api.portkey.test/v1"
TRACE_ID = str(uuid.uuid4())
REMOTE_ID = "gr_abc123"


# --- Хелперы ---
def _resp(status: int = 200, body: dict | list | None = None) -> httpx.Response:
    if body is not None:
        return httpx.Response(
            status,
            content=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", BASE_URL),
        )
    return httpx.Response(status, content=b"", request=httpx.Request("POST", BASE_URL))


def _chat_body() -> dict:
    return {
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _embedding_body() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": [0.123, 0.456, 0.789],
            }
        ],
        "model": "text-embedding-ada-002",
        "usage": {"prompt_tokens": 3, "total_tokens": 3},
    }


def _prompt(**kw) -> UnifiedPrompt:
    defaults = dict(
        trace_id=TRACE_ID,
        model="gpt-4",
        messages=[MessageItem(role="user", content="Hi")],
    )
    defaults.update(kw)
    return UnifiedPrompt(**defaults)


def _http_err(status: int, method: str = "POST") -> httpx.HTTPStatusError:
    resp = httpx.Response(status, request=httpx.Request(method, BASE_URL))
    return httpx.HTTPStatusError(f"HTTP {status}", request=resp.request, response=resp)


# ===========================================================================
# 1. provider_name
# ===========================================================================
class TestProviderName:
    def test_returns_portkey(self):
        assert PortkeyAdapter().provider_name == "portkey"

    def test_is_gateway_provider(self):
        assert isinstance(PortkeyAdapter(), GatewayProvider)


# ===========================================================================
# 2. send_prompt — успех
# ===========================================================================
class TestSendPromptSuccess:
    @pytest.mark.asyncio
    async def test_returns_unified_response(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, UnifiedResponse)
        assert r.content == "Hello!"
        assert r.model == "gpt-4"
        assert r.trace_id == TRACE_ID

    @pytest.mark.asyncio
    async def test_parses_usage(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert r.usage is not None
        assert r.usage.prompt_tokens == 10
        assert r.usage.completion_tokens == 5
        assert r.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_url_contains_chat_completions(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert "/chat/completions" in str(m.call_args)

    @pytest.mark.asyncio
    async def test_body_contains_model_and_messages(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        s = str(m.call_args)
        assert "gpt-4" in s
        assert "Hi" in s

    @pytest.mark.asyncio
    async def test_ada_v2_uses_embeddings_endpoint_and_alias(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _embedding_body())
            r = await a.send_prompt(_prompt(model="ada-v2"), API_KEY, BASE_URL)

        assert isinstance(r, UnifiedResponse)
        assert r.model == "text-embedding-ada-002"
        assert r.usage is not None
        assert r.usage.prompt_tokens == 3
        assert r.usage.completion_tokens == 0
        assert r.usage.total_tokens == 3
        call_repr = str(m.call_args)
        assert "/embeddings" in call_repr
        assert "text-embedding-ada-002" in call_repr


# ===========================================================================
# 3. Заголовки
# ===========================================================================
class TestHeaders:
    def test_build_headers_has_api_key(self):
        h = PortkeyAdapter()._build_headers(API_KEY)
        assert h["x-portkey-api-key"] == API_KEY

    def test_build_headers_has_content_type(self):
        h = PortkeyAdapter()._build_headers(API_KEY)
        assert h["Content-Type"] == "application/json"

    def test_build_headers_uses_openrouter_virtual_key_when_provider_matches(self):
        h = PortkeyAdapter()._build_headers(
            API_KEY,
            llm_provider="openrouter",
            virtual_keys={"openrouter": "vk-openrouter"},
        )
        assert h["x-portkey-virtual-key"] == "vk-openrouter"
        assert "x-portkey-provider" not in h

    def test_build_headers_ignores_null_like_openrouter_key(self):
        h = PortkeyAdapter()._build_headers(
            API_KEY,
            llm_provider="openrouter",
            virtual_keys={"openrouter": "null"},
        )
        assert "x-portkey-virtual-key" not in h
        assert h["x-portkey-provider"] == "openrouter"

    @pytest.mark.asyncio
    async def test_send_prompt_returns_clear_error_when_openrouter_key_missing(self):
        a = PortkeyAdapter()
        prompt = _prompt(model="@openrouter/openai/gpt-4o")
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            r = await a.send_prompt(prompt, "pk-test::google=dev-google,openai=dev-openai", BASE_URL)

        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.AUTH_FAILED
        assert "OpenRouter" in r.message
        m.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_prompt_recognizes_openrouter_explicit_provider_alias(self):
        a = PortkeyAdapter()
        prompt = _prompt(model="@openrouter/openai/gpt-4o")
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            await a.send_prompt(prompt, "pk-test::openrouter=vk-openrouter", BASE_URL)

        call_repr = str(m.call_args)
        assert "vk-openrouter" in call_repr
        assert "x-portkey-provider" not in call_repr or "openrouter" in call_repr

    @pytest.mark.asyncio
    async def test_trace_id_in_call(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        s = str(m.call_args)
        assert "x-portkey-trace-id" in s or TRACE_ID in s

    @pytest.mark.asyncio
    async def test_guardrails_header_present_when_ids(self):
        a = PortkeyAdapter()
        p = _prompt(guardrail_ids=["gr_1", "gr_2"])
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            await a.send_prompt(p, API_KEY, BASE_URL)
        assert "x-portkey-guardrails" in str(m.call_args)

    @pytest.mark.asyncio
    async def test_no_guardrails_header_when_empty(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, _chat_body())
            await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert "x-portkey-guardrails" not in str(m.call_args)


# ===========================================================================
# 4. CRUD guardrails — успех
# ===========================================================================
class TestCreateGuardrail:
    @pytest.mark.asyncio
    async def test_returns_dict_with_remote_id(self):
        a = PortkeyAdapter()
        body = {"id": REMOTE_ID, "name": "g1", "config": {}}
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, body)
            r = await a.create_guardrail({}, API_KEY, BASE_URL)
        assert isinstance(r, dict)
        assert r["remote_id"] == REMOTE_ID

    @pytest.mark.asyncio
    async def test_returns_raw_response(self):
        a = PortkeyAdapter()
        body = {"id": REMOTE_ID, "name": "g1", "config": {}}
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, body)
            r = await a.create_guardrail({}, API_KEY, BASE_URL)
        assert "raw_response" in r

    @pytest.mark.asyncio
    async def test_posts_to_guardrails_url(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, {"id": "x"})
            await a.create_guardrail({}, API_KEY, BASE_URL)
        assert "/guardrails" in str(m.call_args)


class TestUpdateGuardrail:
    @pytest.mark.asyncio
    async def test_returns_dict_with_remote_id(self):
        a = PortkeyAdapter()
        body = {"id": REMOTE_ID, "name": "g1", "config": {}}
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, body)
            r = await a.update_guardrail(REMOTE_ID, {}, API_KEY, BASE_URL)
        assert isinstance(r, dict) and "remote_id" in r

    @pytest.mark.asyncio
    async def test_uses_put(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, {"id": REMOTE_ID})
            await a.update_guardrail(REMOTE_ID, {}, API_KEY, BASE_URL)
        assert "PUT" in str(m.call_args).upper()

    @pytest.mark.asyncio
    async def test_url_contains_remote_id(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, {"id": REMOTE_ID})
            await a.update_guardrail(REMOTE_ID, {}, API_KEY, BASE_URL)
        assert REMOTE_ID in str(m.call_args)


class TestDeleteGuardrail:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200)
            assert await a.delete_guardrail(REMOTE_ID, API_KEY, BASE_URL) is True

    @pytest.mark.asyncio
    async def test_returns_true_on_204(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(204)
            assert await a.delete_guardrail(REMOTE_ID, API_KEY, BASE_URL) is True

    @pytest.mark.asyncio
    async def test_url_contains_remote_id(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200)
            await a.delete_guardrail(REMOTE_ID, API_KEY, BASE_URL)
        assert REMOTE_ID in str(m.call_args)


class TestListGuardrails:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        a = PortkeyAdapter()
        body = [{"id": "g1", "name": "n1", "config": {}}]
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, body)
            r = await a.list_guardrails(API_KEY, BASE_URL)
        assert isinstance(r, list) and len(r) == 1

    @pytest.mark.asyncio
    async def test_items_have_required_keys(self):
        a = PortkeyAdapter()
        body = [{"id": "g1", "name": "n1", "config": {}}]
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, body)
            r = await a.list_guardrails(API_KEY, BASE_URL)
        for item in r:
            assert "remote_id" in item and "name" in item and "config" in item

    @pytest.mark.asyncio
    async def test_uses_get(self):
        a = PortkeyAdapter()
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = _resp(200, [])
            await a.list_guardrails(API_KEY, BASE_URL)
        assert "GET" in str(m.call_args).upper()


# ===========================================================================
# 5. [SRE_MARKER] Retry-логика
# ===========================================================================
class TestRetryLogic:
    """Спецификация 1.1: макс 3 попытки, GET retry при таймаутах, POST/PUT/DELETE — нет."""

    @pytest.mark.asyncio
    async def test_max_3_attempts_on_502(self):
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise _http_err(502)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 3

    @pytest.mark.asyncio
    async def test_max_3_attempts_on_503(self):
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise _http_err(503)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 3

    @pytest.mark.asyncio
    async def test_get_retries_on_timeout(self):
        """[SRE] GET повторяется при таймаутах — 3 попытки."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.list_guardrails(API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.TIMEOUT
        assert count == 3, (
            f"GET должен retry при таймауте: ожидалось 3, получено {count}"
        )

    @pytest.mark.asyncio
    async def test_post_no_retry_on_timeout(self):
        """[SRE] POST НЕ повторяется при таймаутах — 1 попытка."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and r.error_code == GatewayError.TIMEOUT
        assert count == 1, (
            f"POST не должен retry при таймауте: ожидалось 1, получено {count}"
        )

    @pytest.mark.asyncio
    async def test_put_no_retry_on_timeout(self):
        """[SRE] PUT НЕ повторяется при таймаутах."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.update_guardrail(REMOTE_ID, {}, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 1

    @pytest.mark.asyncio
    async def test_delete_no_retry_on_timeout(self):
        """[SRE] DELETE НЕ повторяется при таймаутах."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.delete_guardrail(REMOTE_ID, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 1

    @pytest.mark.asyncio
    async def test_create_guardrail_no_retry_on_timeout(self):
        """[SRE] POST (create_guardrail) НЕ повторяется при таймаутах."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.create_guardrail({}, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 1

    @pytest.mark.asyncio
    async def test_post_retries_on_502(self):
        """POST повторяется при 502."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise _http_err(502)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.create_guardrail({}, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        """400 — нет retry, сразу ошибка."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise _http_err(400)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self):
        """401 — нет retry."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise _http_err(401)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_429(self):
        """429 — нет retry."""
        a, count = PortkeyAdapter(), 0

        async def req(*_, **__):
            nonlocal count
            count += 1
            raise _http_err(429)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError) and count == 1


# ===========================================================================
# 6. [SRE_MARKER] Маппинг ошибок
# ===========================================================================
class TestErrorMapping:
    """Спецификация раздел 9: маппинг исключений httpx -> GatewayError."""

    @pytest.mark.asyncio
    async def test_timeout_maps_to_timeout(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.TIMEOUT
        assert r.status_code == 504

    @pytest.mark.asyncio
    async def test_connect_error_maps_to_provider_error(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise httpx.ConnectError("connection refused")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.PROVIDER_ERROR
        assert r.status_code == 502

    @pytest.mark.asyncio
    async def test_401_maps_to_auth_failed(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise _http_err(401)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_403_maps_to_auth_failed(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise _http_err(403)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_429_maps_to_rate_limited(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise _http_err(429)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_400_maps_to_validation_error(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise _http_err(400)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_500_maps_to_provider_error(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise _http_err(500)

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.PROVIDER_ERROR

    @pytest.mark.asyncio
    async def test_json_decode_error_maps_to_provider_error(self):
        """json.JSONDecodeError -> PROVIDER_ERROR, status 502."""
        a = PortkeyAdapter()
        # Return a response with invalid JSON
        bad_resp = httpx.Response(
            200, content=b"not-json", request=httpx.Request("POST", BASE_URL)
        )
        with patch.object(a, "_execute_with_retry", new_callable=AsyncMock) as m:
            m.return_value = bad_resp
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.PROVIDER_ERROR
        assert r.status_code == 502

    @pytest.mark.asyncio
    async def test_generic_exception_maps_to_unknown(self):
        """Любое неизвестное исключение -> UNKNOWN, status 500."""
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise RuntimeError("unexpected")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.error_code == GatewayError.UNKNOWN
        assert r.status_code == 500

    @pytest.mark.asyncio
    async def test_no_exception_leaks_from_send_prompt(self):
        """Никакие исключения не должны просачиваться наружу."""
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise ValueError("boom")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        # Should not be an exception — result is GatewayError
        assert isinstance(r, GatewayError)

    @pytest.mark.asyncio
    async def test_no_exception_leaks_from_create_guardrail(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise ValueError("boom")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.create_guardrail({}, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)

    @pytest.mark.asyncio
    async def test_no_exception_leaks_from_list_guardrails(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise ValueError("boom")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.list_guardrails(API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)

    @pytest.mark.asyncio
    async def test_no_exception_leaks_from_delete_guardrail(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise ValueError("boom")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.delete_guardrail(REMOTE_ID, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)

    @pytest.mark.asyncio
    async def test_no_exception_leaks_from_update_guardrail(self):
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise ValueError("boom")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.update_guardrail(REMOTE_ID, {}, API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)

    @pytest.mark.asyncio
    async def test_error_contains_provider_name(self):
        """GatewayError должен содержать provider_name='portkey'."""
        a = PortkeyAdapter()

        async def req(*_, **__):
            raise httpx.TimeoutException("timeout")

        with patch.object(a, "_get_http_client") as g:
            c = AsyncMock()
            c.request = req
            g.return_value = c
            r = await a.send_prompt(_prompt(), API_KEY, BASE_URL)
        assert isinstance(r, GatewayError)
        assert r.provider_name == "portkey"


# ===========================================================================
# 7. Жизненный цикл — close()
# ===========================================================================
class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close_calls_aclose_on_client(self):
        """close() должен вызвать aclose() на внутреннем httpx.AsyncClient."""
        a = PortkeyAdapter()
        mock_client = AsyncMock()
        a._client = mock_client
        await a.close()
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        """Повторный вызов close() не должен вызывать ошибку."""
        a = PortkeyAdapter()
        # Without an initialized client, close() should not fail
        await a.close()
        await a.close()

    @pytest.mark.asyncio
    async def test_get_http_client_returns_async_client(self):
        """_get_http_client должен возвращать httpx.AsyncClient."""
        a = PortkeyAdapter()
        client = a._get_http_client()
        assert isinstance(client, httpx.AsyncClient)
        await client.aclose()

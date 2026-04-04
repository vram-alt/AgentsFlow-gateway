"""
TDD Red-phase тесты для TesterService — оркестратора модуля Testing Console.

Спецификация: app/services/tester_service_spec.md

Все тесты ДОЛЖНЫ падать на Red-фазе, пока TesterService не реализован
(tester_service.py пуст).

Все зависимости (ProviderRepository, httpx.AsyncClient) — строго замоканы.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ── Импорт тестируемого класса (упадёт на Red-фазе) ─────────────────────
from app.services.tester_service import TesterService

# ── Импорт доменных объектов (уже реализованы) ───────────────────────────
from app.domain.dto.gateway_error import GatewayError


# ═══════════════════════════════════════════════════════════════════════════
# Константы
# ═══════════════════════════════════════════════════════════════════════════

SAMPLE_PROVIDER_NAME = "portkey"
SAMPLE_API_KEY = "sk-test-key-12345"
SAMPLE_BASE_URL = "https://api.portkey.ai"
SAMPLE_PATH = "/v1/chat/completions"
SAMPLE_METHOD = "POST"
SAMPLE_BODY = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hi"}]}


# ═══════════════════════════════════════════════════════════════════════════
# Фикстуры
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_provider_repo():
    """Мок ProviderRepository с async-методами."""
    repo = AsyncMock()
    provider_record = MagicMock()
    provider_record.api_key = SAMPLE_API_KEY
    provider_record.base_url = SAMPLE_BASE_URL
    provider_record.name = SAMPLE_PROVIDER_NAME
    provider_record.is_active = True
    repo.get_active_by_name = AsyncMock(return_value=provider_record)
    return repo


@pytest.fixture
def mock_http_client():
    """Мок httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    # По умолчанию: успешный ответ
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {
        "content-type": "application/json",
        "x-request-id": "req-123",
        "x-portkey-trace-id": "trace-456",
        "server": "nginx",  # Этот заголовок должен быть отфильтрован
    }
    mock_response.text = '{"choices": [{"message": {"content": "Hello!"}}]}'
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello!"}}]
    }
    mock_response.content = b'{"choices": [{"message": {"content": "Hello!"}}]}'
    mock_response.read = AsyncMock(return_value=mock_response.content)
    client.request = AsyncMock(return_value=mock_response)
    return client


@pytest.fixture
def service(mock_provider_repo, mock_http_client):
    """Экземпляр TesterService с замоканными зависимостями."""
    return TesterService(
        provider_repo=mock_provider_repo,
        http_client=mock_http_client,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Конструктор (spec 1.1)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterServiceConstructor:
    """Тесты конструктора TesterService (spec 1.1)."""

    def test_constructor_accepts_dependencies(
        self, mock_provider_repo, mock_http_client
    ):
        """TesterService принимает provider_repo и http_client."""
        svc = TesterService(
            provider_repo=mock_provider_repo,
            http_client=mock_http_client,
        )
        assert svc is not None

    def test_constructor_stores_provider_repo(
        self, mock_provider_repo, mock_http_client
    ):
        """provider_repo сохраняется как атрибут."""
        svc = TesterService(
            provider_repo=mock_provider_repo,
            http_client=mock_http_client,
        )
        assert svc.provider_repo is mock_provider_repo

    def test_constructor_stores_http_client(
        self, mock_provider_repo, mock_http_client
    ):
        """http_client сохраняется как атрибут."""
        svc = TesterService(
            provider_repo=mock_provider_repo,
            http_client=mock_http_client,
        )
        assert svc.http_client is mock_http_client


# ═══════════════════════════════════════════════════════════════════════════
# 2. Happy Path — proxy_request (spec 1.2)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestHappyPath:
    """Успешный сценарий proxy_request."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self, service):
        """При успехе возвращается словарь (не GatewayError)."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert isinstance(result, dict)
        assert not isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_result_contains_status_code(self, service):
        """Результат содержит status_code."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert "status_code" in result
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_result_contains_headers(self, service):
        """Результат содержит отфильтрованные заголовки."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert "headers" in result
        assert isinstance(result["headers"], dict)

    @pytest.mark.asyncio
    async def test_result_contains_body(self, service):
        """Результат содержит body."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert "body" in result

    @pytest.mark.asyncio
    async def test_result_contains_latency_ms(self, service):
        """Результат содержит latency_ms."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_latency_ms_is_non_negative(self, service):
        """latency_ms >= 0."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert result["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_latency_ms_rounded_to_2_decimals(self, service):
        """latency_ms округлена до 2 знаков (spec 1.2 п.9)."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        latency_str = str(result["latency_ms"])
        if "." in latency_str:
            decimals = len(latency_str.split(".")[1])
            assert decimals <= 2

    @pytest.mark.asyncio
    async def test_calls_provider_repo(self, service, mock_provider_repo):
        """Вызывает provider_repo.get_active_by_name."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        mock_provider_repo.get_active_by_name.assert_awaited_once_with(
            SAMPLE_PROVIDER_NAME
        )

    @pytest.mark.asyncio
    async def test_calls_http_client_request(self, service, mock_http_client):
        """Вызывает http_client.request с правильным методом."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        mock_http_client.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_url_formed_correctly(self, service, mock_http_client):
        """URL формируется как base_url + path (spec 1.2 п.3)."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/v1/chat/completions",
            body=SAMPLE_BODY,
            headers=None,
        )
        call_args = mock_http_client.request.call_args
        args, kwargs = call_args
        # URL должен быть https://api.portkey.ai/v1/chat/completions
        url = kwargs.get("url") or (args[1] if len(args) > 1 else None)
        expected = "https://api.portkey.ai/v1/chat/completions"
        assert url == expected


# ═══════════════════════════════════════════════════════════════════════════
# 3. Провайдер не найден (spec 1.2 п.2)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestProviderNotFound:
    """Провайдер не найден -> GatewayError(PROVIDER_NOT_FOUND)."""

    @pytest.mark.asyncio
    async def test_returns_gateway_error(self, service, mock_provider_repo):
        """Если провайдер не найден -> GatewayError."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.proxy_request(
            provider_name="nonexistent",
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_error_code_is_provider_not_found(self, service, mock_provider_repo):
        """error_code = 'PROVIDER_NOT_FOUND'."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.proxy_request(
            provider_name="nonexistent",
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert result.error_code == "PROVIDER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_status_code_is_404(self, service, mock_provider_repo):
        """status_code = 404."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.proxy_request(
            provider_name="nonexistent",
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_http_client_not_called(
        self, service, mock_provider_repo, mock_http_client
    ):
        """HTTP-клиент НЕ вызывается, если провайдер не найден."""
        mock_provider_repo.get_active_by_name.return_value = None

        await service.proxy_request(
            provider_name="nonexistent",
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        mock_http_client.request.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# 4. [SRE_MARKER] Валидация path (spec 1.2 п.1)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestPathValidation:
    """[SRE_MARKER] Валидация path: path traversal, абсолютные URL."""

    @pytest.mark.asyncio
    async def test_path_traversal_returns_validation_error(self, service):
        """[SRE_MARKER] Path traversal '..' -> GatewayError(VALIDATION_ERROR)."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/../../etc/passwd",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"
        assert result.status_code == 422

    @pytest.mark.asyncio
    async def test_absolute_url_returns_validation_error(self, service):
        """[SRE_MARKER] Абсолютный URL '://' -> GatewayError(VALIDATION_ERROR)."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="https://evil.com/steal",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"
        assert result.status_code == 422

    @pytest.mark.asyncio
    async def test_percent_encoded_path_traversal_rejected(self, service):
        """[SRE_MARKER] Percent-encoded '..' (%2e%2e) отклоняется после URL-декодирования."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/%2e%2e/%2e%2e/etc/passwd",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_percent_encoded_absolute_url_rejected(self, service):
        """[SRE_MARKER] Percent-encoded '://' отклоняется после URL-декодирования."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="http%3A%2F%2Fevil.com/steal",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_http_client_not_called_on_invalid_path(
        self, service, mock_http_client
    ):
        """HTTP-клиент НЕ вызывается при невалидном path."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/../../etc/passwd",
            body=None,
            headers=None,
        )
        mock_http_client.request.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# 5. [SRE_MARKER] SSRF-валидация итогового URL (spec 1.2 п.4)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestSSRFValidation:
    """[SRE_MARKER] SSRF-защита: приватные IP, hostname mismatch, scheme."""

    @pytest.mark.asyncio
    async def test_private_ip_127_rejected(self, service, mock_provider_repo):
        """[SRE_MARKER] Приватный IP 127.0.0.1 отклоняется."""
        provider = MagicMock()
        provider.api_key = SAMPLE_API_KEY
        provider.base_url = "https://127.0.0.1"
        provider.name = SAMPLE_PROVIDER_NAME
        mock_provider_repo.get_active_by_name.return_value = provider

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/v1/chat",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_private_ip_10_range_rejected(self, service, mock_provider_repo):
        """[SRE_MARKER] Приватный IP 10.0.0.1 отклоняется."""
        provider = MagicMock()
        provider.api_key = SAMPLE_API_KEY
        provider.base_url = "https://10.0.0.1"
        provider.name = SAMPLE_PROVIDER_NAME
        mock_provider_repo.get_active_by_name.return_value = provider

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/v1/chat",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_private_ip_172_16_range_rejected(self, service, mock_provider_repo):
        """[SRE_MARKER] Приватный IP 172.16.0.1 отклоняется."""
        provider = MagicMock()
        provider.api_key = SAMPLE_API_KEY
        provider.base_url = "https://172.16.0.1"
        provider.name = SAMPLE_PROVIDER_NAME
        mock_provider_repo.get_active_by_name.return_value = provider

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/v1/chat",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_private_ip_192_168_range_rejected(self, service, mock_provider_repo):
        """[SRE_MARKER] Приватный IP 192.168.1.1 отклоняется."""
        provider = MagicMock()
        provider.api_key = SAMPLE_API_KEY
        provider.base_url = "https://192.168.1.1"
        provider.name = SAMPLE_PROVIDER_NAME
        mock_provider_repo.get_active_by_name.return_value = provider

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/v1/chat",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_aws_metadata_ip_rejected(self, service, mock_provider_repo):
        """[SRE_MARKER] AWS metadata endpoint 169.254.169.254 отклоняется."""
        provider = MagicMock()
        provider.api_key = SAMPLE_API_KEY
        provider.base_url = "https://169.254.169.254"
        provider.name = SAMPLE_PROVIDER_NAME
        mock_provider_repo.get_active_by_name.return_value = provider

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/latest/meta-data/",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_ipv6_loopback_rejected(self, service, mock_provider_repo):
        """[SRE_MARKER] IPv6 loopback ::1 отклоняется."""
        provider = MagicMock()
        provider.api_key = SAMPLE_API_KEY
        provider.base_url = "https://[::1]"
        provider.name = SAMPLE_PROVIDER_NAME
        mock_provider_repo.get_active_by_name.return_value = provider

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/v1/chat",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Формирование заголовков (spec 1.2 п.5)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestHeaders:
    """Формирование заголовков запроса к провайдеру."""

    @pytest.mark.asyncio
    async def test_api_key_header_set(self, service, mock_http_client):
        """Заголовок x-portkey-api-key устанавливается из записи провайдера."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        call_args = mock_http_client.request.call_args
        _, kwargs = call_args
        sent_headers = kwargs.get("headers", {})
        assert sent_headers.get("x-portkey-api-key") == SAMPLE_API_KEY

    @pytest.mark.asyncio
    async def test_content_type_header_set(self, service, mock_http_client):
        """Заголовок Content-Type = application/json."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        call_args = mock_http_client.request.call_args
        _, kwargs = call_args
        sent_headers = kwargs.get("headers", {})
        assert sent_headers.get("Content-Type") == "application/json"

    @pytest.mark.asyncio
    async def test_api_key_not_overwritten_by_user_headers(
        self, service, mock_http_client
    ):
        """[SRE_MARKER] Пользователь НЕ может перезаписать x-portkey-api-key."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers={"x-portkey-api-key": "evil-key"},
        )
        call_args = mock_http_client.request.call_args
        _, kwargs = call_args
        sent_headers = kwargs.get("headers", {})
        # API-ключ должен остаться оригинальным
        assert sent_headers.get("x-portkey-api-key") == SAMPLE_API_KEY

    @pytest.mark.asyncio
    async def test_api_key_not_overwritten_case_insensitive(
        self, service, mock_http_client
    ):
        """[SRE_MARKER] Регистронезависимая защита x-portkey-api-key."""
        await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers={"X-Portkey-Api-Key": "evil-key"},
        )
        call_args = mock_http_client.request.call_args
        _, kwargs = call_args
        sent_headers = kwargs.get("headers", {})
        # Проверяем, что ни один вариант регистра не содержит evil-key
        for key, value in sent_headers.items():
            if key.lower() == "x-portkey-api-key":
                assert value == SAMPLE_API_KEY


# ═══════════════════════════════════════════════════════════════════════════
# 7. Фильтрация заголовков ответа (spec 1.2 п.12)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestResponseHeaderFiltering:
    """Фильтрация заголовков ответа — только allowlist."""

    @pytest.mark.asyncio
    async def test_allowed_headers_included(self, service):
        """Допустимые заголовки (content-type, x-request-id, x-portkey-trace-id, retry-after) включаются."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        response_headers = result["headers"]
        assert "content-type" in response_headers

    @pytest.mark.asyncio
    async def test_disallowed_headers_excluded(self, service):
        """Недопустимые заголовки (server и т.д.) исключаются."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        response_headers = result["headers"]
        assert "server" not in response_headers


# ═══════════════════════════════════════════════════════════════════════════
# 8. Обработка ошибок HTTP-запроса (spec 1.2 п.8)
# ═══════════════════════════════════════════════════════════════════════════


class TestProxyRequestHttpErrors:
    """Обработка ошибок при HTTP-запросе к провайдеру."""

    @pytest.mark.asyncio
    async def test_timeout_returns_proxy_timeout(self, service, mock_http_client):
        """Таймаут -> GatewayError(PROXY_TIMEOUT, 504)."""
        mock_http_client.request.side_effect = httpx.TimeoutException("Timed out")

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "PROXY_TIMEOUT"
        assert result.status_code == 504

    @pytest.mark.asyncio
    async def test_connect_error_returns_proxy_connection_error(
        self, service, mock_http_client
    ):
        """Ошибка соединения -> GatewayError(PROXY_CONNECTION_ERROR, 502)."""
        mock_http_client.request.side_effect = httpx.ConnectError("Connection refused")

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "PROXY_CONNECTION_ERROR"
        assert result.status_code == 502

    @pytest.mark.asyncio
    async def test_generic_exception_returns_internal_error(
        self, service, mock_http_client
    ):
        """Непредвиденное исключение -> GatewayError(INTERNAL_ERROR, 500)."""
        mock_http_client.request.side_effect = RuntimeError("Unexpected")

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "INTERNAL_ERROR"
        assert result.status_code == 500


# ═══════════════════════════════════════════════════════════════════════════
# 9. [SRE_MARKER] Ограничение размера ответа (spec 1.2 п.10)
# ═══════════════════════════════════════════════════════════════════════════



class TestProxyRequestResponseSizeLimit:
    """[SRE_MARKER] Ответ больше 10 МБ -> GatewayError(RESPONSE_TOO_LARGE)."""

    @pytest.mark.asyncio
    async def test_response_too_large_returns_error(
        self, service, mock_http_client
    ):
        """[SRE_MARKER] Ответ больше 10 МБ возвращает RESPONSE_TOO_LARGE."""
        large_content = b"x" * (10_485_760 + 1)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = large_content
        mock_response.read = AsyncMock(return_value=large_content)
        mock_response.text = "x" * (10_485_760 + 1)
        mock_http_client.request = AsyncMock(return_value=mock_response)

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "RESPONSE_TOO_LARGE"
        assert result.status_code == 502


class TestProxyRequestTraceId:
    """[SRE_MARKER] Каждый GatewayError содержит валидный trace_id (UUID v4)."""

    @pytest.mark.asyncio
    async def test_trace_id_on_provider_not_found(self, service, mock_provider_repo):
        """trace_id присутствует при PROVIDER_NOT_FOUND."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.proxy_request(
            provider_name="nonexistent",
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        parsed = uuid.UUID(result.trace_id)
        assert parsed.version == 4

    @pytest.mark.asyncio
    async def test_trace_id_on_timeout(self, service, mock_http_client):
        """trace_id присутствует при PROXY_TIMEOUT."""
        mock_http_client.request.side_effect = httpx.TimeoutException("Timed out")

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        parsed = uuid.UUID(result.trace_id)
        assert parsed.version == 4

    @pytest.mark.asyncio
    async def test_trace_id_on_validation_error(self, service):
        """trace_id присутствует при VALIDATION_ERROR."""
        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path="/../../etc/passwd",
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        parsed = uuid.UUID(result.trace_id)
        assert parsed.version == 4

    @pytest.mark.asyncio
    async def test_trace_id_on_internal_error(self, service, mock_http_client):
        """trace_id присутствует при INTERNAL_ERROR."""
        mock_http_client.request.side_effect = RuntimeError("Boom")

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        parsed = uuid.UUID(result.trace_id)
        assert parsed.version == 4


class TestProxyRequestResponseParsing:
    """Парсинг тела ответа: JSON или сырой текст."""

    @pytest.mark.asyncio
    async def test_json_response_parsed(self, service, mock_http_client):
        """Валидный JSON-ответ парсится в dict."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"result": "ok"}
        mock_response.text = '{"result": "ok"}'
        mock_response.content = b'{"result": "ok"}'
        mock_response.read = AsyncMock(return_value=mock_response.content)
        mock_http_client.request = AsyncMock(return_value=mock_response)

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert result["body"] == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_non_json_response_returned_as_text(self, service, mock_http_client):
        """Невалидный JSON-ответ возвращается как строка."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Plain text response"
        mock_response.content = b"Plain text response"
        mock_response.read = AsyncMock(return_value=mock_response.content)
        mock_http_client.request = AsyncMock(return_value=mock_response)

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=SAMPLE_BODY,
            headers=None,
        )
        assert isinstance(result["body"], str)
        assert result["body"] == "Plain text response"


class TestProxyRequestApiKeyNotLeaked:
    """[SRE_MARKER] API-ключ НИКОГДА не включается в сообщения об ошибках."""

    @pytest.mark.asyncio
    async def test_api_key_not_in_timeout_error_message(
        self, service, mock_http_client
    ):
        """API-ключ отсутствует в сообщении ошибки таймаута."""
        mock_http_client.request.side_effect = httpx.TimeoutException("Timed out")

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert SAMPLE_API_KEY not in result.message

    @pytest.mark.asyncio
    async def test_api_key_not_in_internal_error_message(
        self, service, mock_http_client
    ):
        """API-ключ отсутствует в сообщении внутренней ошибки."""
        mock_http_client.request.side_effect = RuntimeError(
            f"Error with key {SAMPLE_API_KEY}"
        )

        result = await service.proxy_request(
            provider_name=SAMPLE_PROVIDER_NAME,
            method=SAMPLE_METHOD,
            path=SAMPLE_PATH,
            body=None,
            headers=None,
        )
        assert isinstance(result, GatewayError)
        assert SAMPLE_API_KEY not in result.message

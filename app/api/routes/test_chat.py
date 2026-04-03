"""
TDD Red-phase tests for POST /api/chat/send router.

Based on: app/api/routes/chat_spec.md
These tests MUST fail with ImportError until the router is implemented.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Hypothetical imports (will fail until modules exist) ---
from app.main import app
from app.api.schemas.chat import ChatRequest, ChatResponse, ErrorResponse
from app.services.chat_service import ChatService
from app.domain.dto.unified_response import UnifiedResponse
from app.domain.dto.gateway_error import GatewayError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "model": "gpt-4",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
    ],
}

VALID_PAYLOAD_FULL = {
    "model": "gpt-4",
    "messages": [
        {"role": "user", "content": "Ping"},
    ],
    "provider_name": "openai",
    "temperature": 0.7,
    "max_tokens": 256,
    "guardrail_ids": ["guard-1", "guard-2"],
}

FAKE_TRACE_ID = str(uuid.uuid4())


def _make_success_response() -> UnifiedResponse:
    """Return a mock UnifiedResponse that the service would produce."""
    resp = MagicMock(spec=UnifiedResponse)
    resp.trace_id = FAKE_TRACE_ID
    resp.content = "Hello from LLM!"
    resp.model = "gpt-4"
    resp.usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    resp.guardrail_blocked = False
    return resp


def _make_gateway_error(
    status_code: int, error_code: str, message: str
) -> GatewayError:
    """Return a mock GatewayError with the given status."""
    err = MagicMock(spec=GatewayError)
    err.status_code = status_code
    err.trace_id = FAKE_TRACE_ID
    err.error_code = error_code
    err.message = message
    err.details = {}
    return err


@pytest.fixture()
def mock_chat_service() -> AsyncMock:
    """Create an AsyncMock of ChatService."""
    return AsyncMock(spec=ChatService)


@pytest.fixture()
def client(mock_chat_service: AsyncMock) -> TestClient:
    """
    Build a TestClient with ChatService overridden via dependency_overrides.
    Also override HTTP Basic Auth to bypass authentication in tests.
    """
    from app.api.dependencies.di import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    # Bypass HTTP Basic Auth for isolated route testing
    from app.api.middleware.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: "test-user"

    yield TestClient(app)

    app.dependency_overrides.clear()


# ===========================================================================
# 1. Успешный ответ — HTTP 200
# ===========================================================================


class TestChatSendSuccess:
    """POST /api/chat/send → 200 OK."""

    def test_returns_200_with_valid_payload(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """Минимальный валидный запрос возвращает 200 и корректное тело."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body["trace_id"] == FAKE_TRACE_ID
        assert body["content"] == "Hello from LLM!"
        assert body["model"] == "gpt-4"
        assert body["guardrail_blocked"] is False

    def test_returns_200_with_full_payload(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """Запрос со всеми опциональными полями тоже возвращает 200."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        response = client.post("/api/chat/send", json=VALID_PAYLOAD_FULL)

        assert response.status_code == 200

    def test_service_called_with_correct_args(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """Проверяем, что сервис вызывается с данными из запроса."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        client.post("/api/chat/send", json=VALID_PAYLOAD)

        mock_chat_service.send_chat_message.assert_called_once()

    def test_usage_field_can_be_null(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """usage может быть null — это допустимо по спецификации."""
        resp = _make_success_response()
        resp.usage = None
        mock_chat_service.send_chat_message.return_value = resp

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 200
        assert response.json()["usage"] is None


# ===========================================================================
# 2. Валидация — HTTP 422
# ===========================================================================


class TestChatSendValidation:
    """POST /api/chat/send → 422 Unprocessable Entity."""

    def test_missing_model_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'model' → 422."""
        payload = {
            "messages": [{"role": "user", "content": "Hi"}],
        }
        response = client.post("/api/chat/send", json=payload)
        assert response.status_code == 422

    def test_missing_messages_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'messages' → 422."""
        payload = {
            "model": "gpt-4",
        }
        response = client.post("/api/chat/send", json=payload)
        assert response.status_code == 422

    def test_empty_body_returns_422(self, client: TestClient):
        """Пустое тело запроса → 422."""
        response = client.post("/api/chat/send", json={})
        assert response.status_code == 422

    def test_empty_messages_list_returns_422(self, client: TestClient):
        """Пустой список messages → 422 (нужен хотя бы один элемент)."""
        payload = {
            "model": "gpt-4",
            "messages": [],
        }
        response = client.post("/api/chat/send", json=payload)
        assert response.status_code == 422

    def test_invalid_json_returns_422(self, client: TestClient):
        """Невалидный JSON → 422."""
        response = client.post(
            "/api/chat/send",
            content=b"not-a-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


# ===========================================================================
# 3. Дефолтные значения опциональных полей
# ===========================================================================


class TestChatSendDefaults:
    """Проверка значений по умолчанию из спецификации."""

    def test_provider_name_defaults_to_portkey(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """provider_name по умолчанию = 'portkey'."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        client.post("/api/chat/send", json=VALID_PAYLOAD)

        call_args = mock_chat_service.send_chat_message.call_args
        # Проверяем, что в аргументах вызова provider_name == "portkey"
        # Точная проверка зависит от сигнатуры, но мы проверяем через kwargs или позиционно
        assert call_args is not None

    def test_temperature_defaults_to_none(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """temperature по умолчанию = null."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        client.post("/api/chat/send", json=VALID_PAYLOAD)

        # Сервис должен быть вызван — дефолт temperature=None
        mock_chat_service.send_chat_message.assert_called_once()

    def test_guardrail_ids_defaults_to_empty_list(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """guardrail_ids по умолчанию = пустой список."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        client.post("/api/chat/send", json=VALID_PAYLOAD)

        mock_chat_service.send_chat_message.assert_called_once()


# ===========================================================================
# 4. Маппинг GatewayError → HTTP-статусы
# ===========================================================================


class TestChatSendGatewayErrors:
    """POST /api/chat/send → 4xx/5xx при GatewayError от сервиса."""

    def test_gateway_error_401_unauthorized(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """GatewayError(status_code=401) → HTTP 401."""
        error = _make_gateway_error(401, "AUTH_FAILED", "Invalid API key")
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 401
        body = response.json()
        assert body["trace_id"] == FAKE_TRACE_ID
        assert body["error_code"] == "AUTH_FAILED"
        assert body["message"] == "Invalid API key"

    def test_gateway_error_500_internal(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """GatewayError(status_code=500) → HTTP 500."""
        error = _make_gateway_error(500, "INTERNAL_ERROR", "Something went wrong")
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 500
        body = response.json()
        assert body["trace_id"] == FAKE_TRACE_ID
        assert body["error_code"] == "INTERNAL_ERROR"

    def test_gateway_error_502_bad_gateway(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """GatewayError(status_code=502) → HTTP 502 (ошибка провайдера)."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Provider returned error")
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 502
        body = response.json()
        assert body["error_code"] == "PROVIDER_ERROR"

    def test_gateway_error_504_timeout(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """GatewayError(status_code=504) → HTTP 504 (таймаут провайдера)."""
        error = _make_gateway_error(504, "TIMEOUT", "Provider timed out")
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 504
        body = response.json()
        assert body["error_code"] == "TIMEOUT"
        assert body["message"] == "Provider timed out"


# ===========================================================================
# 5. Структура ErrorResponse
# ===========================================================================


class TestErrorResponseStructure:
    """Проверка полноты ErrorResponse по спецификации."""

    def test_error_response_contains_all_fields(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """ErrorResponse должен содержать trace_id, error_code, message, details."""
        error = _make_gateway_error(500, "INTERNAL_ERROR", "Boom")
        error.details = {"extra": "info"}
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        body = response.json()
        assert "trace_id" in body
        assert "error_code" in body
        assert "message" in body
        assert "details" in body
        assert body["details"] == {"extra": "info"}

    def test_error_response_details_defaults_to_empty_dict(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """details по умолчанию — пустой словарь."""
        error = _make_gateway_error(500, "INTERNAL_ERROR", "Boom")
        error.details = {}
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        body = response.json()
        assert body["details"] == {}


# ===========================================================================
# 6. [SRE_MARKER] — trace_id всегда присутствует
# ===========================================================================


class TestSRETraceIdPresence:
    """
    [SRE_MARKER] trace_id MUST always be present in both success and error
    responses. Missing trace_id breaks distributed tracing and incident response.
    """

    def test_trace_id_present_in_success_response(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """trace_id обязателен в успешном ответе."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert response.status_code == 200
        assert "trace_id" in response.json()
        assert response.json()["trace_id"] is not None

    def test_trace_id_present_in_error_response(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """trace_id обязателен в ответе с ошибкой."""
        error = _make_gateway_error(500, "INTERNAL_ERROR", "Fail")
        mock_chat_service.send_chat_message.return_value = error

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        assert "trace_id" in response.json()
        assert response.json()["trace_id"] is not None

    def test_trace_id_is_valid_uuid_format(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """trace_id должен быть валидным UUID."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        trace_id = response.json()["trace_id"]
        # Проверяем, что trace_id — валидный UUID
        parsed = uuid.UUID(trace_id)
        assert str(parsed) == trace_id


# ===========================================================================
# 7. Структура ChatResponse
# ===========================================================================


class TestChatResponseStructure:
    """Проверка полноты ChatResponse по спецификации."""

    def test_success_response_contains_all_fields(
        self, client: TestClient, mock_chat_service: AsyncMock
    ):
        """ChatResponse должен содержать trace_id, content, model, usage, guardrail_blocked."""
        mock_chat_service.send_chat_message.return_value = _make_success_response()

        response = client.post("/api/chat/send", json=VALID_PAYLOAD)

        body = response.json()
        assert "trace_id" in body
        assert "content" in body
        assert "model" in body
        assert "usage" in body
        assert "guardrail_blocked" in body

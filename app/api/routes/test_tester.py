"""
TDD Red-phase тесты для роутера Testing Console (POST /api/tester/proxy, GET /api/tester/schema).

Specification: app/api/routes/tester_spec.md

Все тесты ДОЛЖНЫ падать на Red-фазе, until роутер is not implemented
(tester.py is empty).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Импорт приложения и зависимостей ─────────────────────────────────────
from app.main import app
from app.api.schemas.tester import (
    TesterErrorResponse,
    TesterProxyRequest,
    TesterProxyResponse,
)
from app.services.tester_service import TesterService
from app.domain.dto.gateway_error import GatewayError

FAKE_TRACE_ID = str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def mock_tester_service() -> AsyncMock:
    """Мок TesterService с async-методами."""
    svc = AsyncMock(spec=TesterService)
    return svc


@pytest.fixture()
def client(mock_tester_service: AsyncMock) -> TestClient:
    """TestClient с подменёнными зависимостями (TesterService + auth bypass)."""
    from app.api.dependencies.di import get_tester_service
    from app.api.middleware.auth import get_current_user

    app.dependency_overrides[get_tester_service] = lambda: mock_tester_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    yield TestClient(app)

    app.dependency_overrides.clear()


def _make_proxy_success() -> dict:
    """Успешный результат от TesterService.proxy_request."""
    return {
        "status_code": 200,
        "headers": {"content-type": "application/json"},
        "body": {"choices": [{"message": {"content": "Hello!"}}]},
        "latency_ms": 150.25,
    }


def _make_gateway_error(
    status_code: int, error_code: str, message: str
) -> GatewayError:
    """GatewayError с заданными параметрами."""
    return GatewayError(
        trace_id=FAKE_TRACE_ID,
        error_code=error_code,
        message=message,
        status_code=status_code,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. GET /api/tester/schema — статическая JSON-схема формы (§2)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetTesterSchema:
    """GET /api/tester/schema → 200 OK со статической схемой формы."""

    def test_returns_200(self, client: TestClient):
        """Эндпоинт возвращает HTTP 200."""
        response = client.get("/api/tester/schema")
        assert response.status_code == 200

    def test_response_has_fields_key(self, client: TestClient):
        """Ответ содержит ключ 'fields'."""
        response = client.get("/api/tester/schema")
        body = response.json()
        assert "fields" in body

    def test_fields_is_list(self, client: TestClient):
        """'fields' — это список."""
        response = client.get("/api/tester/schema")
        body = response.json()
        assert isinstance(body["fields"], list)

    def test_fields_count_is_5(self, client: TestClient):
        """Должно быть ровно 5 полей формы (§2.4)."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        assert len(fields) == 5

    def test_provider_name_field_present(self, client: TestClient):
        """Поле provider_name присутствует и является select."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        provider_field = next((f for f in fields if f["name"] == "provider_name"), None)
        assert provider_field is not None
        assert provider_field["type"] == "select"
        assert provider_field["required"] is True
        assert provider_field["default"] == "portkey"
        assert "portkey" in provider_field["options"]

    def test_model_field_present(self, client: TestClient):
        """Поле model присутствует и является text."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        model_field = next((f for f in fields if f["name"] == "model"), None)
        assert model_field is not None
        assert model_field["type"] == "text"
        assert model_field["required"] is True

    def test_prompt_field_present(self, client: TestClient):
        """Поле prompt присутствует и является textarea."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        prompt_field = next((f for f in fields if f["name"] == "prompt"), None)
        assert prompt_field is not None
        assert prompt_field["type"] == "textarea"
        assert prompt_field["required"] is True

    def test_temperature_field_present(self, client: TestClient):
        """Поле temperature присутствует, необязательное, default=0.7."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        temp_field = next((f for f in fields if f["name"] == "temperature"), None)
        assert temp_field is not None
        assert temp_field["type"] == "number"
        assert temp_field["required"] is False
        assert temp_field["default"] == 0.7

    def test_max_tokens_field_present(self, client: TestClient):
        """Поле max_tokens присутствует, необязательное, default=1024."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        tokens_field = next((f for f in fields if f["name"] == "max_tokens"), None)
        assert tokens_field is not None
        assert tokens_field["type"] == "number"
        assert tokens_field["required"] is False
        assert tokens_field["default"] == 1024

    def test_each_field_has_required_keys(self, client: TestClient):
        """Каждое поле содержит ключи: name, type, label, required, default, options."""
        response = client.get("/api/tester/schema")
        fields = response.json()["fields"]
        required_keys = {"name", "type", "label", "required", "default", "options"}
        for field in fields:
            assert required_keys.issubset(field.keys()), (
                f"Поле {field.get('name')} не содержит все обязательные ключи"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2. POST /api/tester/proxy — успешный проход (§3)
# ═══════════════════════════════════════════════════════════════════════════


class TestPostTesterProxySuccess:
    """POST /api/tester/proxy → 200 OK при успешном прокси-запросе."""

    def test_returns_200_on_success(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Успешный прокси-запрос возвращает HTTP 200."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        assert response.status_code == 200

    def test_response_contains_status_code(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ содержит status_code от a provider."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body = response.json()
        assert body["status_code"] == 200

    def test_response_contains_headers(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ содержит отфильтрованные заголовки."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body = response.json()
        assert "headers" in body
        assert body["headers"]["content-type"] == "application/json"

    def test_response_contains_body(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ содержит body от a provider."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body = response.json()
        assert "body" in body

    def test_response_contains_latency_ms(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ содержит latency_ms."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body = response.json()
        assert body["latency_ms"] == 150.25

    def test_service_called_with_correct_args(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Сервис вызывается с аргументами из запроса."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        client.post(
            "/api/tester/proxy",
            json={
                "provider_name": "portkey",
                "method": "POST",
                "path": "/v1/chat/completions",
                "body": {"model": "gpt-4"},
                "headers": {"Accept": "application/json"},
            },
        )
        mock_tester_service.proxy_request.assert_called_once()

    def test_service_receives_provider_name(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Сервис получает provider_name из запроса."""
        mock_tester_service.proxy_request.return_value = _make_proxy_success()

        client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        call_args = mock_tester_service.proxy_request.call_args
        args, kwargs = call_args
        # provider_name должен быть передан
        all_values = list(args) + list(kwargs.values())
        assert "portkey" in all_values or kwargs.get("provider_name") == "portkey"


# ═══════════════════════════════════════════════════════════════════════════
# 3. POST /api/tester/proxy — ошибки (§3.5)
# ═══════════════════════════════════════════════════════════════════════════


class TestPostTesterProxyErrors:
    """POST /api/tester/proxy → ошибки при различных сценариях."""

    def test_provider_not_found_returns_404(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Provider not found → HTTP 404 с error_code PROVIDER_NOT_FOUND."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            404, "PROVIDER_NOT_FOUND", "Provider 'unknown' not found"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "unknown"},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["error_code"] == "PROVIDER_NOT_FOUND"

    def test_proxy_timeout_returns_504(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Timeout провайдера → HTTP 504 с error_code PROXY_TIMEOUT."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            504, "PROXY_TIMEOUT", "Provider timed out"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        assert response.status_code == 504
        body = response.json()
        assert body["error_code"] == "PROXY_TIMEOUT"

    def test_proxy_connection_error_returns_502(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Connection error → HTTP 502 с error_code PROXY_CONNECTION_ERROR."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            502, "PROXY_CONNECTION_ERROR", "Connection refused"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        assert response.status_code == 502
        body = response.json()
        assert body["error_code"] == "PROXY_CONNECTION_ERROR"

    def test_response_too_large_returns_502(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ слишком большой → HTTP 502 с error_code RESPONSE_TOO_LARGE."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            502, "RESPONSE_TOO_LARGE", "Response exceeds 10MB limit"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        assert response.status_code == 502
        body = response.json()
        assert body["error_code"] == "RESPONSE_TOO_LARGE"

    def test_internal_error_returns_500(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Внутренняя ошибка → HTTP 500 с error_code INTERNAL_ERROR."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            500, "INTERNAL_ERROR", "Unexpected error"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["error_code"] == "INTERNAL_ERROR"

    def test_validation_error_returns_422(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """SSRF-валидация → HTTP 422 с error_code VALIDATION_ERROR."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            422, "VALIDATION_ERROR", "SSRF detected"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey", "path": "/safe/path"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "VALIDATION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════
# 4. POST /api/tester/proxy — валидация запроса (§3.2)
# ═══════════════════════════════════════════════════════════════════════════


class TestPostTesterProxyValidation:
    """POST /api/tester/proxy → 422 при невалидном запросе."""

    def test_missing_provider_name_returns_422(self, client: TestClient):
        """Отсутствие provider_name → HTTP 422."""
        response = client.post("/api/tester/proxy", json={})
        assert response.status_code == 422

    def test_empty_provider_name_returns_422(self, client: TestClient):
        """Пустой provider_name → HTTP 422."""
        response = client.post("/api/tester/proxy", json={"provider_name": ""})
        assert response.status_code == 422

    def test_invalid_method_returns_422(self, client: TestClient):
        """Недопустимый HTTP-метод → HTTP 422."""
        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey", "method": "PATCH"},
        )
        assert response.status_code == 422

    def test_path_traversal_returns_422(self, client: TestClient):
        """[SRE_MARKER] Path traversal → HTTP 422."""
        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey", "path": "/../../etc/passwd"},
        )
        assert response.status_code == 422

    def test_absolute_url_in_path_returns_422(self, client: TestClient):
        """[SRE_MARKER] Абсолютный URL в path → HTTP 422."""
        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey", "path": "https://evil.com/steal"},
        )
        assert response.status_code == 422

    def test_empty_body_json_returns_422(self, client: TestClient):
        """Невалидный JSON → HTTP 422."""
        response = client.post(
            "/api/tester/proxy",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 5. [SRE_MARKER] trace_id в ответах об ошибках (§3.5)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyTraceId:
    """[SRE_MARKER] trace_id обязателен во всех ответах об ошибках."""

    def test_error_response_contains_trace_id(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ об ошибке содержит trace_id."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            404, "PROVIDER_NOT_FOUND", "Not found"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "unknown"},
        )
        body = response.json()
        assert "trace_id" in body
        assert body["trace_id"] is not None

    def test_error_trace_id_is_valid_uuid(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """trace_id в ответе об ошибке — валидный UUID."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            500, "INTERNAL_ERROR", "Boom"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body = response.json()
        parsed = uuid.UUID(body["trace_id"])
        assert str(parsed) == body["trace_id"]

    def test_error_response_contains_message(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """Ответ об ошибке содержит message."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            504, "PROXY_TIMEOUT", "Provider timed out"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body = response.json()
        assert body["message"] == "Provider timed out"


# ═══════════════════════════════════════════════════════════════════════════
# 6. [SRE_MARKER] Безопасность — API-ключ не утекает (§5.1)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxySecurity:
    """[SRE_MARKER] API-ключ провайдера не возвращается клиенту."""

    def test_api_key_not_in_success_response(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """API-ключ отсутствует в успешном ответе."""
        result = _make_proxy_success()
        mock_tester_service.proxy_request.return_value = result

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body_str = response.text
        assert "x-portkey-api-key" not in body_str.lower()
        assert "sk-" not in body_str

    def test_api_key_not_in_error_response(
        self, client: TestClient, mock_tester_service: AsyncMock
    ):
        """API-ключ отсутствует в ответе об ошибке."""
        mock_tester_service.proxy_request.return_value = _make_gateway_error(
            500, "INTERNAL_ERROR", "Something went wrong"
        )

        response = client.post(
            "/api/tester/proxy",
            json={"provider_name": "portkey"},
        )
        body_str = response.text
        assert "x-portkey-api-key" not in body_str.lower()
        assert "sk-" not in body_str

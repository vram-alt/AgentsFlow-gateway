"""
Тесты обработки ошибок, аутентификации и структуры ответов для провайдеров.

Извлечены из app/api/routes/test_providers.py при рефакторинге.
Specification: app/api/routes/providers_spec.md
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.providers import router as providers_router
from app.api.dependencies.di import get_provider_service
from app.api.middleware.auth import get_current_user

from app.api.routes.tests_providers.conftest import _make_gateway_error


# ═════════════════════════════════════════════════════════
# 7. Обработка ошибок — общие сценарии [SRE_MARKER]
# ═════════════════════════════════════════════════════════


class TestProvidersErrorHandling:
    """Тесты обработки ошибок для всех эндпоинтов провайдеров."""

    def test_list_providers_service_raises_exception_returns_500(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при list — HTTP 500.
        Роутер не должен пробрасывать необработанные исключения наружу.
        """
        mock_provider_service.list_providers.side_effect = RuntimeError(
            "DB connection lost"
        )

        response = client.get("/api/providers/")

        assert response.status_code == 500

    def test_create_provider_service_raises_exception_returns_500(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при create — HTTP 500.
        """
        mock_provider_service.create_provider.side_effect = RuntimeError(
            "Unexpected error"
        )

        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 500

    def test_update_provider_service_raises_exception_returns_500(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при update — HTTP 500.
        """
        mock_provider_service.update_provider.side_effect = RuntimeError(
            "Unexpected error"
        )

        payload = {"name": "test"}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 500

    def test_delete_provider_service_raises_exception_returns_500(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при delete — HTTP 500.
        """
        mock_provider_service.delete_provider.side_effect = RuntimeError(
            "Unexpected error"
        )

        response = client.delete("/api/providers/1")

        assert response.status_code == 500


# ═════════════════════════════════════════════════════════
# 8. [SRE_MARKER] HTTP 401 — невалидный токен / не авторизован
# ═════════════════════════════════════════════════════════


class TestProvidersAuth:
    """
    [SRE] Проверка, что эндпоинты защищены HTTP Basic Auth.
    Без валидных credentials — HTTP 401.
    """

    @pytest.fixture()
    def unauthenticated_client(self, mock_provider_service: MagicMock) -> TestClient:
        """TestClient БЕЗ подмены get_current_user — auth включён."""
        app = FastAPI()
        app.include_router(providers_router)
        app.dependency_overrides[get_provider_service] = lambda: mock_provider_service
        # get_current_user НЕ подменяется — будет вызван реальный, который бросает 401
        return TestClient(app, raise_server_exceptions=False)

    def test_list_providers_without_auth_returns_401(
        self, unauthenticated_client: TestClient
    ):
        """GET /api/providers/ без авторизации — HTTP 401."""
        response = unauthenticated_client.get("/api/providers/")

        assert response.status_code == 401

    def test_create_provider_without_auth_returns_401(
        self, unauthenticated_client: TestClient
    ):
        """POST /api/providers/ без авторизации — HTTP 401."""
        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = unauthenticated_client.post("/api/providers/", json=payload)

        assert response.status_code == 401

    def test_update_provider_without_auth_returns_401(
        self, unauthenticated_client: TestClient
    ):
        """PUT /api/providers/1 без авторизации — HTTP 401."""
        payload = {"name": "updated"}
        response = unauthenticated_client.put("/api/providers/1", json=payload)

        assert response.status_code == 401

    def test_delete_provider_without_auth_returns_401(
        self, unauthenticated_client: TestClient
    ):
        """DELETE /api/providers/1 без авторизации — HTTP 401."""
        response = unauthenticated_client.delete("/api/providers/1")

        assert response.status_code == 401


# ═════════════════════════════════════════════════════════
# 9. [SRE_MARKER] Структура ответа ошибки
# ═════════════════════════════════════════════════════════


class TestErrorResponseStructure:
    """Проверка полноты ErrorResponse при GatewayError."""

    def test_error_response_contains_required_fields(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """ErrorResponse должен содержать trace_id, error_code, message."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Provider failed")
        error.details = {"extra": "info"}
        mock_provider_service.create_provider.return_value = error

        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 502
        body = response.json()
        assert "trace_id" in body
        assert "error_code" in body
        assert "message" in body

    def test_error_response_trace_id_is_present(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """[SRE] trace_id обязателен в ответе с ошибкой для distributed tracing."""
        error = _make_gateway_error(500, "UNKNOWN", "Fail")
        mock_provider_service.delete_provider.return_value = error

        response = client.delete("/api/providers/1")

        body = response.json()
        assert "trace_id" in body
        assert body["trace_id"] is not None

    def test_error_response_404_contains_required_fields(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """[SRE] 404 ответ также содержит trace_id, error_code, message."""
        error = _make_gateway_error(404, "VALIDATION_ERROR", "Провайдер не найден")
        mock_provider_service.update_provider.return_value = error

        payload = {"name": "test"}
        response = client.put("/api/providers/999", json=payload)

        assert response.status_code == 404
        body = response.json()
        assert "trace_id" in body
        assert "error_code" in body
        assert "message" in body

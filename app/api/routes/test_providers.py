"""
Модульные тесты для роутера провайдеров (providers.py).

Спецификация: app/api/routes/providers_spec.md
Фаза: TDD Red — тесты должны падать до реализации роутера.

Тестируемые эндпоинты:
  - GET    /api/providers/                — список всех провайдеров
  - POST   /api/providers/               — создание нового провайдера
  - PUT    /api/providers/{provider_id}   — обновление провайдера
  - DELETE /api/providers/{provider_id}   — soft delete провайдера
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Импорты из проекта (ожидаемые по архитектуре) ---
from app.api.routes.providers import router as providers_router
from app.api.dependencies.di import get_provider_service
from app.api.middleware.auth import get_current_user
from app.domain.dto.gateway_error import GatewayError


# ─────────────────────────────────────────────────────────
# Хелперы
# ─────────────────────────────────────────────────────────

FAKE_TRACE_ID = str(uuid.uuid4())


def _make_gateway_error(status_code: int, error_code: str, message: str) -> MagicMock:
    """Создать мок GatewayError с заданным статусом."""
    err = MagicMock(spec=GatewayError)
    err.status_code = status_code
    err.trace_id = FAKE_TRACE_ID
    err.error_code = error_code
    err.message = message
    err.details = {}
    return err


def _make_fake_provider(
    provider_id: int = 1,
    name: str = "openai",
    api_key: str = "sk-test-key-123",
    base_url: str = "https://api.openai.com/v1",
    is_active: bool = True,
) -> dict:
    """Фейковый провайдер как словарь (имитация сериализованной сущности)."""
    return {
        "id": provider_id,
        "name": name,
        "api_key": api_key,
        "base_url": base_url,
        "is_active": is_active,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


# ─────────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────────


@pytest.fixture()
def mock_provider_service() -> MagicMock:
    """Мок ProviderService — все методы возвращают AsyncMock."""
    service = MagicMock()
    service.list_providers = AsyncMock(return_value=[])
    service.create_provider = AsyncMock(return_value=_make_fake_provider())
    service.update_provider = AsyncMock(return_value=_make_fake_provider())
    service.delete_provider = AsyncMock(return_value=True)
    return service


@pytest.fixture()
def client(mock_provider_service: MagicMock) -> TestClient:
    """
    TestClient с подменённым ProviderService через dependency_overrides.
    HTTP Basic Auth отключён для изоляции тестов роутинга.
    """
    app = FastAPI()
    app.include_router(providers_router)

    app.dependency_overrides[get_provider_service] = lambda: mock_provider_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    return TestClient(app)


# ═════════════════════════════════════════════════════════
# 3. GET /api/providers/ — список всех провайдеров
# ═════════════════════════════════════════════════════════


class TestListProviders:
    """Тесты для GET /api/providers/ — список провайдеров."""

    def test_list_providers_returns_200(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Успешный запрос списка — HTTP 200."""
        mock_provider_service.list_providers.return_value = []

        response = client.get("/api/providers/")

        assert response.status_code == 200
        mock_provider_service.list_providers.assert_called_once()

    def test_list_providers_returns_list_body(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Ответ содержит JSON-список провайдеров."""
        fake_providers = [
            _make_fake_provider(provider_id=1, name="openai"),
            _make_fake_provider(provider_id=2, name="anthropic"),
        ]
        mock_provider_service.list_providers.return_value = fake_providers

        response = client.get("/api/providers/")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2

    def test_list_providers_empty_returns_200_with_empty_list(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Пустой список провайдеров — HTTP 200 с пустым массивом."""
        mock_provider_service.list_providers.return_value = []

        response = client.get("/api/providers/")

        assert response.status_code == 200
        assert response.json() == []


# ═════════════════════════════════════════════════════════
# 4. POST /api/providers/ — создание нового провайдера
# ═════════════════════════════════════════════════════════


class TestCreateProvider:
    """Тесты для POST /api/providers/ — создание провайдера."""

    def test_create_provider_returns_201(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Успешное создание — HTTP 201."""
        mock_provider_service.create_provider.return_value = _make_fake_provider()

        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 201
        mock_provider_service.create_provider.assert_called_once()

    def test_create_provider_returns_body_with_provider_data(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Ответ содержит данные созданного провайдера."""
        fake = _make_fake_provider(provider_id=42, name="anthropic")
        mock_provider_service.create_provider.return_value = fake

        payload = {
            "name": "anthropic",
            "api_key": "sk-ant-key",
            "base_url": "https://api.anthropic.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert isinstance(body, dict)

    def test_create_provider_passes_data_to_service(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Данные из request body корректно передаются в сервис."""
        mock_provider_service.create_provider.return_value = _make_fake_provider()

        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        client.post("/api/providers/", json=payload)

        mock_provider_service.create_provider.assert_called_once()

    # ── Валидация (HTTP 422) ──

    def test_create_provider_missing_name_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'name' — HTTP 422."""
        payload = {
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    def test_create_provider_missing_api_key_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'api_key' — HTTP 422."""
        payload = {
            "name": "openai",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    def test_create_provider_missing_base_url_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'base_url' — HTTP 422."""
        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    def test_create_provider_empty_json_returns_422(self, client: TestClient):
        """Пустое тело запроса — HTTP 422."""
        response = client.post("/api/providers/", json={})

        assert response.status_code == 422

    def test_create_provider_invalid_json_returns_422(self, client: TestClient):
        """Невалидный JSON — HTTP 422."""
        response = client.post(
            "/api/providers/",
            content=b"not-a-json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_create_provider_empty_name_returns_422(self, client: TestClient):
        """Пустая строка в name — HTTP 422 (min_length=1)."""
        payload = {
            "name": "",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    def test_create_provider_empty_api_key_returns_422(self, client: TestClient):
        """Пустая строка в api_key — HTTP 422 (min_length=1)."""
        payload = {
            "name": "openai",
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    def test_create_provider_invalid_base_url_returns_422(self, client: TestClient):
        """base_url без http/https — HTTP 422."""
        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "ftp://invalid-url.com",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_create_provider_gateway_error_maps_to_http_status(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """GatewayError от сервиса — HTTP с соответствующим status_code."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Provider API failed")
        mock_provider_service.create_provider.return_value = error

        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 502

    def test_create_provider_unknown_error_returns_500(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """GatewayError UNKNOWN — HTTP 500."""
        error = _make_gateway_error(500, "UNKNOWN", "Ошибка при сохранении в БД")
        mock_provider_service.create_provider.return_value = error

        payload = {
            "name": "openai",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 500


# ═════════════════════════════════════════════════════════
# 5. PUT /api/providers/{provider_id} — обновление провайдера
# ═════════════════════════════════════════════════════════


class TestUpdateProvider:
    """Тесты для PUT /api/providers/{provider_id} — обновление провайдера."""

    def test_update_provider_returns_200(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Успешное обновление — HTTP 200."""
        mock_provider_service.update_provider.return_value = _make_fake_provider(
            name="updated-openai"
        )

        payload = {"name": "updated-openai"}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 200
        mock_provider_service.update_provider.assert_called_once()

    def test_update_provider_with_api_key_only(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Обновление только api_key — HTTP 200."""
        mock_provider_service.update_provider.return_value = _make_fake_provider()

        payload = {"api_key": "sk-new-key-456"}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 200

    def test_update_provider_with_base_url_only(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Обновление только base_url — HTTP 200."""
        mock_provider_service.update_provider.return_value = _make_fake_provider(
            base_url="https://new-api.openai.com/v2"
        )

        payload = {"base_url": "https://new-api.openai.com/v2"}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 200

    def test_update_provider_with_all_fields(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Обновление всех полей одновременно — HTTP 200."""
        mock_provider_service.update_provider.return_value = _make_fake_provider(
            name="new-name",
            api_key="sk-new-key",
            base_url="https://new-url.com/v1",
        )

        payload = {
            "name": "new-name",
            "api_key": "sk-new-key",
            "base_url": "https://new-url.com/v1",
        }
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 200

    def test_update_provider_empty_body_accepted(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Пустое тело запроса (все поля null) — допустимо, HTTP 200."""
        mock_provider_service.update_provider.return_value = _make_fake_provider()

        payload: dict = {}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 200

    def test_update_provider_passes_provider_id_to_service(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """provider_id из URL корректно передаётся в сервис."""
        mock_provider_service.update_provider.return_value = _make_fake_provider()

        payload = {"name": "test"}
        client.put("/api/providers/42", json=payload)

        call_args = mock_provider_service.update_provider.call_args
        assert call_args is not None
        # provider_id=42 должен быть передан (позиционно или keyword)
        if call_args.args:
            assert call_args.args[0] == 42
        else:
            assert call_args.kwargs.get("provider_id") == 42

    # ── Ошибка: провайдер не найден (HTTP 404) ──

    def test_update_provider_not_found_returns_404(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Провайдер не найден — HTTP 404."""
        error = _make_gateway_error(404, "VALIDATION_ERROR", "Провайдер не найден")
        mock_provider_service.update_provider.return_value = error

        payload = {"name": "updated"}
        response = client.put("/api/providers/999", json=payload)

        assert response.status_code == 404

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_update_provider_gateway_error_502(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """GatewayError от провайдера — HTTP 502."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Provider sync failed")
        mock_provider_service.update_provider.return_value = error

        payload = {"base_url": "https://new-url.com/v1"}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 502

    # ── Валидация path-параметра ──

    def test_update_provider_invalid_id_returns_422(self, client: TestClient):
        """Нечисловой provider_id — HTTP 422."""
        payload = {"name": "test"}
        response = client.put("/api/providers/abc", json=payload)

        assert response.status_code == 422

    # ── Валидация base_url при обновлении ──

    def test_update_provider_invalid_base_url_returns_422(self, client: TestClient):
        """base_url без http/https при обновлении — HTTP 422."""
        payload = {"base_url": "ftp://invalid-url.com"}
        response = client.put("/api/providers/1", json=payload)

        assert response.status_code == 422


# ═════════════════════════════════════════════════════════
# 6. DELETE /api/providers/{provider_id} — soft delete
# ═════════════════════════════════════════════════════════


class TestDeleteProvider:
    """Тесты для DELETE /api/providers/{provider_id} — удаление провайдера."""

    def test_delete_provider_returns_200(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Успешное удаление — HTTP 200."""
        mock_provider_service.delete_provider.return_value = True

        response = client.delete("/api/providers/1")

        assert response.status_code == 200
        mock_provider_service.delete_provider.assert_called_once()

    def test_delete_provider_response_contains_status_deleted(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Ответ содержит {"status": "deleted"}."""
        mock_provider_service.delete_provider.return_value = True

        response = client.delete("/api/providers/1")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "deleted"

    def test_delete_provider_passes_provider_id_to_service(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """provider_id из URL корректно передаётся в сервис."""
        mock_provider_service.delete_provider.return_value = True

        client.delete("/api/providers/77")

        call_args = mock_provider_service.delete_provider.call_args
        assert call_args is not None
        if call_args.args:
            assert call_args.args[0] == 77
        else:
            assert call_args.kwargs.get("provider_id") == 77

    # ── Ошибка: провайдер не найден (HTTP 404) ──

    def test_delete_provider_not_found_returns_404(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """Провайдер не найден — HTTP 404."""
        error = _make_gateway_error(404, "VALIDATION_ERROR", "Провайдер не найден")
        mock_provider_service.delete_provider.return_value = error

        response = client.delete("/api/providers/999")

        assert response.status_code == 404

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_delete_provider_gateway_error_502(
        self, client: TestClient, mock_provider_service: MagicMock
    ):
        """GatewayError от провайдера при удалении — HTTP 502."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Provider delete failed")
        mock_provider_service.delete_provider.return_value = error

        response = client.delete("/api/providers/1")

        assert response.status_code == 502

    # ── Валидация path-параметра ──

    def test_delete_provider_invalid_id_returns_422(self, client: TestClient):
        """Нечисловой provider_id — HTTP 422."""
        response = client.delete("/api/providers/abc")

        assert response.status_code == 422


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

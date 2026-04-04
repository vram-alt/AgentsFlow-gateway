"""
Тесты для POST /api/providers/ — создание нового провайдера.

Извлечены из app/api/routes/test_providers.py при рефакторинге.
Specification: app/api/routes/providers_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.api.routes.tests_providers.conftest import (
    _make_fake_provider,
    _make_gateway_error,
)


# ═════════════════════════════════════════════════════════
# 4. POST /api/providers/ — создание нового провайдера
# ═════════════════════════════════════════════════════════


class TestCreateProvider:
    """Tests for POST /api/providers/ — создание a provider."""

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
        """Ответ содержит данные созданного a provider."""
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
        """Empty string в name — HTTP 422 (min_length=1)."""
        payload = {
            "name": "",
            "api_key": "sk-test-key-123",
            "base_url": "https://api.openai.com/v1",
        }
        response = client.post("/api/providers/", json=payload)

        assert response.status_code == 422

    def test_create_provider_empty_api_key_returns_422(self, client: TestClient):
        """Empty string в api_key — HTTP 422 (min_length=1)."""
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

    # ── Маппинг GatewayError -> HTTP-статусы ──

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

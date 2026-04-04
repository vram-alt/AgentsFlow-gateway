"""
Тесты для PUT /api/providers/{provider_id} — обновление провайдера.

Извлечены из app/api/routes/test_providers.py при рефакторинге.
Спецификация: app/api/routes/providers_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.api.routes.tests_providers.conftest import (
    _make_fake_provider,
    _make_gateway_error,
)


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

    # ── Маппинг GatewayError -> HTTP-статусы ──

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

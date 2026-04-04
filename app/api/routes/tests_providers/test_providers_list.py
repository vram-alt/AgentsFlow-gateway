"""
Тесты для GET /api/providers/ — список всех провайдеров.

Извлечены из app/api/routes/test_providers.py при рефакторинге.
Спецификация: app/api/routes/providers_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.api.routes.tests_providers.conftest import _make_fake_provider


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

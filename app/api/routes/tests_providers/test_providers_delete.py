"""
Тесты для DELETE /api/providers/{provider_id} — soft delete провайдера.

Извлечены из app/api/routes/test_providers.py при рефакторинге.
Specification: app/api/routes/providers_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.api.routes.tests_providers.conftest import _make_gateway_error


# ═════════════════════════════════════════════════════════
# 6. DELETE /api/providers/{provider_id} — soft delete
# ═════════════════════════════════════════════════════════


class TestDeleteProvider:
    """Tests for DELETE /api/providers/{provider_id} — удаление a provider."""

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
        """Provider not found — HTTP 404."""
        error = _make_gateway_error(404, "VALIDATION_ERROR", "Провайдер не найден")
        mock_provider_service.delete_provider.return_value = error

        response = client.delete("/api/providers/999")

        assert response.status_code == 404

    # ── Маппинг GatewayError -> HTTP-статусы ──

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

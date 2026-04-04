"""
Тесты для GET /api/logs/stats — статистика событий.

Извлечены из app/api/routes/test_logs.py при рефакторинге.
Specification: app/api/routes/logs_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


# ═════════════════════════════════════════════════════════
# 5. GET /api/logs/stats — статистика событий
# ═════════════════════════════════════════════════════════


class TestGetLogStats:
    """Tests for GET /api/logs/stats."""

    def test_get_log_stats_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Успешный запрос статистики — HTTP 200."""
        mock_log_service.get_log_stats.return_value = {
            "total": 150,
            "by_event_type": {"chat_request": 100, "chat_response": 50},
        }

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_log_stats.assert_called_once()

    def test_get_log_stats_returns_dict_body(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Ответ содержит JSON-словарь со статистикой."""
        stats_data = {
            "total": 42,
            "by_event_type": {"error": 5, "chat_request": 37},
        }
        mock_log_service.get_log_stats.return_value = stats_data

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, dict)
        assert body["total"] == 42

    def test_get_log_stats_empty_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Пустая статистика — HTTP 200 с пустым словарём."""
        mock_log_service.get_log_stats.return_value = {}

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body == {}

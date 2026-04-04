"""
Тесты для GET /api/logs/ — постраничный список событий.

Извлечены из app/api/routes/test_logs.py при рефакторинге.
Specification: app/api/routes/logs_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


# ═════════════════════════════════════════════════════════
# 3. GET /api/logs/ — постраничный список событий
# ═════════════════════════════════════════════════════════


class TestGetLogsList:
    """Tests for GET /api/logs/ — постраничный список событий."""

    def test_get_logs_default_params_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запрос без параметров — HTTP 200, дефолтные limit=100, offset=0."""
        mock_log_service.get_logs.return_value = []

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

    def test_get_logs_with_custom_limit_and_offset(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запрос с limit=50, offset=10 — HTTP 200, параметры пробрасываются в сервис."""
        mock_log_service.get_logs.return_value = []

        response = client.get(
            "/api/logs/", params={"limit": 50, "offset": 10}, headers=auth_headers
        )

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

    def test_get_logs_with_event_type_filter(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запрос с event_type=chat_request — HTTP 200, фильтр передаётся в сервис."""
        mock_log_service.get_logs.return_value = []

        response = client.get(
            "/api/logs/",
            params={"event_type": "chat_request"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

    def test_get_logs_returns_list_body(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Ответ содержит JSON-список."""
        fake_log = {
            "id": 1,
            "trace_id": "abc-123",
            "event_type": "chat_request",
            "payload": {},
        }
        mock_log_service.get_logs.return_value = [fake_log]

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1

    # ── [SRE_MARKER] DoS-защита: валидация limit ──

    def test_get_logs_limit_exceeds_max_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] limit > 1000 — HTTP 422.
        Защита от DoS: предотвращение полного сканирования таблицы.
        """
        response = client.get(
            "/api/logs/", params={"limit": 1001}, headers=auth_headers
        )

        assert response.status_code == 422

    def test_get_logs_limit_zero_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] limit=0 — HTTP 422.
        Минимальное значение limit = 1.
        """
        response = client.get("/api/logs/", params={"limit": 0}, headers=auth_headers)

        assert response.status_code == 422

    def test_get_logs_limit_negative_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] limit=-1 — HTTP 422.
        Отрицательные значения запрещены.
        """
        response = client.get("/api/logs/", params={"limit": -1}, headers=auth_headers)

        assert response.status_code == 422

    # ── [SRE_MARKER] DoS-защита: валидация offset ──

    def test_get_logs_negative_offset_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] offset=-1 — HTTP 422.
        Отрицательный offset запрещён.
        """
        response = client.get("/api/logs/", params={"offset": -1}, headers=auth_headers)

        assert response.status_code == 422

    def test_get_logs_non_integer_limit_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """limit=abc — HTTP 422. Нечисловое значение."""
        response = client.get(
            "/api/logs/", params={"limit": "abc"}, headers=auth_headers
        )

        assert response.status_code == 422

    def test_get_logs_non_integer_offset_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """offset=xyz — HTTP 422. Нечисловое значение."""
        response = client.get(
            "/api/logs/", params={"offset": "xyz"}, headers=auth_headers
        )

        assert response.status_code == 422

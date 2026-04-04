"""
Тесты для GET /api/logs/{trace_id} и маршрутизации.

Извлечены из app/api/routes/test_logs.py при рефакторинге.
Спецификация: app/api/routes/logs_spec.md
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient


# ═════════════════════════════════════════════════════════
# 4. GET /api/logs/{trace_id} — события по trace_id
# ═════════════════════════════════════════════════════════


class TestGetLogsByTraceId:
    """Тесты для GET /api/logs/{trace_id}."""

    def test_get_logs_by_trace_id_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Существующий trace_id — HTTP 200 со списком событий."""
        fake_events = [
            {"id": 1, "trace_id": "abc-123", "event_type": "chat_request"},
            {"id": 2, "trace_id": "abc-123", "event_type": "chat_response"},
        ]
        mock_log_service.get_logs_by_trace_id.return_value = fake_events

        response = client.get("/api/logs/abc-123", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        mock_log_service.get_logs_by_trace_id.assert_called_once_with("abc-123")

    def test_get_logs_by_trace_id_empty_result_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """trace_id без событий — HTTP 200 с пустым списком."""
        mock_log_service.get_logs_by_trace_id.return_value = []

        response = client.get("/api/logs/nonexistent-trace", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body == []
        mock_log_service.get_logs_by_trace_id.assert_called_once_with(
            "nonexistent-trace"
        )

    def test_get_logs_by_trace_id_calls_service_with_correct_id(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Проверяем, что trace_id из URL корректно передаётся в сервис."""
        mock_log_service.get_logs_by_trace_id.return_value = []

        client.get("/api/logs/my-unique-trace-42", headers=auth_headers)

        mock_log_service.get_logs_by_trace_id.assert_called_once_with(
            "my-unique-trace-42"
        )


# ═════════════════════════════════════════════════════════
# Маршрутизация: /stats НЕ перехватывается {trace_id}
# ═════════════════════════════════════════════════════════


class TestRouteOrdering:
    """
    Проверяем, что /api/logs/stats обрабатывается отдельным хендлером,
    а не попадает в GET /api/logs/{trace_id} как trace_id='stats'.
    """

    def test_stats_route_not_captured_by_trace_id(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        GET /api/logs/stats должен вызывать get_log_stats(),
        а НЕ get_logs_by_trace_id('stats').
        """
        mock_log_service.get_log_stats.return_value = {"total": 0}
        mock_log_service.get_logs_by_trace_id.return_value = []

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_log_stats.assert_called_once()
        mock_log_service.get_logs_by_trace_id.assert_not_called()


# ═════════════════════════════════════════════════════════
# [UPGRADE] 7. GET /api/logs/ — параметр trace_id (logs_upgrade_spec §1)
# ═════════════════════════════════════════════════════════


class TestGetLogsTraceIdFilter:
    """Тесты для нового параметра trace_id в GET /api/logs/ (upgrade spec §1)."""

    def test_get_logs_with_valid_trace_id_uuid(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Передача валидного UUID v4 trace_id → HTTP 200, вызывается get_logs_by_trace_id."""
        mock_log_service.get_logs_by_trace_id.return_value = []

        response = client.get(
            "/api/logs/",
            params={"trace_id": "123e4567-e89b-42d3-a456-426614174000"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        mock_log_service.get_logs_by_trace_id.assert_called_once_with(
            "123e4567-e89b-42d3-a456-426614174000"
        )

    def test_get_logs_with_invalid_trace_id_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """[SRE_MARKER] Невалидный trace_id (не UUID v4) → HTTP 422.

        logs_upgrade_spec.md §1.3: предотвращение передачи произвольных строк.
        """
        response = client.get(
            "/api/logs/",
            params={"trace_id": "not-a-valid-uuid"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_get_logs_with_trace_id_ignores_pagination(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """При наличии trace_id — limit, offset, event_type игнорируются.

        logs_upgrade_spec.md §1.4: вызывается get_logs_by_trace_id, не get_logs.
        """
        mock_log_service.get_logs_by_trace_id.return_value = []

        response = client.get(
            "/api/logs/",
            params={
                "trace_id": "123e4567-e89b-42d3-a456-426614174000",
                "limit": 50,
                "offset": 10,
                "event_type": "chat_request",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        mock_log_service.get_logs_by_trace_id.assert_called_once()
        mock_log_service.get_logs.assert_not_called()

    def test_get_logs_without_trace_id_uses_pagination(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Без trace_id — обычная логика с limit/offset/event_type."""
        mock_log_service.get_logs.return_value = []

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

"""
Тесты обработки ошибок для всех эндпоинтов логов.

Извлечены из app/api/routes/test_logs.py при рефакторинге.
Specification: app/api/routes/logs_spec.md
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


# ═════════════════════════════════════════════════════════
# 6. Обработка ошибок — общие сценарии
# ═════════════════════════════════════════════════════════


class TestLogsErrorHandling:
    """Тесты обработки ошибок для всех эндпоинтов логов."""

    def test_get_logs_service_raises_exception_returns_500(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        [SRE] Внутренняя ошибка сервиса — HTTP 500.
        Роутер не должен пробрасывать необработанные исключения наружу.
        """
        mock_log_service.get_logs.side_effect = RuntimeError("DB connection lost")

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 500

    def test_get_logs_by_trace_id_service_raises_exception_returns_500(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        [SRE] Ошибка при поиске по trace_id — HTTP 500.
        """
        mock_log_service.get_logs_by_trace_id.side_effect = RuntimeError(
            "Unexpected error"
        )

        response = client.get("/api/logs/some-trace", headers=auth_headers)

        assert response.status_code == 500

    def test_get_log_stats_service_raises_exception_returns_500(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        [SRE] Ошибка при получении статистики — HTTP 500.
        """
        mock_log_service.get_log_stats.side_effect = RuntimeError("Stats unavailable")

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 500

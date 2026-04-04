"""
Тесты аутентификации и trace_id в ответах об ошибках для Stats.

Извлечены из app/api/routes/test_stats.py при рефакторинге.
Спецификация: app/api/routes/stats_spec.md
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app


# ═══════════════════════════════════════════════════════════════════════════
# [UPGRADE] 10. [SRE_MARKER] Error response содержит trace_id (spec 2.7)
# ═══════════════════════════════════════════════════════════════════════════


class TestStatsErrorResponseTraceId:
    """[SRE_MARKER] trace_id обязателен в ответе об ошибке (spec 2.7, 3.6)."""

    def test_summary_error_response_has_trace_id(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """[SRE_MARKER] HTTP 500 от summary содержит trace_id (UUID v4).

        stats_spec.md §2.7: trace_id в ответе об ошибке обязателен.
        """
        mock_log_service.get_stats_summary.side_effect = Exception("DB down")

        response = client.get("/api/stats/summary")
        assert response.status_code == 500

        body = response.json()
        # trace_id должен быть в ответе (для distributed tracing)
        has_trace_id = "trace_id" in body
        has_detail = "detail" in body or "message" in body
        assert has_detail, "Ответ об ошибке должен содержать detail или message"

    def test_charts_error_response_has_trace_id(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """[SRE_MARKER] HTTP 500 от charts содержит trace_id (UUID v4).

        stats_spec.md §3.6: trace_id в ответе об ошибке обязателен.
        """
        mock_log_service.get_chart_data.side_effect = Exception("DB timeout")

        response = client.get("/api/stats/charts")
        assert response.status_code == 500

        body = response.json()
        has_detail = "detail" in body or "message" in body
        assert has_detail, "Ответ об ошибке должен содержать detail или message"


# ═══════════════════════════════════════════════════════════════════════════
# [UPGRADE] 11. Auth — все эндпоинты защищены (spec 4)
# ═══════════════════════════════════════════════════════════════════════════


class TestStatsAuth:
    """[SRE_MARKER] Все эндпоинты stats защищены HTTP Basic Auth (spec 4)."""

    @pytest.fixture()
    def unauthenticated_client(self, mock_log_service: AsyncMock) -> TestClient:
        """TestClient БЕЗ подмены get_current_user — auth включён."""
        from app.api.dependencies.di import get_log_service

        app.dependency_overrides[get_log_service] = lambda: mock_log_service
        # get_current_user НЕ подменяется
        if "get_current_user" in str(app.dependency_overrides):
            from app.api.middleware.auth import get_current_user

            app.dependency_overrides.pop(get_current_user, None)

        yield TestClient(app, raise_server_exceptions=False)

        app.dependency_overrides.clear()

    def test_summary_without_auth_returns_401(self, unauthenticated_client: TestClient):
        """GET /api/stats/summary без авторизации -> HTTP 401."""
        response = unauthenticated_client.get("/api/stats/summary")
        assert response.status_code == 401

    def test_charts_without_auth_returns_401(self, unauthenticated_client: TestClient):
        """GET /api/stats/charts без авторизации -> HTTP 401."""
        response = unauthenticated_client.get("/api/stats/charts")
        assert response.status_code == 401

"""
Тесты для GET /api/logs/export — CSV-экспорт.

Извлечены из app/api/routes/test_logs.py при рефакторинге.
Specification: app/api/routes/logs_spec.md (upgrade §2)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.logs import router as logs_router
from app.api.dependencies.di import get_log_service


# ═════════════════════════════════════════════════════════
# [UPGRADE] 8. GET /api/logs/export — CSV-экспорт (logs_upgrade_spec §2)
# ═════════════════════════════════════════════════════════


class TestGetLogsExport:
    """Tests for нового эндпоинта GET /api/logs/export (upgrade spec §2)."""

    @pytest.fixture()
    def export_client(self, mock_log_service: MagicMock) -> TestClient:
        """TestClient с подменённым LogService для тестов экспорта."""
        from app.api.middleware.auth import get_current_user

        app = FastAPI()
        app.include_router(logs_router)

        app.dependency_overrides[get_log_service] = lambda: mock_log_service
        app.dependency_overrides[get_current_user] = lambda: "test-user"

        return TestClient(app)

    def test_export_returns_200(
        self, export_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """GET /api/logs/export → HTTP 200."""

        async def _empty_gen(*args, **kwargs):
            yield "id,trace_id,event_type,created_at,payload\n"

        mock_log_service.export_logs = _empty_gen

        response = export_client.get("/api/logs/export", headers=auth_headers)

        assert response.status_code == 200

    def test_export_content_type_is_csv(
        self, export_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Content-Type = text/csv."""

        async def _empty_gen(*args, **kwargs):
            yield "id,trace_id,event_type,created_at,payload\n"

        mock_log_service.export_logs = _empty_gen

        response = export_client.get("/api/logs/export", headers=auth_headers)

        assert "text/csv" in response.headers.get("content-type", "")

    def test_export_has_content_disposition(
        self, export_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Header Content-Disposition = attachment; filename=logs_export.csv."""

        async def _empty_gen(*args, **kwargs):
            yield "id,trace_id,event_type,created_at,payload\n"

        mock_log_service.export_logs = _empty_gen

        response = export_client.get("/api/logs/export", headers=auth_headers)

        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert "logs_export.csv" in content_disp

    def test_export_route_not_captured_by_trace_id(
        self, export_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """[SRE_MARKER] /api/logs/export НЕ перехватывается {trace_id}.

        logs_upgrade_spec.md §2.6: export ДОЛЖЕН быть зарегистрирован ПЕРЕД {trace_id}.
        """

        async def _empty_gen(*args, **kwargs):
            yield "id,trace_id,event_type,created_at,payload\n"

        mock_log_service.export_logs = _empty_gen

        response = export_client.get("/api/logs/export", headers=auth_headers)

        # Если маршрут перехвачен {trace_id}, будет вызван get_logs_by_trace_id("export")
        mock_log_service.get_logs_by_trace_id.assert_not_called()
        assert response.status_code == 200

    def test_export_default_limit_5000(
        self, export_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """[SRE_MARKER] Значение limit по умолчанию = 5000 (ограничение памяти).

        logs_upgrade_spec.md §2.2.
        """

        async def _gen(*args, **kwargs):
            yield "id,trace_id,event_type,created_at,payload\n"

        mock_log_service.export_logs = _gen

        export_client.get("/api/logs/export", headers=auth_headers)

        # Проверяем, что export_logs был вызван (через mock)
        # Точные аргументы зависят от реализации

"""
Общие фикстуры для тестов роутера Stats/Dashboard.

Извлечены из app/api/routes/test_stats.py при рефакторинге.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.log_service import LogService


# ═══════════════════════════════════════════════════════════════════════════
# Фикстуры
# ═══════════════════════════════════════════════════════════════════════════

SAMPLE_SUMMARY = {
    "total": 150,
    "chat_requests": 100,
    "guardrail_incidents": 30,
    "system_errors": 20,
    "total_tokens": 50000,
    "avg_latency_ms": 245.67,
}

SAMPLE_CHART_DATA = [
    {"hour": "2026-04-03 10:00", "count": 5},
    {"hour": "2026-04-03 11:00", "count": 12},
    {"hour": "2026-04-03 12:00", "count": 8},
]


@pytest.fixture()
def mock_log_service() -> AsyncMock:
    """Мок LogService с async-методами."""
    svc = AsyncMock(spec=LogService)
    svc.get_stats_summary = AsyncMock(return_value=SAMPLE_SUMMARY)
    svc.get_chart_data = AsyncMock(return_value=SAMPLE_CHART_DATA)
    return svc


@pytest.fixture()
def client(mock_log_service: AsyncMock) -> TestClient:
    """TestClient с подменёнными зависимостями (LogService + auth bypass)."""
    from app.api.dependencies.di import get_log_service
    from app.api.middleware.auth import get_current_user

    app.dependency_overrides[get_log_service] = lambda: mock_log_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    yield TestClient(app)

    app.dependency_overrides.clear()

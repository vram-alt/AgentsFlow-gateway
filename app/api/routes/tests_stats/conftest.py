"""
Shared fixtures for Stats/Dashboard router tests.

Extracted from app/api/routes/test_stats.py during refactoring.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.log_service import LogService


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
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
    """Mock LogService with async methods."""
    svc = AsyncMock(spec=LogService)
    svc.get_stats_summary = AsyncMock(return_value=SAMPLE_SUMMARY)
    svc.get_chart_data = AsyncMock(return_value=SAMPLE_CHART_DATA)
    return svc


@pytest.fixture()
def client(mock_log_service: AsyncMock) -> TestClient:
    """TestClient with substituted dependencies (LogService + auth bypass)."""
    from app.api.dependencies.di import get_log_service
    from app.api.middleware.auth import get_current_user

    app.dependency_overrides[get_log_service] = lambda: mock_log_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    yield TestClient(app)

    app.dependency_overrides.clear()

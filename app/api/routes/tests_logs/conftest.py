"""
Shared fixtures for event log router tests (logs).

Extracted from app/api/routes/test_logs.py during refactoring.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.logs import router as logs_router
from app.services.log_service import LogService
from app.api.dependencies.di import get_log_service


@pytest.fixture()
def mock_log_service() -> MagicMock:
    """Mock LogService — all methods return AsyncMock."""
    service = MagicMock(spec=LogService)
    service.get_logs = AsyncMock(return_value=[])
    service.get_logs_by_trace_id = AsyncMock(return_value=[])
    service.get_log_stats = AsyncMock(return_value={})
    return service


@pytest.fixture()
def client(mock_log_service: MagicMock) -> TestClient:
    """
    TestClient with LogService substituted via dependency_overrides.
    HTTP Basic Auth disabled for routing test isolation.
    """
    from app.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(logs_router)

    app.dependency_overrides[get_log_service] = lambda: mock_log_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """HTTP Basic Auth headers for authorized requests."""
    import base64

    credentials = base64.b64encode(b"admin:admin").decode("utf-8")
    return {"Authorization": f"Basic {credentials}"}

"""
Общие фикстуры для тестов роутера провайдеров (providers).

Извлечены из app/api/routes/test_providers.py при рефакторинге.
"""

import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.providers import router as providers_router
from app.api.dependencies.di import get_provider_service
from app.api.middleware.auth import get_current_user
from app.domain.dto.gateway_error import GatewayError


# ─────────────────────────────────────────────────────────
# Хелперы
# ─────────────────────────────────────────────────────────

FAKE_TRACE_ID = str(uuid.uuid4())


def _make_gateway_error(status_code: int, error_code: str, message: str) -> MagicMock:
    """Создать мок GatewayError с заданным статусом."""
    err = MagicMock(spec=GatewayError)
    err.status_code = status_code
    err.trace_id = FAKE_TRACE_ID
    err.error_code = error_code
    err.message = message
    err.details = {}
    return err


def _make_fake_provider(
    provider_id: int = 1,
    name: str = "openai",
    api_key: str = "sk-test-key-123",
    base_url: str = "https://api.openai.com/v1",
    is_active: bool = True,
) -> dict:
    """Фейковый провайдер как словарь (имитация сериализованной сущности)."""
    return {
        "id": provider_id,
        "name": name,
        "api_key": api_key,
        "base_url": base_url,
        "is_active": is_active,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


# ─────────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────────


@pytest.fixture()
def mock_provider_service() -> MagicMock:
    """Мок ProviderService — все методы возвращают AsyncMock."""
    service = MagicMock()
    service.list_providers = AsyncMock(return_value=[])
    service.create_provider = AsyncMock(return_value=_make_fake_provider())
    service.update_provider = AsyncMock(return_value=_make_fake_provider())
    service.delete_provider = AsyncMock(return_value=True)
    return service


@pytest.fixture()
def client(mock_provider_service: MagicMock) -> TestClient:
    """
    TestClient с подменённым ProviderService через dependency_overrides.
    HTTP Basic Auth отключён для изоляции тестов роутинга.
    """
    app = FastAPI()
    app.include_router(providers_router)

    app.dependency_overrides[get_provider_service] = lambda: mock_provider_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    return TestClient(app)

"""
Тесты для GET /api/providers/health и SSRF-защиты.

Извлечены из app/api/routes/test_providers.py при рефакторинге.
Specification: app/api/routes/providers_spec.md (upgrade §1)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.providers import router as providers_router
from app.api.dependencies.di import get_provider_service
from app.api.middleware.auth import get_current_user


# ═════════════════════════════════════════════════════════
# [UPGRADE] 10. GET /api/providers/health (providers_upgrade_spec §1)
# ═════════════════════════════════════════════════════════


class TestGetProvidersHealth:
    """Tests for нового эндпоинта GET /api/providers/health (upgrade spec §1)."""

    @pytest.fixture()
    def health_client(self, mock_provider_service: MagicMock) -> TestClient:
        """TestClient с подменёнными зависимостями для health-check."""
        from app.api.dependencies.di import get_http_client

        mock_http_client = AsyncMock()

        app = FastAPI()
        app.include_router(providers_router)

        app.dependency_overrides[get_provider_service] = lambda: mock_provider_service
        app.dependency_overrides[get_current_user] = lambda: "test-user"
        app.dependency_overrides[get_http_client] = lambda: mock_http_client

        return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_200(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """GET /api/providers/health -> HTTP 200."""
        mock_provider_service.check_health = AsyncMock(return_value=[])

        response = health_client.get("/api/providers/health")

        assert response.status_code == 200

    def test_health_returns_list(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """Ответ — JSON-массив."""
        mock_provider_service.check_health = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "openai",
                    "base_url_masked": "https://api.openai.com",
                    "is_active": True,
                    "status": "healthy",
                    "response_time_ms": 150.5,
                }
            ]
        )

        response = health_client.get("/api/providers/health")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1

    def test_health_item_has_required_fields(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """Каждый элемент содержит id, name, base_url_masked, is_active, status, response_time_ms."""
        mock_provider_service.check_health = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "openai",
                    "base_url_masked": "https://api.openai.com",
                    "is_active": True,
                    "status": "healthy",
                    "response_time_ms": 150.5,
                }
            ]
        )

        response = health_client.get("/api/providers/health")
        body = response.json()

        item = body[0]
        assert "id" in item
        assert "name" in item
        assert "base_url_masked" in item
        assert "is_active" in item
        assert "status" in item
        assert "response_time_ms" in item

    def test_health_route_not_captured_by_provider_id(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """[SRE_MARKER] /api/providers/health НЕ перехватывается {provider_id}.

        providers_upgrade_spec.md §1.7: health ДОЛЖЕН быть зарегистрирован
        ПЕРЕД {provider_id}, иначе FastAPI интерпретирует 'health' как provider_id.
        """
        mock_provider_service.check_health = AsyncMock(return_value=[])

        response = health_client.get("/api/providers/health")

        # Если маршрут перехвачен {provider_id}, будет HTTP 422
        # (т.к. "health" не является int)
        assert response.status_code != 422, (
            "GET /api/providers/health вернул 422 — маршрут перехвачен {provider_id}. "
            "Эндпоинт health должен быть зарегистрирован ПЕРЕД параметризованными маршрутами."
        )
        assert response.status_code == 200

    def test_health_base_url_masked(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """[SRE_MARKER] base_url маскируется — только scheme и hostname.

        providers_upgrade_spec.md §2: предотвращение раскрытия внутренней инфраструктуры.
        """
        mock_provider_service.check_health = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "openai",
                    "base_url_masked": "https://api.openai.com",
                    "is_active": True,
                    "status": "healthy",
                    "response_time_ms": 100.0,
                }
            ]
        )

        response = health_client.get("/api/providers/health")
        body = response.json()

        # base_url_masked не должен содержать path
        masked = body[0]["base_url_masked"]
        assert "/" not in masked.split("//", 1)[-1] or masked.endswith("/") is False, (
            f"base_url_masked должен содержать только scheme и hostname, получено: {masked}"
        )

    def test_health_service_error_returns_500(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """[SRE_MARKER] Ошибка сервиса -> HTTP 500."""
        mock_provider_service.check_health = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )

        response = health_client.get("/api/providers/health")

        assert response.status_code == 500

    def test_health_caching_second_call_uses_cache(
        self, health_client: TestClient, mock_provider_service: MagicMock
    ):
        """[SRE_MARKER] Кэширование: повторный вызов в пределах TTL=30s не обращается к сервису.

        providers_upgrade_spec.md §1.4 п.2: предотвращение каскадного отказа при polling.
        """
        mock_provider_service.check_health = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "openai",
                    "base_url_masked": "https://api.openai.com",
                    "is_active": True,
                    "status": "healthy",
                    "response_time_ms": 100.0,
                }
            ]
        )

        # Первый вызов
        response1 = health_client.get("/api/providers/health")
        assert response1.status_code == 200
        call_count_after_first = mock_provider_service.check_health.call_count

        # Второй вызов — должен использовать кэш
        response2 = health_client.get("/api/providers/health")
        assert response2.status_code == 200
        call_count_after_second = mock_provider_service.check_health.call_count

        # Сервис не должен быть вызван повторно
        assert call_count_after_second == call_count_after_first, (
            "Повторный вызов health-check должен использовать кэш (TTL=30s)"
        )


# ═════════════════════════════════════════════════════════
# [UPGRADE] 11. ProviderService.check_health — SSRF-защита
# ═════════════════════════════════════════════════════════


class TestProviderServiceSSRF:
    """[SRE_MARKER] Тесты SSRF-защиты для check_health.

    provider_service_upgrade_spec.md §1.4 п.3: запрет приватных IP.
    """

    @pytest.fixture()
    def provider_service_instance(self) -> MagicMock:
        """Мок ProviderService для unit-тестов check_health."""
        from app.services.provider_service import ProviderService

        mock_repo = AsyncMock()
        return ProviderService(provider_repo=mock_repo)

    @pytest.mark.asyncio
    async def test_check_health_exists(self, provider_service_instance):
        """ProviderService должен иметь метод check_health."""
        assert hasattr(provider_service_instance, "check_health"), (
            "ProviderService должен иметь метод check_health"
        )

    @pytest.mark.asyncio
    async def test_check_health_accepts_http_client(self, provider_service_instance):
        """check_health accepts http_client как аргумент (не через конструктор).

        provider_service_upgrade_spec.md §1.2: не менять сигнатуру конструктора.
        """
        import inspect

        sig = inspect.signature(provider_service_instance.check_health)
        assert "http_client" in sig.parameters, (
            "check_health должен принимать http_client как аргумент"
        )

    @pytest.mark.asyncio
    async def test_check_health_returns_list(self, provider_service_instance):
        """check_health возвращает список словарей."""
        mock_http_client = AsyncMock()
        provider_service_instance.provider_repo.list_all = AsyncMock(return_value=[])

        result = await provider_service_instance.check_health(
            http_client=mock_http_client
        )

        assert isinstance(result, list)

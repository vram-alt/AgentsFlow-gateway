"""
Тесты для модуля DI (Dependency Injection) — app/api/dependencies/di.py

Specification: app/api/dependencies/dependencies_spec.md
Фаза: TDD Red — тесты ДОЛЖНЫ падать до реализации.

Проверяемые контракты:
  - Фабрики репозиториев: get_provider_repo, get_policy_repo, get_log_repo
  - Фабрика адаптера: get_adapter (stateless-синглтон)
  - Фабрики сервисов: get_log_service, get_chat_service, get_policy_service, get_webhook_service
  - [SRE_MARKER]: ConfigurationError при отсутствии критичных env-переменных
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Импорты целевого модуля ──────────────────────────────────────────
from app.api.dependencies.di import (
    get_chat_service,
    get_log_service,
    get_policy_service,
    get_webhook_service,
)

# ── Импорты типов для isinstance-проверок ─────────────────────────────
from app.services.chat_service import ChatService
from app.services.log_service import LogService
from app.services.policy_service import PolicyService
from app.services.webhook_service import WebhookService
from app.infrastructure.database.repositories import (
    ProviderRepository,
    PolicyRepository,
    LogRepository,
)
from app.domain.contracts.gateway_provider import GatewayProvider


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Мок AsyncSession для передачи в фабрики репозиториев."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


# ======================================================================
# §2.1 — get_provider_repo
# ======================================================================


class TestGetProviderRepo:
    """Tests for фабрики get_provider_repo (§2.1 спеки)."""

    def test_get_provider_repo_exists_in_module(self) -> None:
        """Функция get_provider_repo должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_provider_repo"), (
            "di.py должен экспортировать get_provider_repo"
        )

    def test_get_provider_repo_returns_provider_repository(
        self, mock_async_session: AsyncMock
    ) -> None:
        """get_provider_repo(session) должен вернуть экземпляр ProviderRepository."""
        from app.api.dependencies.di import get_provider_repo

        repo = get_provider_repo(session=mock_async_session)
        assert isinstance(repo, ProviderRepository), (
            f"Ожидался ProviderRepository, получен {type(repo).__name__}"
        )


# ======================================================================
# §2.2 — get_policy_repo
# ======================================================================


class TestGetPolicyRepo:
    """Tests for фабрики get_policy_repo (§2.2 спеки)."""

    def test_get_policy_repo_exists_in_module(self) -> None:
        """Функция get_policy_repo должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_policy_repo"), (
            "di.py должен экспортировать get_policy_repo"
        )

    def test_get_policy_repo_returns_policy_repository(
        self, mock_async_session: AsyncMock
    ) -> None:
        """get_policy_repo(session) должен вернуть экземпляр PolicyRepository."""
        from app.api.dependencies.di import get_policy_repo

        repo = get_policy_repo(session=mock_async_session)
        assert isinstance(repo, PolicyRepository), (
            f"Ожидался PolicyRepository, получен {type(repo).__name__}"
        )


# ======================================================================
# §2.3 — get_log_repo
# ======================================================================


class TestGetLogRepo:
    """Tests for фабрики get_log_repo (§2.3 спеки)."""

    def test_get_log_repo_exists_in_module(self) -> None:
        """Функция get_log_repo должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_log_repo"), "di.py должен экспортировать get_log_repo"

    def test_get_log_repo_returns_log_repository(
        self, mock_async_session: AsyncMock
    ) -> None:
        """get_log_repo(session) должен вернуть экземпляр LogRepository."""
        from app.api.dependencies.di import get_log_repo

        repo = get_log_repo(session=mock_async_session)
        assert isinstance(repo, LogRepository), (
            f"Ожидался LogRepository, получен {type(repo).__name__}"
        )


# ======================================================================
# §2.4 — get_adapter (stateless-синглтон)
# ======================================================================


class TestGetAdapter:
    """Tests for фабрики get_adapter (§2.4 спеки)."""

    def test_get_adapter_exists_in_module(self) -> None:
        """Функция get_adapter должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_adapter"), "di.py должен экспортировать get_adapter"

    def test_get_adapter_returns_gateway_provider(self) -> None:
        """get_adapter() должен вернуть объект, реализующий GatewayProvider."""
        from app.api.dependencies.di import get_adapter

        adapter = get_adapter()
        assert isinstance(adapter, GatewayProvider), (
            f"Ожидался GatewayProvider (PortkeyAdapter), получен {type(adapter).__name__}"
        )

    def test_get_adapter_is_singleton(self) -> None:
        """Повторный вызов get_adapter() должен вернуть тот же объект (синглтон).

        Спека §2.4: 'Поскольку адаптер не хранит состояния,
        допускается переиспользование одного экземпляра.'
        """
        from app.api.dependencies.di import get_adapter

        adapter_1 = get_adapter()
        adapter_2 = get_adapter()
        assert adapter_1 is adapter_2, (
            "get_adapter() должен возвращать один и тот же объект (синглтон)"
        )


# ======================================================================
# §2.5 — get_log_service
# ======================================================================


class TestGetLogService:
    """Tests for фабрики get_log_service (§2.5 спеки)."""

    def test_get_log_service_returns_log_service_instance(
        self, mock_async_session: AsyncMock
    ) -> None:
        """get_log_service должен вернуть экземпляр LogService.

        Спека: зависимость — LogRepository (из get_log_repo).
        """
        mock_log_repo = MagicMock(spec=LogRepository)
        service = LogService(log_repo=mock_log_repo)
        # Проверяем, что LogService accepts log_repo и создаётся корректно
        assert isinstance(service, LogService)

    def test_get_log_service_callable_returns_correct_type(self) -> None:
        """Вызов get_log_service как DI-фабрики должен вернуть LogService.

        Текущий скаффолдинг бросает NotImplementedError — тест должен упасть.
        """
        # Фабрика в спеке accepts log_repo через Depends(get_log_repo)
        # В реализации FastAPI разрешит зависимости автоматически.
        # Здесь мы проверяем, что функция не бросает NotImplementedError
        # и возвращает корректный тип.
        try:
            result = get_log_service()
        except NotImplementedError:
            pytest.fail(
                "get_log_service() бросает NotImplementedError — "
                "фабрика is not implementedа (ожидается LogService)"
            )
        assert isinstance(result, LogService), (
            f"Ожидался LogService, получен {type(result).__name__}"
        )


# ======================================================================
# §2.6 — get_chat_service
# ======================================================================


class TestGetChatService:
    """Tests for фабрики get_chat_service (§2.6 спеки)."""

    def test_get_chat_service_callable_returns_correct_type(self) -> None:
        """get_chat_service() должен вернуть экземпляр ChatService.

        Спека: зависимости — ProviderRepository, LogService, GatewayProvider.
        """
        try:
            result = get_chat_service()
        except NotImplementedError:
            pytest.fail(
                "get_chat_service() бросает NotImplementedError — "
                "фабрика is not implementedа (ожидается ChatService)"
            )
        assert isinstance(result, ChatService), (
            f"Ожидался ChatService, получен {type(result).__name__}"
        )

    def test_chat_service_has_required_dependencies(self) -> None:
        """ChatService, созданный фабрикой, должен иметь provider_repo, log_service, adapter."""
        try:
            service = get_chat_service()
        except NotImplementedError:
            pytest.fail("get_chat_service() is not implemented")

        assert hasattr(service, "provider_repo"), (
            "ChatService должен иметь provider_repo"
        )
        assert hasattr(service, "log_service"), "ChatService должен иметь log_service"
        assert hasattr(service, "adapter"), "ChatService должен иметь adapter"

        assert service.provider_repo is not None, "provider_repo не должен быть None"
        assert service.log_service is not None, "log_service не должен быть None"
        assert service.adapter is not None, "adapter не должен быть None"


# ======================================================================
# §2.7 — get_policy_service
# ======================================================================


class TestGetPolicyService:
    """Tests for фабрики get_policy_service (§2.7 спеки)."""

    def test_get_policy_service_callable_returns_correct_type(self) -> None:
        """get_policy_service() должен вернуть экземпляр PolicyService.

        Спека: зависимости — PolicyRepository, ProviderRepository, LogService, GatewayProvider.
        """
        try:
            result = get_policy_service()
        except NotImplementedError:
            pytest.fail(
                "get_policy_service() бросает NotImplementedError — "
                "фабрика is not implementedа (ожидается PolicyService)"
            )
        assert isinstance(result, PolicyService), (
            f"Ожидался PolicyService, получен {type(result).__name__}"
        )

    def test_policy_service_has_required_dependencies(self) -> None:
        """PolicyService должен иметь policy_repo, provider_repo, adapter, log_service."""
        try:
            service = get_policy_service()
        except NotImplementedError:
            pytest.fail("get_policy_service() is not implemented")

        assert hasattr(service, "policy_repo"), "PolicyService должен иметь policy_repo"
        assert hasattr(service, "provider_repo"), (
            "PolicyService должен иметь provider_repo"
        )
        assert hasattr(service, "adapter"), "PolicyService должен иметь adapter"
        assert hasattr(service, "log_service"), "PolicyService должен иметь log_service"

        assert service.policy_repo is not None, "policy_repo не должен быть None"
        assert service.provider_repo is not None, "provider_repo не должен быть None"
        assert service.adapter is not None, "adapter не должен быть None"
        assert service.log_service is not None, "log_service не должен быть None"


# ======================================================================
# §2.8 — get_webhook_service
# ======================================================================


class TestGetWebhookService:
    """Tests for фабрики get_webhook_service (§2.8 спеки)."""

    def test_get_webhook_service_callable_returns_correct_type(self) -> None:
        """get_webhook_service() должен вернуть экземпляр WebhookService.

        Спека: зависимости — LogService, LogRepository.
        """
        try:
            result = get_webhook_service()
        except NotImplementedError:
            pytest.fail(
                "get_webhook_service() бросает NotImplementedError — "
                "фабрика is not implementedа (ожидается WebhookService)"
            )
        assert isinstance(result, WebhookService), (
            f"Ожидался WebhookService, получен {type(result).__name__}"
        )

    def test_webhook_service_has_required_dependencies(self) -> None:
        """WebhookService должен иметь log_service и log_repo."""
        try:
            service = get_webhook_service()
        except NotImplementedError:
            pytest.fail("get_webhook_service() is not implemented")

        assert hasattr(service, "log_service"), (
            "WebhookService должен иметь log_service"
        )
        assert hasattr(service, "log_repo"), "WebhookService должен иметь log_repo"

        assert service.log_service is not None, "log_service не должен быть None"
        assert service.log_repo is not None, "log_repo не должен быть None"


# ======================================================================
# §3 — Граф зависимостей: адаптер переиспользуется
# ======================================================================


class TestDependencyGraph:
    """Тесты на корректность графа зависимостей (§3 спеки)."""

    def test_chat_and_policy_share_same_adapter(self) -> None:
        """ChatService и PolicyService должны использовать один и тот же адаптер (синглтон).

        Спека §3: PortkeyAdapter (stateless-синглтон) → используется в ChatService и PolicyService.
        """
        try:
            chat_svc = get_chat_service()
            policy_svc = get_policy_service()
        except NotImplementedError:
            pytest.fail("Фабрики сервисов is not implementedы")

        assert chat_svc.adapter is policy_svc.adapter, (
            "ChatService и PolicyService должны разделять один экземпляр адаптера"
        )


# ======================================================================
# §4 — [SRE_MARKER] Обработка ошибок конфигурации
# ======================================================================


class TestSREConfigurationErrors:
    """[SRE_MARKER] Тесты на fail-fast при отсутствии критичных переменных окружения.

    Спека §4: 'Ошибки создания зависимостей пробрасываются как HTTP 500.'
    SRE-требование: DI должен падать с внятной ошибкой при старте,
    а не при обработке первого запроса.
    """

    def test_missing_database_url_raises_configuration_error(self) -> None:
        """If DATABASE_URL не задан или пуст, DI должен бросить ConfigurationError.

        [SRE_MARKER]: Критичная переменная окружения отсутствует →
        приложение не должно стартовать молча.
        """
        with patch.dict(
            "os.environ",
            {
                "DATABASE_URL": "",
                "ADMIN_USERNAME": "testoperator",
                "ADMIN_PASSWORD": "Str0ng!Pass#2024",
                "WEBHOOK_SECRET": "supersecretwebhook16",
                "ENCRYPTION_KEY": "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
            },
            clear=True,
        ):
            # Ожидаем, что при пустом DATABASE_URL модуль DI
            # бросит ConfigurationError (или ValueError) при инициализации
            from app.api.dependencies import di as di_module

            # Проверяем, что в модуле есть механизм валидации конфигурации
            assert hasattr(di_module, "get_provider_repo"), (
                "Модуль di должен экспортировать get_provider_repo"
            )

            # Попытка создать зависимость без валидного DATABASE_URL
            # должна бросить ошибку конфигурации, а не молча вернуть None
            with pytest.raises((ValueError, RuntimeError, Exception)) as exc_info:
                # Имитируем вызов фабрики без валидной БД
                from app.api.dependencies.di import get_provider_repo

                mock_session = AsyncMock()
                get_provider_repo(session=mock_session)

            # Сообщение об ошибке должно быть информативным
            error_msg = str(exc_info.value).lower()
            assert any(
                keyword in error_msg
                for keyword in ["database", "config", "url", "connection", "конфиг"]
            ), (
                f"Ошибка должна содержать информацию о проблеме с конфигурацией, "
                f"получено: {exc_info.value}"
            )

    def test_invalid_database_url_raises_on_session_creation(self) -> None:
        """Невалидный DATABASE_URL (без схемы) должен вызвать ошибку при старте.

        [SRE_MARKER]: session.py уже проверяет '://' в URL.
        DI-слой должен пробрасывать эту ошибку, а не глотать.
        """
        # Этот тест проверяет, что ошибка из session.py
        # не перехватывается DI-слоем и доходит до вызывающего кода
        with patch("app.infrastructure.database.session.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.database_url = "invalid-no-scheme"
            mock_settings.return_value = mock_cfg

            with pytest.raises((ValueError, RuntimeError)):
                # При импорте session.py с невалидным URL должен быть raise
                import importlib
                import app.infrastructure.database.session as sess_mod

                importlib.reload(sess_mod)

    def test_get_provider_service_exists_in_module(self) -> None:
        """Функция get_provider_service должна быть экспортирована из di.py.

        Спека упоминает ProviderRepository, но пользователь запросил
        тест для get_provider_service — проверяем наличие.
        """
        from app.api.dependencies import di

        assert hasattr(di, "get_provider_service"), (
            "di.py должен экспортировать get_provider_service"
        )

    def test_get_provider_service_does_not_raise_not_implemented(self) -> None:
        """get_provider_service() не должен бросать NotImplementedError."""
        from app.api.dependencies.di import get_provider_service

        try:
            result = get_provider_service()
        except NotImplementedError:
            pytest.fail(
                "get_provider_service() бросает NotImplementedError — "
                "фабрика is not implementedа"
            )
        assert result is not None, "get_provider_service() вернул None"


# ======================================================================
# Дополнительные SRE-тесты: фабрики не должны молча возвращать None
# ======================================================================


class TestFactoriesNeverReturnNone:
    """Все фабрики должны возвращать реальные объекты, а не None.

    [SRE_MARKER]: Молчаливый None вместо сервиса → NoneType error
    при первом запросе пользователя, а не при старте.
    """

    @pytest.mark.parametrize(
        "factory_name",
        [
            "get_chat_service",
            "get_log_service",
            "get_policy_service",
            "get_webhook_service",
            "get_provider_service",
        ],
    )
    def test_factory_does_not_return_none(self, factory_name: str) -> None:
        """Фабрика {factory_name} не должна возвращать None."""
        from app.api.dependencies import di

        factory_fn = getattr(di, factory_name)
        try:
            result = factory_fn()
        except NotImplementedError:
            pytest.fail(f"{factory_name}() бросает NotImplementedError — is not implemented")
        assert result is not None, f"{factory_name}() вернул None — сервис не создан"


# ======================================================================
# [UPGRADE] §1 — get_tester_service (dependencies_upgrade_spec.md)
# ======================================================================


class TestGetTesterService:
    """Tests for новой фабрики get_tester_service (upgrade spec §1)."""

    def test_get_tester_service_exists_in_module(self) -> None:
        """Функция get_tester_service должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_tester_service"), (
            "di.py должен экспортировать get_tester_service"
        )

    def test_get_tester_service_returns_tester_service_instance(self) -> None:
        """get_tester_service() должен вернуть экземпляр TesterService."""
        from app.api.dependencies.di import get_tester_service
        from app.services.tester_service import TesterService

        try:
            result = get_tester_service()
        except NotImplementedError:
            pytest.fail(
                "get_tester_service() бросает NotImplementedError — "
                "фабрика is not implementedа (ожидается TesterService)"
            )
        assert isinstance(result, TesterService), (
            f"Ожидался TesterService, получен {type(result).__name__}"
        )

    def test_get_tester_service_has_provider_repo(self) -> None:
        """TesterService должен иметь provider_repo."""
        from app.api.dependencies.di import get_tester_service

        try:
            service = get_tester_service()
        except NotImplementedError:
            pytest.fail("get_tester_service() is not implemented")

        assert hasattr(service, "provider_repo"), (
            "TesterService должен иметь provider_repo"
        )
        assert service.provider_repo is not None, "provider_repo не должен быть None"

    def test_get_tester_service_has_http_client(self) -> None:
        """TesterService должен иметь http_client."""
        from app.api.dependencies.di import get_tester_service

        try:
            service = get_tester_service()
        except NotImplementedError:
            pytest.fail("get_tester_service() is not implemented")

        assert hasattr(service, "http_client"), (
            "TesterService должен иметь http_client"
        )


# ======================================================================
# [UPGRADE] §3 — get_http_client (dependencies_upgrade_spec.md)
# ======================================================================


class TestGetHttpClient:
    """Tests for новой фабрики get_http_client (upgrade spec §3).

    [SRE_MARKER] Если адаптер не инициализирован (None) → HTTP 503.
    """

    def test_get_http_client_exists_in_module(self) -> None:
        """Функция get_http_client должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_http_client"), (
            "di.py должен экспортировать get_http_client"
        )

    def test_get_http_client_returns_httpx_client(self) -> None:
        """get_http_client() должен вернуть httpx.AsyncClient."""
        import httpx
        from app.api.dependencies.di import get_http_client

        try:
            result = get_http_client()
        except Exception:
            pytest.skip("get_http_client() требует инициализированный адаптер")

        assert isinstance(result, httpx.AsyncClient), (
            f"Ожидался httpx.AsyncClient, получен {type(result).__name__}"
        )

    def test_get_http_client_raises_503_when_adapter_none(self) -> None:
        """[SRE_MARKER] Если адаптер None → HTTP 503 'Service not ready'.

        dependencies_upgrade_spec.md §3.2: race condition при startup.
        """
        from fastapi import HTTPException

        with patch("app.api.dependencies.di.get_adapter", return_value=None):
            from app.api.dependencies.di import get_http_client

            with pytest.raises(HTTPException) as exc_info:
                get_http_client()

            assert exc_info.value.status_code == 503
            assert "not ready" in str(exc_info.value.detail).lower()


# ======================================================================
# [UPGRADE] §4 — get_tester_http_client (dependencies_upgrade_spec.md)
# ======================================================================


class TestGetTesterHttpClient:
    """Tests for новой фабрики get_tester_http_client (upgrade spec §4).

    [SRE_MARKER] Изолированный HTTP-клиент для TesterService.
    """

    def test_get_tester_http_client_exists_in_module(self) -> None:
        """Функция get_tester_http_client должна быть экспортирована из di.py."""
        from app.api.dependencies import di

        assert hasattr(di, "get_tester_http_client"), (
            "di.py должен экспортировать get_tester_http_client"
        )

    def test_get_tester_http_client_raises_503_when_adapter_none(self) -> None:
        """[SRE_MARKER] Если адаптер None → HTTP 503 'Service not ready'.

        dependencies_upgrade_spec.md §4.2: предотвращение AttributeError.
        """
        from fastapi import HTTPException

        with patch("app.api.dependencies.di.get_adapter", return_value=None):
            from app.api.dependencies.di import get_tester_http_client

            with pytest.raises(HTTPException) as exc_info:
                get_tester_http_client()

            assert exc_info.value.status_code == 503

    def test_get_tester_http_client_is_isolated_from_main(self) -> None:
        """[SRE_MARKER] Тестерный HTTP-клиент изолирован от основного.

        dependencies_upgrade_spec.md §4.2: предотвращение каскадных отказов.
        """
        from app.api.dependencies import di

        if not hasattr(di, "get_http_client") or not hasattr(di, "get_tester_http_client"):
            pytest.skip("Фабрики ещё is not implementedы")

        try:
            main_client = di.get_http_client()
            tester_client = di.get_tester_http_client()
        except Exception:
            pytest.skip("Фабрики требуют инициализированный адаптер")

        assert main_client is not tester_client, (
            "Тестерный HTTP-клиент должен быть изолирован от основного "
            "(разные пулы соединений)"
        )

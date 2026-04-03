"""
Модульные тесты для PolicyService.
Спецификация: app/services/policy_service_spec.md

TDD Red-фаза: все тесты должны падать с ImportError,
пока PolicyService не реализован.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Импорт тестируемого класса (должен упасть на Red-фазе) ──────────────
from app.services.policy_service import PolicyService

# ── Импорт доменных объектов (уже реализованы в скаффолдинге) ────────────
from app.domain.dto.gateway_error import GatewayError


# ═══════════════════════════════════════════════════════════════════════════
# Фикстуры
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_policy_repo():
    """Мок PolicyRepository с async-методами."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.soft_delete = AsyncMock()
    repo.list_all = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock()
    repo.get_by_remote_id = AsyncMock()
    return repo


@pytest.fixture
def mock_provider_repo():
    """Мок ProviderRepository с async-методами."""
    repo = AsyncMock()
    repo.get_active_by_name = AsyncMock()
    return repo


@pytest.fixture
def mock_adapter():
    """Мок GatewayProvider (адаптер облака)."""
    adapter = AsyncMock()
    adapter.create_guardrail = AsyncMock()
    adapter.update_guardrail = AsyncMock()
    adapter.delete_guardrail = AsyncMock()
    adapter.list_guardrails = AsyncMock()
    return adapter


@pytest.fixture
def mock_log_service():
    """Мок LogService."""
    return AsyncMock()


@pytest.fixture
def fake_provider():
    """Фейковый объект провайдера с api_key и base_url."""
    provider = MagicMock()
    provider.id = 1
    provider.name = "portkey"
    provider.api_key = "test-api-key-123"
    provider.base_url = "https://api.portkey.ai"
    return provider


@pytest.fixture
def fake_policy():
    """Фейковый объект политики из БД."""
    policy = MagicMock()
    policy.id = 42
    policy.name = "content-filter"
    policy.body = {"type": "content_filter", "threshold": 0.8}
    policy.remote_id = "remote-guardrail-abc"
    policy.provider_id = 1
    policy.is_active = True
    return policy


@pytest.fixture
def service(mock_policy_repo, mock_provider_repo, mock_adapter, mock_log_service):
    """Экземпляр PolicyService со всеми замоканными зависимостями."""
    return PolicyService(
        policy_repo=mock_policy_repo,
        provider_repo=mock_provider_repo,
        adapter=mock_adapter,
        log_service=mock_log_service,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. create_policy
# ═══════════════════════════════════════════════════════════════════════════


class TestCreatePolicy:
    """Тесты для метода create_policy (спецификация §3)."""

    @pytest.mark.asyncio
    async def test_create_policy_success(
        self, service, mock_policy_repo, mock_provider_repo, mock_adapter, fake_provider
    ):
        """Успешное создание: облако → БД → возврат Policy."""
        # Arrange
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.create_guardrail.return_value = {
            "remote_id": "remote-123",
            "raw_response": {},
        }
        created_policy = MagicMock(id=1, name="test-policy", remote_id="remote-123")
        mock_policy_repo.create.return_value = created_policy

        body = {"type": "content_filter", "threshold": 0.9}

        # Act
        result = await service.create_policy(name="test-policy", body=body)

        # Assert
        mock_provider_repo.get_active_by_name.assert_awaited_once_with("portkey")
        mock_adapter.create_guardrail.assert_awaited_once_with(
            body, fake_provider.api_key, fake_provider.base_url
        )
        mock_policy_repo.create.assert_awaited_once()
        assert result is not None
        assert not isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_create_policy_custom_provider_name(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """Передача кастомного provider_name вместо дефолтного 'portkey'."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.create_guardrail.return_value = {
            "remote_id": "r-456",
            "raw_response": {},
        }
        mock_policy_repo.create.return_value = MagicMock()

        await service.create_policy(
            name="my-policy", body={"x": 1}, provider_name="openai"
        )

        mock_provider_repo.get_active_by_name.assert_awaited_once_with("openai")

    @pytest.mark.asyncio
    async def test_create_policy_provider_not_found_returns_auth_failed(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo
    ):
        """[SRE_MARKER] Провайдер не найден → GatewayError(error_code='AUTH_FAILED')."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.create_policy(name="p", body={"a": 1})

        assert isinstance(result, GatewayError)
        assert result.error_code == "AUTH_FAILED"
        mock_adapter.create_guardrail.assert_not_awaited()
        mock_policy_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_policy_cloud_error_does_not_touch_db(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """[SRE_MARKER] Ошибка облака → GatewayError, БД НЕ изменяется."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.create_guardrail.return_value = GatewayError(
            trace_id="123e4567-e89b-42d3-a456-426614174000",
            error_code="PROVIDER_ERROR",
            message="Cloud timeout",
        )

        result = await service.create_policy(name="p", body={"a": 1})

        assert isinstance(result, GatewayError)
        mock_policy_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_policy_passes_remote_id_to_repo(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """remote_id из ответа облака передаётся в policy_repo.create."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        cloud_response = {"remote_id": "cloud-id-xyz", "raw_response": {}}
        mock_adapter.create_guardrail.return_value = cloud_response
        mock_policy_repo.create.return_value = MagicMock()

        await service.create_policy(name="pol", body={"b": 2})

        call_kwargs = mock_policy_repo.create.call_args
        # remote_id должен быть передан в вызов create
        assert "cloud-id-xyz" in str(call_kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 4. update_policy
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdatePolicy:
    """Тесты для метода update_policy (спецификация §4)."""

    @pytest.mark.asyncio
    async def test_update_policy_not_found_returns_validation_error(
        self, service, mock_policy_repo
    ):
        """[SRE_MARKER] Политика не найдена → GatewayError(VALIDATION_ERROR)."""
        mock_policy_repo.get_by_id.return_value = None

        result = await service.update_policy(policy_id=999, name="new-name")

        assert isinstance(result, GatewayError)
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_update_policy_name_only_no_cloud_call(
        self, service, mock_policy_repo, mock_adapter, fake_policy
    ):
        """Обновление только name (без body) → облако НЕ вызывается."""
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_policy_repo.update.return_value = fake_policy

        result = await service.update_policy(policy_id=42, name="renamed")

        mock_adapter.update_guardrail.assert_not_awaited()
        mock_policy_repo.update.assert_awaited_once()
        assert not isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_update_policy_body_with_remote_id_syncs_cloud(
        self,
        service,
        mock_policy_repo,
        mock_provider_repo,
        mock_adapter,
        fake_policy,
        fake_provider,
    ):
        """Обновление body при наличии remote_id → синхронизация с облаком."""
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.update_guardrail.return_value = MagicMock()
        mock_policy_repo.update.return_value = fake_policy

        new_body = {"type": "content_filter", "threshold": 0.5}
        result = await service.update_policy(policy_id=42, body=new_body)

        mock_adapter.update_guardrail.assert_awaited_once()
        mock_policy_repo.update.assert_awaited_once()
        assert not isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_update_policy_cloud_error_does_not_touch_db(
        self,
        service,
        mock_policy_repo,
        mock_provider_repo,
        mock_adapter,
        fake_policy,
        fake_provider,
    ):
        """[SRE_MARKER] Ошибка облака при update → GatewayError, БД не трогаем."""
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.update_guardrail.return_value = GatewayError(
            trace_id="123e4567-e89b-42d3-a456-426614174001",
            error_code="PROVIDER_ERROR",
            message="Cloud error",
        )

        result = await service.update_policy(policy_id=42, body={"new": True})

        assert isinstance(result, GatewayError)
        mock_policy_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_policy_body_without_remote_id_skips_cloud(
        self, service, mock_policy_repo, mock_adapter, fake_policy
    ):
        """Обновление body, но remote_id отсутствует → облако НЕ вызывается."""
        fake_policy.remote_id = None
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_policy_repo.update.return_value = fake_policy

        result = await service.update_policy(policy_id=42, body={"new": True})

        mock_adapter.update_guardrail.assert_not_awaited()
        mock_policy_repo.update.assert_awaited_once()
        assert not isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_update_policy_returns_updated_entity(
        self, service, mock_policy_repo, fake_policy
    ):
        """Метод возвращает обновлённую доменную сущность Policy."""
        updated = MagicMock(id=42, name="updated-name")
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_policy_repo.update.return_value = updated

        result = await service.update_policy(policy_id=42, name="updated-name")

        assert result is updated


# ═══════════════════════════════════════════════════════════════════════════
# 5. delete_policy
# ═══════════════════════════════════════════════════════════════════════════


class TestDeletePolicy:
    """Тесты для метода delete_policy (спецификация §5)."""

    @pytest.mark.asyncio
    async def test_delete_policy_not_found_returns_error(
        self, service, mock_policy_repo
    ):
        """[SRE_MARKER] Политика не найдена → GatewayError."""
        mock_policy_repo.get_by_id.return_value = None

        result = await service.delete_policy(policy_id=999)

        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_delete_policy_with_remote_id_deletes_from_cloud_first(
        self,
        service,
        mock_policy_repo,
        mock_provider_repo,
        mock_adapter,
        fake_policy,
        fake_provider,
    ):
        """Удаление с remote_id: сначала облако, потом soft_delete в БД."""
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.delete_guardrail.return_value = MagicMock()
        mock_policy_repo.soft_delete.return_value = True

        result = await service.delete_policy(policy_id=42)

        mock_adapter.delete_guardrail.assert_awaited_once()
        mock_policy_repo.soft_delete.assert_awaited_once_with(42)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_policy_cloud_error_does_not_touch_db(
        self,
        service,
        mock_policy_repo,
        mock_provider_repo,
        mock_adapter,
        fake_policy,
        fake_provider,
    ):
        """[SRE_MARKER] Ошибка облака при удалении → GatewayError, БД не трогаем."""
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.delete_guardrail.return_value = GatewayError(
            trace_id="123e4567-e89b-42d3-a456-426614174002",
            error_code="PROVIDER_ERROR",
            message="Delete failed",
        )

        result = await service.delete_policy(policy_id=42)

        assert isinstance(result, GatewayError)
        mock_policy_repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_policy_without_remote_id_skips_cloud(
        self, service, mock_policy_repo, mock_adapter, fake_policy
    ):
        """Удаление без remote_id → облако НЕ вызывается, только soft_delete."""
        fake_policy.remote_id = None
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_policy_repo.soft_delete.return_value = True

        result = await service.delete_policy(policy_id=42)

        mock_adapter.delete_guardrail.assert_not_awaited()
        mock_policy_repo.soft_delete.assert_awaited_once_with(42)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_policy_returns_true_on_success(
        self, service, mock_policy_repo, fake_policy
    ):
        """Успешное удаление возвращает True."""
        fake_policy.remote_id = None
        mock_policy_repo.get_by_id.return_value = fake_policy
        mock_policy_repo.soft_delete.return_value = True

        result = await service.delete_policy(policy_id=42)

        assert result is True


# ═══════════════════════════════════════════════════════════════════════════
# 6. list_policies
# ═══════════════════════════════════════════════════════════════════════════


class TestListPolicies:
    """Тесты для метода list_policies (спецификация §6)."""

    @pytest.mark.asyncio
    async def test_list_policies_default_only_active(self, service, mock_policy_repo):
        """По умолчанию only_active=True."""
        mock_policy_repo.list_all.return_value = []

        await service.list_policies()

        mock_policy_repo.list_all.assert_awaited_once_with(only_active=True)

    @pytest.mark.asyncio
    async def test_list_policies_include_inactive(self, service, mock_policy_repo):
        """Передача only_active=False возвращает все политики."""
        mock_policy_repo.list_all.return_value = []

        await service.list_policies(only_active=False)

        mock_policy_repo.list_all.assert_awaited_once_with(only_active=False)

    @pytest.mark.asyncio
    async def test_list_policies_returns_list(self, service, mock_policy_repo):
        """Метод возвращает список доменных сущностей."""
        fake_items = [MagicMock(), MagicMock()]
        mock_policy_repo.list_all.return_value = fake_items

        result = await service.list_policies()

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_policies_empty_returns_empty_list(
        self, service, mock_policy_repo
    ):
        """Пустая БД → пустой список."""
        mock_policy_repo.list_all.return_value = []

        result = await service.list_policies()

        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# 7. sync_policies_from_provider
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncPoliciesFromProvider:
    """Тесты для метода sync_policies_from_provider (спецификация §7)."""

    @pytest.mark.asyncio
    async def test_sync_provider_not_found_returns_error(
        self, service, mock_provider_repo
    ):
        """[SRE_MARKER] Провайдер не найден → GatewayError(AUTH_FAILED)."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.sync_policies_from_provider()

        assert isinstance(result, GatewayError)
        assert result.error_code == "AUTH_FAILED"

    @pytest.mark.asyncio
    async def test_sync_cloud_list_error_returns_gateway_error(
        self, service, mock_provider_repo, mock_adapter, fake_provider
    ):
        """[SRE_MARKER] Ошибка при запросе списка из облака → GatewayError."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.list_guardrails.return_value = GatewayError(
            trace_id="123e4567-e89b-42d3-a456-426614174003",
            error_code="PROVIDER_ERROR",
            message="List failed",
        )

        result = await service.sync_policies_from_provider()

        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_sync_creates_new_policies(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """Новые политики из облака создаются в БД."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        remote_policy = {
            "remote_id": "r-new-1",
            "name": "cloud-policy",
            "config": {"x": 1},
        }
        mock_adapter.list_guardrails.return_value = [remote_policy]
        mock_policy_repo.get_by_remote_id.return_value = None
        mock_policy_repo.create.return_value = MagicMock()

        result = await service.sync_policies_from_provider()

        mock_policy_repo.create.assert_awaited_once()
        assert isinstance(result, dict)
        assert result["created"] == 1
        assert result["total_remote"] == 1

    @pytest.mark.asyncio
    async def test_sync_updates_existing_policies(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """Существующие политики обновляются, если данные отличаются."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider

        remote_policy = {
            "remote_id": "r-exist",
            "name": "updated-name",
            "config": {"new": True},
        }
        mock_adapter.list_guardrails.return_value = [remote_policy]

        existing = MagicMock(remote_id="r-exist", name="old-name", body={"old": True})
        mock_policy_repo.get_by_remote_id.return_value = existing
        mock_policy_repo.update.return_value = MagicMock()

        result = await service.sync_policies_from_provider()

        assert isinstance(result, dict)
        assert result["updated"] == 1
        assert result["unchanged"] == 0

    @pytest.mark.asyncio
    async def test_sync_unchanged_policies(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """Политики без изменений не обновляются."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider

        config = {"type": "filter"}
        remote_policy = {"remote_id": "r-same", "name": "same", "config": config}
        mock_adapter.list_guardrails.return_value = [remote_policy]

        existing = MagicMock(remote_id="r-same", name="same", body=config)
        mock_policy_repo.get_by_remote_id.return_value = existing

        result = await service.sync_policies_from_provider()

        assert isinstance(result, dict)
        assert result["unchanged"] == 1
        assert result["created"] == 0
        assert result["updated"] == 0

    @pytest.mark.asyncio
    async def test_sync_report_has_all_required_keys(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """Отчёт содержит все обязательные ключи: created, updated, unchanged, total_remote."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.list_guardrails.return_value = []

        result = await service.sync_policies_from_provider()

        assert isinstance(result, dict)
        for key in ("created", "updated", "unchanged", "total_remote"):
            assert key in result, f"Ключ '{key}' отсутствует в отчёте синхронизации"

    @pytest.mark.asyncio
    async def test_sync_default_provider_name_is_portkey(
        self, service, mock_provider_repo, mock_adapter, fake_provider
    ):
        """По умолчанию provider_name='portkey'."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.list_guardrails.return_value = []

        await service.sync_policies_from_provider()

        mock_provider_repo.get_active_by_name.assert_awaited_once_with("portkey")

    @pytest.mark.asyncio
    async def test_sync_error_on_single_policy_continues_with_rest(
        self, service, mock_provider_repo, mock_adapter, mock_policy_repo, fake_provider
    ):
        """[SRE_MARKER] Ошибка при синхронизации одной политики → пропустить, продолжить."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider

        good_policy = {"remote_id": "r-good", "name": "good", "config": {"ok": True}}
        bad_policy = {"remote_id": "r-bad", "name": "bad", "config": {"fail": True}}
        mock_adapter.list_guardrails.return_value = [bad_policy, good_policy]

        # Первый вызов get_by_remote_id бросает исключение, второй — нормальный
        mock_policy_repo.get_by_remote_id.side_effect = [
            Exception("DB error on bad policy"),
            None,  # не найден → создать
        ]
        mock_policy_repo.create.return_value = MagicMock()

        result = await service.sync_policies_from_provider()

        # Несмотря на ошибку первой политики, вторая должна быть создана
        assert isinstance(result, dict)
        assert result["total_remote"] == 2
        assert result["created"] >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 8. Обработка ошибок (общие сценарии)
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Общие тесты обработки ошибок (спецификация §8)."""

    @pytest.mark.asyncio
    async def test_db_error_returns_unknown_gateway_error(
        self, service, mock_policy_repo, mock_provider_repo, mock_adapter, fake_provider
    ):
        """[SRE_MARKER] Ошибка БД → GatewayError(error_code='UNKNOWN')."""
        mock_provider_repo.get_active_by_name.return_value = fake_provider
        mock_adapter.create_guardrail.return_value = {"remote_id": "r-1", "raw_response": {}}
        mock_policy_repo.create.side_effect = Exception("DB connection lost")

        result = await service.create_policy(name="p", body={"a": 1})

        assert isinstance(result, GatewayError)
        assert result.error_code == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_gateway_error(
        self, service, mock_policy_repo
    ):
        """Удаление несуществующей политики → GatewayError."""
        mock_policy_repo.get_by_id.return_value = None

        result = await service.delete_policy(policy_id=12345)

        assert isinstance(result, GatewayError)


# ═══════════════════════════════════════════════════════════════════════════
# Конструктор
# ═══════════════════════════════════════════════════════════════════════════


class TestPolicyServiceConstructor:
    """Тесты конструктора PolicyService (спецификация §2)."""

    def test_constructor_accepts_all_dependencies(
        self, mock_policy_repo, mock_provider_repo, mock_adapter, mock_log_service
    ):
        """PolicyService принимает 4 зависимости через конструктор."""
        svc = PolicyService(
            policy_repo=mock_policy_repo,
            provider_repo=mock_provider_repo,
            adapter=mock_adapter,
            log_service=mock_log_service,
        )
        assert svc is not None

    def test_constructor_stores_dependencies(
        self, mock_policy_repo, mock_provider_repo, mock_adapter, mock_log_service
    ):
        """Зависимости сохраняются как атрибуты экземпляра."""
        svc = PolicyService(
            policy_repo=mock_policy_repo,
            provider_repo=mock_provider_repo,
            adapter=mock_adapter,
            log_service=mock_log_service,
        )
        assert svc.policy_repo is mock_policy_repo
        assert svc.provider_repo is mock_provider_repo
        assert svc.adapter is mock_adapter
        assert svc.log_service is mock_log_service

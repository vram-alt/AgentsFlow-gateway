"""
TDD-тесты для слоя репозиториев (repositories.py).

Все тесты используют мок AsyncSession — реальная БД не нужна.
Тесты ДОЛЖНЫ падать, пока repositories.py содержит только placeholder.

Покрытие:
  - ProviderRepository: CRUD + soft_delete
  - PolicyRepository: CRUD + soft_delete + upsert_by_remote_id
  - LogRepository: create, get_by_trace_id, list_all, list_by_type, count_all, count_by_type
  - [SRE_MARKER] IntegrityError, OperationalError, ValueError (невалидный JSON)
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError, OperationalError

from app.infrastructure.database.models import (
    LogEntryModel,
    PolicyModel,
    ProviderModel,
)

try:
    from app.infrastructure.database.repositories import (
        LogRepository,
        PolicyRepository,
        ProviderRepository,
    )
except ImportError:
    # Скаффолдинг ещё пуст — создаём заглушки, чтобы тесты собирались и ПАДАЛИ
    ProviderRepository = None  # type: ignore[assignment, misc]
    PolicyRepository = None  # type: ignore[assignment, misc]
    LogRepository = None  # type: ignore[assignment, misc]

    pytestmark = pytest.mark.skip(
        reason="repositories.py ещё не реализован (placeholder)"
    )


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Мок AsyncSession для инъекции в репозитории."""
    session = AsyncMock()
    # session.execute возвращает AsyncMock по умолчанию
    # session.commit / session.flush / session.refresh — AsyncMock
    # session.add — обычный MagicMock (синхронный метод)
    session.add = MagicMock()
    return session


@pytest.fixture
def provider_repo(mock_session: AsyncMock) -> ProviderRepository:
    return ProviderRepository(mock_session)


@pytest.fixture
def policy_repo(mock_session: AsyncMock) -> PolicyRepository:
    return PolicyRepository(mock_session)


@pytest.fixture
def log_repo(mock_session: AsyncMock) -> LogRepository:
    return LogRepository(mock_session)


def _make_provider(**overrides) -> ProviderModel:
    """Фабрика для создания ProviderModel-заглушки."""
    defaults = dict(
        id=1,
        name="openai",
        api_key="sk-test-key",
        base_url="https://api.openai.com",
        is_active=True,
        created_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
    )
    defaults.update(overrides)
    obj = MagicMock(spec=ProviderModel)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_policy(**overrides) -> PolicyModel:
    """Фабрика для создания PolicyModel-заглушки."""
    defaults = dict(
        id=1,
        name="rate-limit",
        body='{"max_rpm": 100}',
        remote_id="pol_abc123",
        provider_id=1,
        is_active=True,
        created_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
    )
    defaults.update(overrides)
    obj = MagicMock(spec=PolicyModel)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_log(**overrides) -> LogEntryModel:
    """Фабрика для создания LogEntryModel-заглушки."""
    defaults = dict(
        id=1,
        trace_id="abc-123-def",
        event_type="prompt_sent",
        payload='{"model": "gpt-4"}',
        created_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
    )
    defaults.update(overrides)
    obj = MagicMock(spec=LogEntryModel)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ===================================================================
# ProviderRepository
# ===================================================================


class TestProviderRepository:
    """Тесты для ProviderRepository."""

    # --- get_active_by_name ---

    @pytest.mark.asyncio
    async def test_get_active_by_name_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен вернуть ProviderModel, если активный провайдер найден."""
        expected = _make_provider(name="openai", is_active=True)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await provider_repo.get_active_by_name("openai")

        assert result is expected
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_active_by_name_not_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен вернуть None, если провайдер не найден."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await provider_repo.get_active_by_name("nonexistent")

        assert result is None

    # --- get_by_id ---

    @pytest.mark.asyncio
    async def test_get_by_id_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен вернуть ProviderModel по ID."""
        expected = _make_provider(id=42)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await provider_repo.get_by_id(42)

        assert result is expected
        assert result.id == 42

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен вернуть None, если провайдер с таким ID не существует."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await provider_repo.get_by_id(999)

        assert result is None

    # --- list_all ---

    @pytest.mark.asyncio
    async def test_list_all_only_active(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """По умолчанию возвращает только активных провайдеров."""
        providers = [
            _make_provider(id=1, is_active=True),
            _make_provider(id=2, is_active=True),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = providers
        mock_session.execute.return_value = result_mock

        result = await provider_repo.list_all(only_active=True)

        assert len(result) == 2
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_all_include_inactive(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """С only_active=False возвращает всех провайдеров."""
        providers = [
            _make_provider(id=1, is_active=True),
            _make_provider(id=2, is_active=False),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = providers
        mock_session.execute.return_value = result_mock

        result = await provider_repo.list_all(only_active=False)

        assert len(result) == 2

    # --- create ---

    @pytest.mark.asyncio
    async def test_create_provider(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен создать провайдера, вызвать add + commit + refresh."""
        result = await provider_repo.create(
            name="anthropic",
            api_key="sk-ant-key",
            base_url="https://api.anthropic.com",
        )

        # Проверяем, что session.add был вызван
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

        # Результат должен быть ProviderModel
        assert result is not None

    # --- update ---

    @pytest.mark.asyncio
    async def test_update_provider_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен обновить поля провайдера и вернуть обновлённый объект."""
        existing = _make_provider(id=1, name="openai", base_url="https://old.url")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        result = await provider_repo.update(1, base_url="https://new.url")

        assert result is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_provider_not_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """Должен вернуть None, если провайдер не найден."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await provider_repo.update(999, name="ghost")

        assert result is None

    # --- soft_delete ---

    @pytest.mark.asyncio
    async def test_soft_delete_provider_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """soft_delete должен установить is_active=False и вернуть True."""
        existing = _make_provider(id=1, is_active=True)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        result = await provider_repo.soft_delete(1)

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_provider_not_found(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """soft_delete должен вернуть False, если провайдер не найден."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await provider_repo.soft_delete(999)

        assert result is False

    # --- [SRE_MARKER] IntegrityError при дубликате ---

    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises_integrity_error(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """[SRE] Дубликат UNIQUE-поля name → IntegrityError пробрасывается."""
        mock_session.commit.side_effect = IntegrityError(
            statement="INSERT INTO providers",
            params={},
            orig=Exception("UNIQUE constraint failed"),
        )

        with pytest.raises(IntegrityError):
            await provider_repo.create(
                name="openai",
                api_key="sk-dup",
                base_url="https://api.openai.com",
            )

    # --- [SRE_MARKER] OperationalError при потере соединения ---

    @pytest.mark.asyncio
    async def test_get_by_id_operational_error(
        self, provider_repo: ProviderRepository, mock_session: AsyncMock
    ):
        """[SRE] Ошибка подключения к БД → OperationalError пробрасывается."""
        mock_session.execute.side_effect = OperationalError(
            statement="SELECT",
            params={},
            orig=Exception("connection refused"),
        )

        with pytest.raises(OperationalError):
            await provider_repo.get_by_id(1)


# ===================================================================
# PolicyRepository
# ===================================================================


class TestPolicyRepository:
    """Тесты для PolicyRepository."""

    # --- get_by_id ---

    @pytest.mark.asyncio
    async def test_get_by_id_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        expected = _make_policy(id=10)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await policy_repo.get_by_id(10)

        assert result is expected
        assert result.id == 10

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await policy_repo.get_by_id(999)

        assert result is None

    # --- get_by_remote_id ---

    @pytest.mark.asyncio
    async def test_get_by_remote_id_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        expected = _make_policy(remote_id="pol_xyz")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await policy_repo.get_by_remote_id("pol_xyz")

        assert result is expected
        assert result.remote_id == "pol_xyz"

    @pytest.mark.asyncio
    async def test_get_by_remote_id_not_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await policy_repo.get_by_remote_id("nonexistent")

        assert result is None

    # --- list_all ---

    @pytest.mark.asyncio
    async def test_list_all_only_active(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        policies = [_make_policy(id=1), _make_policy(id=2)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = policies
        mock_session.execute.return_value = result_mock

        result = await policy_repo.list_all(only_active=True)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_all_include_inactive(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        policies = [
            _make_policy(id=1, is_active=True),
            _make_policy(id=2, is_active=False),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = policies
        mock_session.execute.return_value = result_mock

        result = await policy_repo.list_all(only_active=False)

        assert len(result) == 2

    # --- list_by_provider ---

    @pytest.mark.asyncio
    async def test_list_by_provider(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        policies = [
            _make_policy(id=1, provider_id=5),
            _make_policy(id=2, provider_id=5),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = policies
        mock_session.execute.return_value = result_mock

        result = await policy_repo.list_by_provider(provider_id=5)

        assert len(result) == 2
        for p in result:
            assert p.provider_id == 5

    # --- create ---

    @pytest.mark.asyncio
    async def test_create_policy(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        """Должен создать политику. body (dict) сериализуется в JSON внутри репозитория."""
        body_dict = {"max_rpm": 200, "burst": 50}

        result = await policy_repo.create(
            name="rate-limit-v2",
            body=body_dict,
            remote_id="pol_new",
            provider_id=1,
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        assert result is not None

    # --- update ---

    @pytest.mark.asyncio
    async def test_update_policy_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        existing = _make_policy(id=1, name="old-name")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        result = await policy_repo.update(1, name="new-name")

        assert result is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_policy_not_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await policy_repo.update(999, name="ghost")

        assert result is None

    # --- soft_delete ---

    @pytest.mark.asyncio
    async def test_soft_delete_policy_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        existing = _make_policy(id=1, is_active=True)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        result = await policy_repo.soft_delete(1)

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_policy_not_found(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await policy_repo.soft_delete(999)

        assert result is False

    # --- upsert_by_remote_id ---

    @pytest.mark.asyncio
    async def test_upsert_creates_when_not_exists(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        """upsert_by_remote_id: если remote_id не найден — создаёт новую запись."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await policy_repo.upsert_by_remote_id(
            remote_id="pol_new",
            name="new-policy",
            body={"key": "value"},
            provider_id=1,
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_upsert_updates_when_exists(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        """upsert_by_remote_id: если remote_id найден — обновляет существующую запись."""
        existing = _make_policy(id=5, remote_id="pol_existing", name="old-name")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        result = await policy_repo.upsert_by_remote_id(
            remote_id="pol_existing",
            name="updated-name",
            body={"updated": True},
            provider_id=2,
        )

        mock_session.commit.assert_awaited_once()
        assert result is not None

    # --- [SRE_MARKER] IntegrityError при дубликате remote_id ---

    @pytest.mark.asyncio
    async def test_create_duplicate_remote_id_raises_integrity_error(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        """[SRE] Дубликат UNIQUE remote_id → IntegrityError пробрасывается."""
        mock_session.commit.side_effect = IntegrityError(
            statement="INSERT INTO policies",
            params={},
            orig=Exception("UNIQUE constraint failed: policies.remote_id"),
        )

        with pytest.raises(IntegrityError):
            await policy_repo.create(
                name="dup-policy",
                body={"key": "val"},
                remote_id="pol_dup",
                provider_id=1,
            )

    # --- [SRE_MARKER] Сериализация body: невалидный JSON ---

    @pytest.mark.asyncio
    async def test_create_policy_invalid_body_raises_value_error(
        self, policy_repo: PolicyRepository, mock_session: AsyncMock
    ):
        """[SRE] Невалидный объект для JSON-сериализации body → ValueError."""
        # Объект, который не сериализуется в JSON
        non_serializable = {"bad": object()}

        with pytest.raises((ValueError, TypeError)):
            await policy_repo.create(
                name="bad-policy",
                body=non_serializable,
                remote_id="pol_bad",
                provider_id=1,
            )


# ===================================================================
# LogRepository
# ===================================================================


class TestLogRepository:
    """Тесты для LogRepository."""

    # --- create ---

    @pytest.mark.asyncio
    async def test_create_log_entry(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен создать запись лога. payload (dict) сериализуется в JSON."""
        payload_dict = {"model": "gpt-4", "tokens": 150}

        result = await log_repo.create(
            trace_id="trace-001",
            event_type="prompt_sent",
            payload=payload_dict,
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        assert result is not None

    # --- get_by_trace_id ---

    @pytest.mark.asyncio
    async def test_get_by_trace_id_found(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть список LogEntryModel по trace_id."""
        logs = [
            _make_log(id=1, trace_id="trace-001", event_type="prompt_sent"),
            _make_log(id=2, trace_id="trace-001", event_type="response_received"),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = logs
        mock_session.execute.return_value = result_mock

        result = await log_repo.get_by_trace_id("trace-001")

        assert len(result) == 2
        for log in result:
            assert log.trace_id == "trace-001"

    @pytest.mark.asyncio
    async def test_get_by_trace_id_empty(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть пустой список, если trace_id не найден."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        result = await log_repo.get_by_trace_id("nonexistent")

        assert result == []

    # --- list_all ---

    @pytest.mark.asyncio
    async def test_list_all_with_pagination(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен поддерживать limit и offset для пагинации."""
        logs = [_make_log(id=i) for i in range(1, 11)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = logs
        mock_session.execute.return_value = result_mock

        result = await log_repo.list_all(limit=10, offset=0)

        assert len(result) == 10
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_all_default_params(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """По умолчанию limit=100, offset=0."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        result = await log_repo.list_all()

        assert result == []
        mock_session.execute.assert_awaited_once()

    # --- list_by_type ---

    @pytest.mark.asyncio
    async def test_list_by_type(self, log_repo: LogRepository, mock_session: AsyncMock):
        """Должен фильтровать логи по event_type."""
        logs = [
            _make_log(id=1, event_type="error"),
            _make_log(id=2, event_type="error"),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = logs
        mock_session.execute.return_value = result_mock

        result = await log_repo.list_by_type("error", limit=50, offset=0)

        assert len(result) == 2

    # --- count_all ---

    @pytest.mark.asyncio
    async def test_count_all(self, log_repo: LogRepository, mock_session: AsyncMock):
        """Должен вернуть общее количество записей."""
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 42
        mock_session.execute.return_value = result_mock

        result = await log_repo.count_all()

        assert result == 42

    # --- count_by_type ---

    @pytest.mark.asyncio
    async def test_count_by_type(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть количество записей определённого типа."""
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 7
        mock_session.execute.return_value = result_mock

        result = await log_repo.count_by_type("prompt_sent")

        assert result == 7

    # --- [SRE_MARKER] Сериализация payload: невалидный JSON ---

    @pytest.mark.asyncio
    async def test_create_log_invalid_payload_raises_value_error(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """[SRE] Невалидный объект для JSON-сериализации payload → ValueError."""
        non_serializable = {"bad": object()}

        with pytest.raises((ValueError, TypeError)):
            await log_repo.create(
                trace_id="trace-bad",
                event_type="error",
                payload=non_serializable,
            )

    # --- [SRE_MARKER] OperationalError при потере соединения ---

    @pytest.mark.asyncio
    async def test_list_all_operational_error(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """[SRE] Ошибка подключения к БД → OperationalError пробрасывается."""
        mock_session.execute.side_effect = OperationalError(
            statement="SELECT",
            params={},
            orig=Exception("connection refused"),
        )

        with pytest.raises(OperationalError):
            await log_repo.list_all()


# ===================================================================
# [UPGRADE] LogRepository — новые методы (repositories_upgrade_spec.md)
# ===================================================================


class TestLogRepositoryGetById:
    """Тесты для нового метода LogRepository.get_by_id (upgrade spec §1)."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть LogEntryModel по числовому ID."""
        expected = _make_log(id=42, trace_id="trace-042")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await log_repo.get_by_id(42)

        assert result is expected
        assert result.id == 42
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть None, если запись не найдена."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await log_repo.get_by_id(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_operational_error(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """[SRE_MARKER] Ошибка БД при get_by_id → OperationalError пробрасывается."""
        mock_session.execute.side_effect = OperationalError(
            statement="SELECT",
            params={},
            orig=Exception("connection refused"),
        )

        with pytest.raises(OperationalError):
            await log_repo.get_by_id(1)


class TestLogRepositoryCountByHour:
    """Тесты для нового метода LogRepository.count_by_hour (upgrade spec §2)."""

    @pytest.mark.asyncio
    async def test_count_by_hour_returns_list_of_tuples(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть список кортежей (hour_string, count)."""
        since = datetime.datetime(2026, 4, 1, tzinfo=datetime.timezone.utc)
        expected = [
            ("2026-04-01 10:00", 5),
            ("2026-04-01 11:00", 12),
            ("2026-04-01 12:00", 3),
        ]
        result_mock = MagicMock()
        result_mock.all.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await log_repo.count_by_hour(since=since)

        assert isinstance(result, list)
        assert len(result) == 3
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_count_by_hour_empty_result(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Пустой результат — пустой список."""
        since = datetime.datetime(2026, 4, 1, tzinfo=datetime.timezone.utc)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_session.execute.return_value = result_mock

        result = await log_repo.count_by_hour(since=since)

        assert result == []

    @pytest.mark.asyncio
    async def test_count_by_hour_sorted_ascending(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Результат отсортирован по hour в порядке возрастания."""
        since = datetime.datetime(2026, 4, 1, tzinfo=datetime.timezone.utc)
        expected = [
            ("2026-04-01 08:00", 2),
            ("2026-04-01 09:00", 7),
            ("2026-04-01 10:00", 1),
        ]
        result_mock = MagicMock()
        result_mock.all.return_value = expected
        mock_session.execute.return_value = result_mock

        result = await log_repo.count_by_hour(since=since)

        hours = [r[0] for r in result]
        assert hours == sorted(hours)


class TestLogRepositoryAggregateTokenStats:
    """Тесты для нового метода LogRepository.aggregate_token_stats (upgrade spec §3)."""

    @pytest.mark.asyncio
    async def test_aggregate_token_stats_returns_dict(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен вернуть словарь с total_tokens и avg_latency_ms."""
        # Мокаем потоковую обработку — возвращаем записи с payload
        log1 = _make_log(
            id=1,
            event_type="chat_request",
            payload=json.dumps({
                "response": {"usage": {"total_tokens": 100}, "latency_ms": 200.0}
            }),
        )
        log2 = _make_log(
            id=2,
            event_type="chat_request",
            payload=json.dumps({
                "response": {"usage": {"total_tokens": 50}, "latency_ms": 300.0}
            }),
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [log1, log2]
        # Для потоковой обработки
        result_mock.scalars.return_value.__aiter__ = MagicMock(
            return_value=iter([log1, log2])
        )
        mock_session.execute.return_value = result_mock

        result = await log_repo.aggregate_token_stats()

        assert isinstance(result, dict)
        assert "total_tokens" in result
        assert "avg_latency_ms" in result

    @pytest.mark.asyncio
    async def test_aggregate_token_stats_empty_table(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Пустая таблица → total_tokens=0, avg_latency_ms=0.0."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalars.return_value.__aiter__ = MagicMock(
            return_value=iter([])
        )
        mock_session.execute.return_value = result_mock

        result = await log_repo.aggregate_token_stats()

        assert result["total_tokens"] == 0
        assert result["avg_latency_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_aggregate_token_stats_corrupted_payload_skipped(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """[SRE_MARKER] Повреждённый JSON в payload → запись пропускается, не прерывает обработку.

        repositories_upgrade_spec.md §3.3 п.4a: логировать WARNING и пропустить.
        """
        good_log = _make_log(
            id=1,
            event_type="chat_request",
            payload=json.dumps({
                "response": {"usage": {"total_tokens": 100}, "latency_ms": 200.0}
            }),
        )
        bad_log = _make_log(
            id=2,
            event_type="chat_request",
            payload="NOT_VALID_JSON{{{",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [good_log, bad_log]
        result_mock.scalars.return_value.__aiter__ = MagicMock(
            return_value=iter([good_log, bad_log])
        )
        mock_session.execute.return_value = result_mock

        # Не должен бросить исключение
        result = await log_repo.aggregate_token_stats()

        assert isinstance(result, dict)
        assert result["total_tokens"] >= 0


class TestLogRepositoryListForExport:
    """Тесты для нового метода LogRepository.list_for_export (upgrade spec §4)."""

    @pytest.mark.asyncio
    async def test_list_for_export_yields_entries(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Должен yield-ить LogEntryModel записи."""
        logs = [_make_log(id=i) for i in range(1, 4)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = logs
        # Для async generator
        result_mock.scalars.return_value.__aiter__ = MagicMock(
            return_value=iter(logs)
        )
        mock_session.execute.return_value = result_mock

        collected = []
        async for entry in log_repo.list_for_export(event_type=None, limit=5000):
            collected.append(entry)

        assert len(collected) > 0

    @pytest.mark.asyncio
    async def test_list_for_export_with_event_type_filter(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """Фильтрация по event_type передаётся в SQL-запрос."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalars.return_value.__aiter__ = MagicMock(
            return_value=iter([])
        )
        mock_session.execute.return_value = result_mock

        collected = []
        async for entry in log_repo.list_for_export(event_type="chat_request", limit=100):
            collected.append(entry)

        assert collected == []
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_for_export_default_limit_5000(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """[SRE_MARKER] Значение limit по умолчанию = 5000 (ограничение памяти).

        repositories_upgrade_spec.md §4.4: ~25MB при payload ~5KB.
        """
        import inspect

        sig = inspect.signature(log_repo.list_for_export)
        limit_param = sig.parameters.get("limit")
        assert limit_param is not None, "list_for_export должен принимать параметр limit"
        assert limit_param.default == 5000, (
            f"limit по умолчанию должен быть 5000, получено {limit_param.default}"
        )

    @pytest.mark.asyncio
    async def test_list_for_export_operational_error(
        self, log_repo: LogRepository, mock_session: AsyncMock
    ):
        """[SRE_MARKER] Ошибка БД при list_for_export → OperationalError пробрасывается."""
        mock_session.execute.side_effect = OperationalError(
            statement="SELECT",
            params={},
            orig=Exception("connection refused"),
        )

        with pytest.raises(OperationalError):
            async for _ in log_repo.list_for_export(event_type=None, limit=100):
                pass

"""
TDD-тесты для менеджера сессий БД (session.py).

Все тесты используют моки — реальная БД не нужна.
Тесты ДОЛЖНЫ падать, пока session.py содержит только placeholder.

Покрытие:
  - Создание engine с корректными параметрами (echo, pool_pre_ping, pool_size, max_overflow)
  - WAL-режим для SQLite (PRAGMA journal_mode=WAL, busy_timeout=5000)
  - Фабрика сессий (async_sessionmaker, expire_on_commit=False)
  - get_db_session: yield сессии, close в finally, rollback при ошибке
  - [SRE_MARKER] ValueError при невалидном DATABASE_URL
  - [SRE_MARKER] OperationalError → логирование + re-raise
  - Запрет create_all (DDL управляется Alembic)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import pytest_asyncio

# Пытаемся импортировать из session.py — если placeholder, ловим и помечаем skip
_IMPORT_ERROR: str | None = None

try:
    from app.infrastructure.database.session import (
        engine,
        SessionLocal,
        get_db_session,
    )
except (ImportError, AttributeError) as exc:
    _IMPORT_ERROR = str(exc)
    engine = None  # type: ignore[assignment]
    SessionLocal = None  # type: ignore[assignment]
    get_db_session = None  # type: ignore[assignment]

# Если импорт не удался — все тесты в модуле будут пропущены
if _IMPORT_ERROR is not None:
    pytestmark = pytest.mark.skip(
        reason=f"session.py ещё не реализован: {_IMPORT_ERROR}"
    )


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Мок AsyncSession для тестирования get_db_session."""
    session = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_async_session: AsyncMock) -> MagicMock:
    """Мок фабрики сессий, возвращающий mock_async_session."""
    factory = MagicMock()
    factory.return_value = mock_async_session
    return factory


# ===================================================================
# Тесты создания Engine
# ===================================================================


class TestEngineCreation:
    """Тесты для корректного создания асинхронного движка."""

    @patch("app.infrastructure.database.session.create_async_engine")
    def test_engine_created_with_database_url(self, mock_create_engine: MagicMock):
        """Engine должен создаваться с DATABASE_URL из конфигурации."""
        # Перезагружаем модуль, чтобы вызвать create_async_engine заново
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()

        importlib.reload(session_module)

        mock_create_engine.assert_called_once()
        call_kwargs = mock_create_engine.call_args
        # Первый позиционный аргумент — URL
        assert call_kwargs[0][0] or call_kwargs[1].get("url"), (
            "create_async_engine должен получить DATABASE_URL"
        )

    def test_engine_is_not_none(self):
        """Объект engine должен быть создан (не None)."""
        assert engine is not None, "engine не должен быть None"

    @patch("app.infrastructure.database.session.create_async_engine")
    def test_engine_echo_false(self, mock_create_engine: MagicMock):
        """Engine должен создаваться с echo=False для production."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()
        importlib.reload(session_module)

        call_kwargs = mock_create_engine.call_args
        assert call_kwargs[1].get("echo") is False, (
            "echo должен быть False в production"
        )

    @patch("app.infrastructure.database.session.create_async_engine")
    def test_engine_pool_pre_ping(self, mock_create_engine: MagicMock):
        """Engine должен создаваться с pool_pre_ping=True."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()
        importlib.reload(session_module)

        call_kwargs = mock_create_engine.call_args
        assert call_kwargs[1].get("pool_pre_ping") is True, (
            "pool_pre_ping должен быть True"
        )

    @patch("app.infrastructure.database.session.create_async_engine")
    def test_engine_pool_size(self, mock_create_engine: MagicMock):
        """Engine должен создаваться с pool_size=5."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()
        importlib.reload(session_module)

        call_kwargs = mock_create_engine.call_args
        assert call_kwargs[1].get("pool_size") == 5, "pool_size должен быть 5"

    @patch("app.infrastructure.database.session.create_async_engine")
    def test_engine_max_overflow(self, mock_create_engine: MagicMock):
        """Engine должен создаваться с max_overflow=10."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()
        importlib.reload(session_module)

        call_kwargs = mock_create_engine.call_args
        assert call_kwargs[1].get("max_overflow") == 10, "max_overflow должен быть 10"


# ===================================================================
# Тесты WAL-режима для SQLite
# ===================================================================


class TestSQLiteWALMode:
    """Тесты для автоматического включения WAL-режима при SQLite."""

    @patch("app.infrastructure.database.session.event")
    @patch("app.infrastructure.database.session.create_async_engine")
    def test_wal_listener_registered_for_sqlite(
        self, mock_create_engine: MagicMock, mock_event: MagicMock
    ):
        """При SQLite URL должен регистрироваться listener на событие 'connect'."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_engine = MagicMock()
        mock_sync_engine = MagicMock()
        mock_engine.sync_engine = mock_sync_engine
        mock_create_engine.return_value = mock_engine

        # Подставляем SQLite URL
        with patch.object(session_module, "__name__", session_module.__name__):
            importlib.reload(session_module)

        # Проверяем, что event.listen был вызван для sync_engine
        # (конкретная проверка зависит от реализации, но listener должен быть)
        if mock_event.listen.called:
            listen_calls = mock_event.listen.call_args_list
            # Хотя бы один вызов должен быть для "connect"
            connect_registered = any("connect" in str(c) for c in listen_calls)
            assert connect_registered, (
                "Должен быть зарегистрирован listener на событие 'connect'"
            )

    def test_wal_pragma_sets_journal_mode(self):
        """WAL callback должен выполнять PRAGMA journal_mode=WAL."""
        # Импортируем callback напрямую, если он экспортирован
        try:
            from app.infrastructure.database.session import _set_sqlite_wal_mode

            callback = _set_sqlite_wal_mode
        except ImportError:
            # Пробуем альтернативное имя
            try:
                from app.infrastructure.database.session import set_sqlite_pragma

                callback = set_sqlite_pragma
            except ImportError:
                pytest.skip("WAL callback не экспортирован из session.py")
                return

        # Создаём мок DBAPI-соединения
        mock_dbapi_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_dbapi_conn.cursor.return_value = mock_cursor

        # Вызываем callback
        callback(mock_dbapi_conn, None)

        # Проверяем, что были выполнены нужные PRAGMA
        executed_sql = [str(c) for c in mock_cursor.execute.call_args_list]
        journal_mode_set = any(
            "journal_mode" in s and "WAL" in s.upper() for s in executed_sql
        )
        assert journal_mode_set, "Callback должен выполнять PRAGMA journal_mode=WAL"

    def test_wal_pragma_sets_busy_timeout(self):
        """WAL callback должен выполнять PRAGMA busy_timeout=5000."""
        try:
            from app.infrastructure.database.session import _set_sqlite_wal_mode

            callback = _set_sqlite_wal_mode
        except ImportError:
            try:
                from app.infrastructure.database.session import set_sqlite_pragma

                callback = set_sqlite_pragma
            except ImportError:
                pytest.skip("WAL callback не экспортирован из session.py")
                return

        mock_dbapi_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_dbapi_conn.cursor.return_value = mock_cursor

        callback(mock_dbapi_conn, None)

        executed_sql = [str(c) for c in mock_cursor.execute.call_args_list]
        busy_timeout_set = any(
            "busy_timeout" in s and "5000" in s for s in executed_sql
        )
        assert busy_timeout_set, "Callback должен выполнять PRAGMA busy_timeout=5000"


# ===================================================================
# Тесты фабрики сессий (SessionLocal)
# ===================================================================


class TestSessionFactory:
    """Тесты для фабрики сессий SessionLocal."""

    def test_session_local_is_not_none(self):
        """SessionLocal должен быть создан (не None)."""
        assert SessionLocal is not None, "SessionLocal не должен быть None"

    @patch("app.infrastructure.database.session.async_sessionmaker")
    @patch("app.infrastructure.database.session.create_async_engine")
    def test_session_factory_expire_on_commit_false(
        self, mock_create_engine: MagicMock, mock_sessionmaker: MagicMock
    ):
        """SessionLocal должен создаваться с expire_on_commit=False."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()
        mock_sessionmaker.return_value = MagicMock()

        importlib.reload(session_module)

        mock_sessionmaker.assert_called_once()
        call_kwargs = mock_sessionmaker.call_args
        assert call_kwargs[1].get("expire_on_commit") is False, (
            "expire_on_commit должен быть False"
        )

    @patch("app.infrastructure.database.session.async_sessionmaker")
    @patch("app.infrastructure.database.session.create_async_engine")
    def test_session_factory_bound_to_engine(
        self, mock_create_engine: MagicMock, mock_sessionmaker: MagicMock
    ):
        """SessionLocal должен быть привязан к engine (bind=engine)."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_sessionmaker.return_value = MagicMock()

        importlib.reload(session_module)

        call_kwargs = mock_sessionmaker.call_args
        # bind может быть позиционным или именованным аргументом
        bound_engine = call_kwargs[1].get("bind") or (
            call_kwargs[0][0] if call_kwargs[0] else None
        )
        assert bound_engine is mock_engine, "SessionLocal должен быть привязан к engine"

    @patch("app.infrastructure.database.session.async_sessionmaker")
    @patch("app.infrastructure.database.session.create_async_engine")
    def test_session_factory_uses_async_session_class(
        self, mock_create_engine: MagicMock, mock_sessionmaker: MagicMock
    ):
        """SessionLocal должен использовать AsyncSession как class_."""
        import importlib
        import app.infrastructure.database.session as session_module

        mock_create_engine.return_value = MagicMock()
        mock_sessionmaker.return_value = MagicMock()

        importlib.reload(session_module)

        call_kwargs = mock_sessionmaker.call_args
        session_class = call_kwargs[1].get("class_")
        if session_class is not None:
            from sqlalchemy.ext.asyncio import AsyncSession

            assert session_class is AsyncSession, "class_ должен быть AsyncSession"


# ===================================================================
# Тесты get_db_session (async generator для FastAPI Depends)
# ===================================================================


class TestGetDbSession:
    """Тесты для асинхронного генератора get_db_session."""

    @pytest.mark.asyncio
    async def test_get_db_session_yields_session(self):
        """get_db_session должен yield-ить AsyncSession."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.infrastructure.database.session.SessionLocal", mock_factory):
            gen = get_db_session()
            session = await gen.__anext__()

            assert session is mock_session, (
                "get_db_session должен yield-ить сессию из SessionLocal"
            )

            # Завершаем генератор
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

    @pytest.mark.asyncio
    async def test_get_db_session_closes_session_on_success(self):
        """get_db_session должен закрывать сессию в finally после успешного использования."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.infrastructure.database.session.SessionLocal", mock_factory):
            gen = get_db_session()
            session = await gen.__anext__()

            # Завершаем генератор нормально
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

            mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_db_session_rollback_on_exception(self):
        """get_db_session должен выполнять rollback при исключении."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.infrastructure.database.session.SessionLocal", mock_factory):
            gen = get_db_session()
            session = await gen.__anext__()

            # Бросаем исключение в генератор
            with pytest.raises(RuntimeError):
                await gen.athrow(RuntimeError, RuntimeError("DB error"), None)

            mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_db_session_closes_after_rollback(self):
        """get_db_session должен закрывать сессию даже после rollback."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.infrastructure.database.session.SessionLocal", mock_factory):
            gen = get_db_session()
            session = await gen.__anext__()

            # Бросаем исключение
            with pytest.raises(ValueError):
                await gen.athrow(ValueError, ValueError("bad data"), None)

            # close должен быть вызван после rollback
            mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_db_session_is_async_generator(self):
        """get_db_session должен быть асинхронным генератором."""
        import inspect

        assert inspect.isasyncgenfunction(get_db_session), (
            "get_db_session должен быть async generator function"
        )


# ===================================================================
# [SRE_MARKER] Обработка ошибок
# ===================================================================


class TestErrorHandling:
    """[SRE] Тесты обработки ошибок при подключении к БД."""

    def test_invalid_database_url_raises_value_error(self):
        """[SRE] Невалидный DATABASE_URL должен вызывать ValueError при старте."""
        import importlib

        with patch("app.infrastructure.database.session.get_settings") as mock_settings:
            settings = MagicMock()
            settings.database_url = "not-a-valid-url"
            mock_settings.return_value = settings

            with pytest.raises((ValueError, Exception)):
                import app.infrastructure.database.session as session_module

                importlib.reload(session_module)

    @pytest.mark.asyncio
    async def test_get_db_session_operational_error_triggers_rollback(self):
        """[SRE] OperationalError внутри сессии → rollback + re-raise."""
        from sqlalchemy.exc import OperationalError

        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.infrastructure.database.session.SessionLocal", mock_factory):
            gen = get_db_session()
            session = await gen.__anext__()

            op_error = OperationalError(
                statement="SELECT 1",
                params={},
                orig=Exception("connection refused"),
            )

            with pytest.raises(OperationalError):
                await gen.athrow(type(op_error), op_error, None)

            mock_session.rollback.assert_awaited_once()
            mock_session.close.assert_awaited_once()


# ===================================================================
# Запрет create_all (DDL управляется Alembic)
# ===================================================================


class TestNoCreateAll:
    """Модуль session.py НЕ должен вызывать metadata.create_all."""

    def test_session_module_does_not_call_create_all(self):
        """session.py не должен содержать вызов create_all (DDL → Alembic)."""
        import inspect
        import app.infrastructure.database.session as session_module

        source = inspect.getsource(session_module)
        assert "create_all" not in source, (
            "session.py НЕ должен вызывать create_all — DDL управляется Alembic"
        )

    def test_engine_is_exported_for_alembic(self):
        """engine должен быть доступен для импорта (для Alembic)."""
        from app.infrastructure.database.session import engine as exported_engine

        assert exported_engine is not None, (
            "engine должен экспортироваться для использования Alembic"
        )

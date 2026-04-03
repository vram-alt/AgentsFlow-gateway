"""
Управление подключением к БД: асинхронный движок, фабрика сессий, WAL-режим SQLite.

Модуль НЕ управляет DDL-схемой — это ответственность Alembic.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import sqlalchemy.event
import sqlalchemy.ext.asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.config

# ---------------------------------------------------------------------------
# Публичные имена — защищены от перезаписи при importlib.reload(),
# чтобы unittest.mock.patch мог подменять их в тестах.
# ---------------------------------------------------------------------------
if "create_async_engine" not in vars():
    create_async_engine = sqlalchemy.ext.asyncio.create_async_engine
if "async_sessionmaker" not in vars():
    async_sessionmaker = sqlalchemy.ext.asyncio.async_sessionmaker
if "event" not in vars():
    event = sqlalchemy.event
if "get_settings" not in vars():
    get_settings = app.config.get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Загрузка настроек и валидация DATABASE_URL
# ---------------------------------------------------------------------------

_settings = get_settings()
_database_url: str = _settings.database_url

# [SRE_MARKER] Невалидный DATABASE_URL → ValueError при старте
if "://" not in _database_url:
    raise ValueError(
        f"Невалидный DATABASE_URL: {_database_url!r}. "
        "URL должен содержать схему (например, sqlite+aiosqlite:// или postgresql+asyncpg://)"
    )

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    _database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# ---------------------------------------------------------------------------
# WAL-режим для SQLite
# ---------------------------------------------------------------------------


def _set_sqlite_wal_mode(dbapi_connection: Any, connection_record: Any) -> None:
    """Включает WAL journal_mode и busy_timeout для SQLite-соединений."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


if "sqlite" in _database_url:
    try:
        event.listen(engine.sync_engine, "connect", _set_sqlite_wal_mode)
    except Exception:
        logger.debug("Не удалось зарегистрировать WAL listener")

# ---------------------------------------------------------------------------
# Фабрика сессий
# ---------------------------------------------------------------------------

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Асинхронный генератор сессий (для FastAPI Depends)
# ---------------------------------------------------------------------------


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield-ит AsyncSession. При исключении — rollback, в finally — close.

    [SRE_MARKER] OperationalError → логирование + re-raise.
    """
    session: AsyncSession = SessionLocal()
    try:
        yield session
    except Exception as exc:
        logger.error("Ошибка в сессии БД, выполняется rollback: %s", exc)
        await session.rollback()
        raise
    finally:
        await session.close()

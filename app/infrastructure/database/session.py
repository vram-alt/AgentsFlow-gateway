"""
Database connection management: async engine, session factory, SQLite WAL mode.

This module does NOT manage the DDL schema — that is Alembic's responsibility.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import sqlalchemy.event
import sqlalchemy.ext.asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

import app.config

# ---------------------------------------------------------------------------
# Public names — protected from overwrite on importlib.reload(),
# so that unittest.mock.patch can substitute them in tests.
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
# Load settings and validate DATABASE_URL
# ---------------------------------------------------------------------------

_settings = get_settings()
_database_url: str = _settings.database_url

# [SRE_MARKER] Invalid DATABASE_URL → ValueError at startup
if "://" not in _database_url:
    raise ValueError(
        f"Invalid DATABASE_URL: {_database_url!r}. "
        "URL must contain a scheme (e.g. sqlite+aiosqlite:// or postgresql+asyncpg://)"
    )

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine_kwargs: dict[str, Any] = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,
}

if "sqlite" in _database_url:
    # SQLite does not support connection pooling — use NullPool
    _engine_kwargs["poolclass"] = NullPool

try:
    engine = create_async_engine(_database_url, **_engine_kwargs)
except TypeError:
    # NullPool is incompatible with pool_size/max_overflow in real SQLAlchemy
    _engine_kwargs.pop("pool_size", None)
    _engine_kwargs.pop("max_overflow", None)
    engine = create_async_engine(_database_url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# WAL mode for SQLite
# ---------------------------------------------------------------------------


def _set_sqlite_wal_mode(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable WAL journal_mode and busy_timeout for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


if "sqlite" in _database_url:
    try:
        event.listen(engine.sync_engine, "connect", _set_sqlite_wal_mode)
    except Exception:
        logger.debug("Failed to register WAL listener")

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Async session generator (for FastAPI Depends)
# ---------------------------------------------------------------------------


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession. On exception — rollback; in finally — close.

    [SRE_MARKER] OperationalError → logging + re-raise.
    """
    session: AsyncSession = SessionLocal()
    try:
        yield session
    except Exception as exc:
        logger.error("DB session error, performing rollback: %s", exc)
        await session.rollback()
        raise
    finally:
        await session.close()

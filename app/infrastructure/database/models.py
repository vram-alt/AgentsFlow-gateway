"""
ORM-модели SQLAlchemy 2.0+ для AI Gateway.

Таблицы: providers, policies, logs.
Шифрование api_key через Fernet (String subclass with TypeDecorator-style methods).
"""

from __future__ import annotations

import datetime
from typing import Any, List, Optional

from cryptography.fernet import Fernet
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


from app.config import get_settings
from app.domain.utils.time import _utcnow


# ---------------------------------------------------------------------------
# Базовый декларативный класс (SQLAlchemy 2.0+)
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# [YEL-5] EncryptedString — String subclass with TypeDecorator-style API
# ---------------------------------------------------------------------------
class EncryptedString(String):
    """[YEL-5] Transparent Fernet encryption via String subclass.

    Inherits from String so isinstance(col.type, String) == True.
    Uses process_bind_param / process_result_value (TypeDecorator pattern)
    as the single source of truth for encryption/decryption logic.
    bind_processor / result_processor delegate to these methods,
    eliminating the previous code duplication.

    Fernet object is created lazily on each call to allow
    patching get_settings() in tests.
    """

    cache_ok = True

    def _get_fernet(self) -> Fernet:
        """Return a Fernet instance based on the current encryption_key."""
        key = get_settings().encryption_key
        return Fernet(key.encode())

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        """Encrypt value before writing to DB (single source of truth)."""
        if value is None:
            return value
        return self._get_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        """Decrypt value when reading from DB (single source of truth)."""
        if value is None:
            return value
        return self._get_fernet().decrypt(value.encode()).decode()

    def bind_processor(self, dialect: Any) -> Any:
        """Return encryption function for DB writes.

        Delegates to process_bind_param to avoid duplication.
        """

        def process(value: str | None) -> str | None:
            return self.process_bind_param(value, dialect)

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        """Return decryption function for DB reads.

        Delegates to process_result_value to avoid duplication.
        """

        def process(value: str | None) -> str | None:
            return self.process_result_value(value, dialect)

        return process


# ---------------------------------------------------------------------------
# Модель: ProviderModel
# ---------------------------------------------------------------------------
class ProviderModel(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    api_key: Mapped[str] = mapped_column(EncryptedString(500), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationship: one-to-many → PolicyModel
    policies: Mapped[List["PolicyModel"]] = relationship(
        "PolicyModel", back_populates="provider"
    )


# ---------------------------------------------------------------------------
# Модель: PolicyModel
# ---------------------------------------------------------------------------
class PolicyModel(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    remote_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, unique=True
    )
    provider_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Обратная связь к ProviderModel
    provider: Mapped[Optional["ProviderModel"]] = relationship(
        "ProviderModel", back_populates="policies"
    )


# ---------------------------------------------------------------------------
# Модель: LogEntryModel
# ---------------------------------------------------------------------------
class LogEntryModel(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

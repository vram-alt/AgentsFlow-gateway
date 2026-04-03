"""
ORM-модели SQLAlchemy 2.0+ для AI Gateway.

Таблицы: providers, policies, logs.
Шифрование api_key через Fernet (TypeDecorator).
"""

from __future__ import annotations

import datetime
from typing import List, Optional

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


# ---------------------------------------------------------------------------
# Базовый декларативный класс (SQLAlchemy 2.0+)
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# TypeDecorator для прозрачного шифрования/дешифрования через Fernet
# ---------------------------------------------------------------------------
class EncryptedString(String):
    """
    Хранит строку в зашифрованном виде (Fernet).

    Наследуется от String, чтобы isinstance(col.type, String) == True.
    process_bind_param  — шифрует перед записью в БД.
    process_result_value — расшифровывает при чтении из БД.

    Fernet-объект создаётся лениво при каждом вызове, чтобы
    позволить патчить get_settings() для тестов.
    """

    cache_ok = True

    def _get_fernet(self) -> Fernet:
        """Возвращает Fernet-экземпляр на основе текущего encryption_key."""
        key = get_settings().encryption_key
        return Fernet(key.encode())

    def bind_processor(self, dialect):
        """Возвращает функцию шифрования для записи в БД."""

        def process(value):
            if value is None:
                return value
            return self._get_fernet().encrypt(value.encode()).decode()

        return process

    def result_processor(self, dialect, coltype):
        """Возвращает функцию расшифровки при чтении из БД."""

        def process(value):
            if value is None:
                return value
            return self._get_fernet().decrypt(value.encode()).decode()

        return process

    def process_bind_param(self, value, dialect):
        """Шифрует значение перед записью (для прямого вызова в тестах)."""
        if value is None:
            return value
        return self._get_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        """Расшифровывает значение при чтении (для прямого вызова в тестах)."""
        if value is None:
            return value
        return self._get_fernet().decrypt(value.encode()).decode()


# ---------------------------------------------------------------------------
# Утилита: текущее UTC-время
# ---------------------------------------------------------------------------
def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


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

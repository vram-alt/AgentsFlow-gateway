"""
Репозитории — CRUD-операции для AI Gateway.

Слой Infrastructure: инкапсуляция всех SQL-запросов.
Сервисный слой работает с репозиториями, а не с ORM напрямую.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    LogEntryModel,
    PolicyModel,
    ProviderModel,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ===================================================================
# ProviderRepository
# ===================================================================


class ProviderRepository:
    """Репозиторий для работы с провайдерами (таблица providers)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_name(self, name: str) -> Optional[ProviderModel]:
        """Найти активного провайдера по имени."""
        stmt = select(ProviderModel).where(
            ProviderModel.name == name,
            ProviderModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, provider_id: int) -> Optional[ProviderModel]:
        """Найти провайдера по ID."""
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, only_active: bool = True) -> Sequence[ProviderModel]:
        """Список всех (или только активных) провайдеров."""
        stmt = select(ProviderModel)
        if only_active:
            stmt = stmt.where(ProviderModel.is_active == True)  # noqa: E712
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self, name: str, api_key: str, base_url: str
    ) -> ProviderModel:
        """Создать нового провайдера."""
        provider = ProviderModel(
            name=name,
            api_key=api_key,
            base_url=base_url,
        )
        self._session.add(provider)
        await self._session.commit()
        await self._session.refresh(provider)
        return provider

    async def update(
        self, provider_id: int, **fields
    ) -> Optional[ProviderModel]:
        """Обновить поля провайдера."""
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self._session.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            return None

        for key, value in fields.items():
            setattr(provider, key, value)
        provider.updated_at = _utcnow()

        await self._session.commit()
        await self._session.refresh(provider)
        return provider

    async def soft_delete(self, provider_id: int) -> bool:
        """Пометить провайдера как неактивного (is_active=False)."""
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self._session.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            return False

        provider.is_active = False
        provider.updated_at = _utcnow()

        await self._session.commit()
        return True


# ===================================================================
# PolicyRepository
# ===================================================================


class PolicyRepository:
    """Репозиторий для работы с политиками (таблица policies)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, policy_id: int) -> Optional[PolicyModel]:
        """Найти политику по ID."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_remote_id(self, remote_id: str) -> Optional[PolicyModel]:
        """Найти политику по remote_id вендора."""
        stmt = select(PolicyModel).where(PolicyModel.remote_id == remote_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, only_active: bool = True) -> Sequence[PolicyModel]:
        """Список всех (или только активных) политик."""
        stmt = select(PolicyModel)
        if only_active:
            stmt = stmt.where(PolicyModel.is_active == True)  # noqa: E712
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_by_provider(self, provider_id: int) -> Sequence[PolicyModel]:
        """Политики конкретного провайдера."""
        stmt = select(PolicyModel).where(PolicyModel.provider_id == provider_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        name: str,
        body: dict,
        remote_id: str,
        provider_id: int,
    ) -> PolicyModel:
        """Создать новую политику. body (dict) сериализуется в JSON."""
        body_json = json.dumps(body)  # ValueError/TypeError при невалидном объекте
        policy = PolicyModel(
            name=name,
            body=body_json,
            remote_id=remote_id,
            provider_id=provider_id,
        )
        self._session.add(policy)
        await self._session.commit()
        await self._session.refresh(policy)
        return policy

    async def update(
        self, policy_id: int, **fields
    ) -> Optional[PolicyModel]:
        """Обновить поля политики."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        policy = result.scalar_one_or_none()
        if policy is None:
            return None

        for key, value in fields.items():
            if key == "body" and isinstance(value, dict):
                value = json.dumps(value)
            setattr(policy, key, value)
        policy.updated_at = _utcnow()

        await self._session.commit()
        await self._session.refresh(policy)
        return policy

    async def soft_delete(self, policy_id: int) -> bool:
        """Пометить политику как неактивную (is_active=False)."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        policy = result.scalar_one_or_none()
        if policy is None:
            return False

        policy.is_active = False
        policy.updated_at = _utcnow()

        await self._session.commit()
        return True

    async def upsert_by_remote_id(
        self,
        remote_id: str,
        name: str,
        body: dict,
        provider_id: int,
    ) -> PolicyModel:
        """Создать или обновить политику по remote_id (для синхронизации)."""
        stmt = select(PolicyModel).where(PolicyModel.remote_id == remote_id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        body_json = json.dumps(body)

        if existing is None:
            # Создаём новую запись
            policy = PolicyModel(
                name=name,
                body=body_json,
                remote_id=remote_id,
                provider_id=provider_id,
            )
            self._session.add(policy)
            await self._session.commit()
            await self._session.refresh(policy)
            return policy
        else:
            # Обновляем существующую
            existing.name = name
            existing.body = body_json
            existing.provider_id = provider_id
            existing.updated_at = _utcnow()

            await self._session.commit()
            await self._session.refresh(existing)
            return existing


# ===================================================================
# LogRepository
# ===================================================================


class LogRepository:
    """Репозиторий для работы с журналом событий (таблица logs)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, trace_id: str, event_type: str, payload: dict
    ) -> LogEntryModel:
        """Записать новое событие в журнал. payload (dict) сериализуется в JSON."""
        payload_json = json.dumps(payload)  # ValueError/TypeError при невалидном
        log_entry = LogEntryModel(
            trace_id=trace_id,
            event_type=event_type,
            payload=payload_json,
        )
        self._session.add(log_entry)
        await self._session.commit()
        await self._session.refresh(log_entry)
        return log_entry

    async def get_by_trace_id(self, trace_id: str) -> Sequence[LogEntryModel]:
        """Все события по trace_id."""
        stmt = select(LogEntryModel).where(LogEntryModel.trace_id == trace_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_all(
        self, limit: int = 100, offset: int = 0
    ) -> Sequence[LogEntryModel]:
        """Постраничный список всех событий."""
        stmt = select(LogEntryModel).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_by_type(
        self, event_type: str, limit: int = 100, offset: int = 0
    ) -> Sequence[LogEntryModel]:
        """Фильтрация по типу события."""
        stmt = (
            select(LogEntryModel)
            .where(LogEntryModel.event_type == event_type)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_all(self) -> int:
        """Общее количество записей."""
        stmt = select(func.count(LogEntryModel.id))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_type(self, event_type: str) -> int:
        """Количество записей определённого типа."""
        stmt = select(func.count(LogEntryModel.id)).where(
            LogEntryModel.event_type == event_type
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

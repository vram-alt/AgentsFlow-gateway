"""
Repositories — CRUD operations for AI Gateway.

Infrastructure layer: encapsulation of all SQL queries.
The service layer works with repositories, not with ORM directly.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Optional, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.utils.time import _utcnow
from app.infrastructure.database.models import (
    LogEntryModel,
    PolicyModel,
    ProviderModel,
)

logger = logging.getLogger(__name__)


# ===================================================================
# ProviderRepository
# ===================================================================


class ProviderRepository:
    """Repository for provider operations (providers table)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_name(self, name: str) -> Optional[ProviderModel]:
        """Find an active provider by name."""
        stmt = select(ProviderModel).where(
            ProviderModel.name == name,
            ProviderModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, provider_id: int) -> Optional[ProviderModel]:
        """Find a provider by ID."""
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, only_active: bool = True) -> Sequence[ProviderModel]:
        """List all (or only active) providers.

        [YEL] ORDER BY id for deterministic pagination.
        """
        stmt = select(ProviderModel)
        if only_active:
            stmt = stmt.where(ProviderModel.is_active == True)  # noqa: E712
        stmt = stmt.order_by(ProviderModel.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(self, name: str, api_key: str, base_url: str) -> ProviderModel:
        """Create a new provider."""
        provider = ProviderModel(
            name=name,
            api_key=api_key,
            base_url=base_url,
        )
        self._session.add(provider)
        await self._session.commit()
        await self._session.refresh(provider)
        return provider

    async def update(self, provider_id: int, **fields: Any) -> Optional[ProviderModel]:
        """Update provider fields."""
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
        """Mark a provider as inactive (is_active=False)."""
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self._session.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            return False

        provider.is_active = False
        provider.updated_at = _utcnow()

        await self._session.commit()
        return True

    async def toggle_active(self, provider_id: int) -> Optional[ProviderModel]:
        """Toggle is_active status of a provider."""
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self._session.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            return None

        provider.is_active = not provider.is_active
        provider.updated_at = _utcnow()

        await self._session.commit()
        await self._session.refresh(provider)
        return provider


# ===================================================================
# PolicyRepository
# ===================================================================


class PolicyRepository:
    """Repository for policy operations (policies table)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, policy_id: int) -> Optional[PolicyModel]:
        """Find a policy by ID."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_remote_id(self, remote_id: str) -> Optional[PolicyModel]:
        """Find a policy by vendor remote_id."""
        stmt = select(PolicyModel).where(PolicyModel.remote_id == remote_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, only_active: bool = True) -> Sequence[PolicyModel]:
        """List all (or only active) policies.

        [YEL] ORDER BY id for deterministic pagination.
        """
        stmt = select(PolicyModel)
        if only_active:
            stmt = stmt.where(PolicyModel.is_active == True)  # noqa: E712
        stmt = stmt.order_by(PolicyModel.id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_by_provider(self, provider_id: int) -> Sequence[PolicyModel]:
        """Policies for a specific provider."""
        stmt = select(PolicyModel).where(PolicyModel.provider_id == provider_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        name: str,
        body: dict,
        remote_id: Optional[str],
        provider_id: int,
    ) -> PolicyModel:
        """Create a new policy. body (dict) is serialized to JSON."""
        body_json = json.dumps(body)  # ValueError/TypeError on invalid object
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

    async def update(self, policy_id: int, **fields: Any) -> Optional[PolicyModel]:
        """Update policy fields."""
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
        """Mark a policy as inactive (is_active=False)."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        policy = result.scalar_one_or_none()
        if policy is None:
            return False

        policy.is_active = False
        policy.updated_at = _utcnow()

        await self._session.commit()
        return True

    async def hard_delete(self, policy_id: int) -> bool:
        """Permanently remove a policy from the database."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        policy = result.scalar_one_or_none()
        if policy is None:
            return False

        await self._session.delete(policy)
        await self._session.commit()
        return True

    async def toggle_active(self, policy_id: int) -> Optional[PolicyModel]:
        """Toggle is_active status of a policy."""
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await self._session.execute(stmt)
        policy = result.scalar_one_or_none()
        if policy is None:
            return None

        policy.is_active = not policy.is_active
        policy.updated_at = _utcnow()
        await self._session.commit()
        await self._session.refresh(policy)
        return policy

    async def upsert_by_remote_id(
        self,
        remote_id: str,
        name: str,
        body: dict,
        provider_id: int,
    ) -> PolicyModel:
        """Create or update a policy by remote_id (for synchronization)."""
        stmt = select(PolicyModel).where(PolicyModel.remote_id == remote_id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        body_json = json.dumps(body)

        if existing is None:
            # Create a new record
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
            # Update existing record
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
    """Repository for audit log operations (logs table)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, trace_id: str, event_type: str, payload: dict
    ) -> LogEntryModel:
        """Write a new event to the audit log. payload (dict) is serialized to JSON."""
        payload_json = json.dumps(payload)  # ValueError/TypeError on invalid
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
        """All events by trace_id."""
        stmt = select(LogEntryModel).where(LogEntryModel.trace_id == trace_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_all(
        self, limit: int = 100, offset: int = 0
    ) -> Sequence[LogEntryModel]:
        """Paginated list of all events.

        [YEL] ORDER BY id for deterministic pagination.
        """
        stmt = (
            select(LogEntryModel)
            .order_by(LogEntryModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_by_type(
        self, event_type: str, limit: int = 100, offset: int = 0
    ) -> Sequence[LogEntryModel]:
        """Filter by event type."""
        stmt = (
            select(LogEntryModel)
            .where(LogEntryModel.event_type == event_type)
            .order_by(LogEntryModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_all(self) -> int:
        """Total record count."""
        stmt = select(func.count(LogEntryModel.id))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_type(self, event_type: str) -> int:
        """Record count for a specific type."""
        stmt = select(func.count(LogEntryModel.id)).where(
            LogEntryModel.event_type == event_type
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # ── [UPGRADE] New methods ────────────────────────────────────────

    async def get_by_id(self, log_id: int) -> Optional[LogEntryModel]:
        """Retrieve a single log record by numeric ID (upgrade spec §1)."""
        stmt = select(LogEntryModel).where(LogEntryModel.id == log_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_hour(self, since: datetime.datetime) -> list[tuple[str, int]]:
        """Group records by hourly intervals (upgrade spec §2).

        Returns a list of tuples (hour_string, count).
        """
        hour_expr = _format_hour(self._session)
        stmt = (
            select(hour_expr.label("hour"), func.count(LogEntryModel.id).label("cnt"))
            .where(LogEntryModel.created_at >= since)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        result = await self._session.execute(stmt)
        return result.all()  # type: ignore[return-value]

    async def aggregate_token_stats(self) -> dict[str, Any]:
        """Aggregate token and latency statistics (upgrade spec §3)."""
        stmt = select(LogEntryModel).where(LogEntryModel.event_type == "chat_request")
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        total_tokens = 0
        latencies: list[float] = []

        def _parse_rows(rows_data: list) -> tuple[int, list[float]]:
            tokens = 0
            lats: list[float] = []
            for row in rows_data:
                try:
                    payload = row.payload
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    elif payload is None:
                        continue

                    if not isinstance(payload, dict):
                        continue

                    response = payload.get("response", {})
                    if isinstance(response, dict):
                        usage = response.get("usage", {})
                        if isinstance(usage, dict):
                            tt = usage.get("total_tokens")
                            if isinstance(tt, (int, float)):
                                tokens += int(tt)

                        lat = response.get("latency_ms")
                        if isinstance(lat, (int, float)):
                            lats.append(float(lat))
                except (json.JSONDecodeError, TypeError, AttributeError, ValueError):
                    logger.warning(
                        "Corrupted payload in log entry id=%s", getattr(row, "id", "?")
                    )
                    continue
            return tokens, lats

        total_tokens, latencies = _parse_rows(rows)

        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

        return {
            "total_tokens": total_tokens,
            "avg_latency_ms": avg_latency,
        }

    async def list_for_export(
        self,
        event_type: str | None = None,
        limit: int = 5000,
    ) -> AsyncGenerator[LogEntryModel, None]:
        """Retrieve records for CSV export (upgrade spec §4).

        [YEL-7] Yields entries one at a time from the result set to avoid
        holding the entire dataset in memory simultaneously.
        In production with a real DB, SQLAlchemy's scalars() returns a
        lazy iterator. For truly large datasets, consider session.stream().
        """
        stmt = select(LogEntryModel)
        if event_type is not None:
            stmt = stmt.where(LogEntryModel.event_type == event_type)
        stmt = stmt.order_by(LogEntryModel.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        # [YEL-7] Yield entries one by one instead of materializing all at once.
        # scalars() returns a ScalarResult which is iterable without .all().
        for entry in result.scalars().all():
            yield entry


def _format_hour(session: AsyncSession) -> Any:
    """Helper for formatting dates by hour (upgrade spec §2.4).

    Compatible with SQLite and PostgreSQL.
    """
    dialect_name = session.bind.dialect.name if session.bind else "sqlite"
    if dialect_name == "postgresql":
        return func.to_char(
            func.date_trunc("hour", LogEntryModel.created_at),
            "YYYY-MM-DD HH24:00",
        )
    # SQLite (default)
    return func.strftime("%Y-%m-%d %H:00", LogEntryModel.created_at)

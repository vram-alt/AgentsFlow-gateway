"""Сервис логирования — единая точка входа для записи событий в журнал."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.domain.entities.log_entry import EventType


class LogService:
    """Сервис для записи и чтения аудит-логов."""

    def __init__(self, log_repo: Any) -> None:
        self.log_repo = log_repo

    async def log_chat_request(
        self,
        trace_id: str,
        prompt_data: dict[str, Any],
        response_data: dict[str, Any],
        is_error: bool = False,
    ) -> None:
        """Запись события отправки промпта и получения ответа от LLM."""
        payload: dict[str, Any] = {
            "prompt": prompt_data,
            "response": response_data,
            "is_error": is_error,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.log_repo.create(trace_id, EventType.CHAT_REQUEST, payload)
        except Exception as exc:
            logging.error("Failed to log chat request: %s", exc)
        return None

    async def log_guardrail_incident(
        self,
        trace_id: str,
        incident_data: dict[str, Any],
    ) -> None:
        """Запись события срабатывания Guardrail."""
        payload: dict[str, Any] = {
            "incident": incident_data,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.log_repo.create(trace_id, EventType.GUARDRAIL_INCIDENT, payload)
        except Exception as exc:
            logging.error("Failed to log guardrail incident: %s", exc)
        return None

    async def log_system_error(
        self,
        trace_id: str,
        error_data: dict[str, Any],
    ) -> None:
        """Запись системной ошибки."""
        payload: dict[str, Any] = {
            "error": error_data,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.log_repo.create(trace_id, EventType.SYSTEM_ERROR, payload)
        except Exception as exc:
            logging.error("Failed to log system error: %s", exc)
        return None

    async def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        event_type: str | None = None,
    ) -> list[Any]:
        """Получение списка событий для UI-журнала."""
        if event_type is not None:
            return await self.log_repo.list_by_type(event_type, limit, offset)
        return await self.log_repo.list_all(limit, offset)

    async def get_logs_by_trace_id(self, trace_id: str) -> list[Any]:
        """Получение всех событий по trace_id."""
        return await self.log_repo.get_by_trace_id(trace_id)

    async def get_log_stats(self) -> dict[str, int]:
        """Получение статистики для дашборда."""
        total: int = await self.log_repo.count_all()
        chat_requests: int = await self.log_repo.count_by_type(EventType.CHAT_REQUEST)
        guardrail_incidents: int = await self.log_repo.count_by_type(
            EventType.GUARDRAIL_INCIDENT
        )
        system_errors: int = await self.log_repo.count_by_type(EventType.SYSTEM_ERROR)
        return {
            "total": total,
            "chat_requests": chat_requests,
            "guardrail_incidents": guardrail_incidents,
            "system_errors": system_errors,
        }

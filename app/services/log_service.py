"""Сервис логирования — единая точка входа для записи событий в журнал."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from app.domain.entities.log_entry import EventType
from app.infrastructure.database.repositories import LogRepository


class LogService:
    """Сервис для записи и чтения аудит-логов."""

    def __init__(self, log_repo: LogRepository) -> None:
        """[YEL-1] Concrete type instead of Any for dependency injection."""
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

    async def get_stats_summary(self) -> dict[str, Any]:
        """Расширенная статистика для дашборда (upgrade spec §1).

        Включает базовую статистику + агрегированные данные по токенам и latency.
        Два отдельных запроса к БД без единой транзакции — допустимая
        несогласованность для информационного дашборда.
        """
        base_stats = await self.get_log_stats()

        try:
            token_stats = await self.log_repo.aggregate_token_stats()
        except Exception as exc:
            logging.warning("Failed to aggregate token stats: %s", exc)
            token_stats = {"total_tokens": 0, "avg_latency_ms": 0.0}

        return {
            **base_stats,
            "total_tokens": token_stats.get("total_tokens", 0),
            "avg_latency_ms": token_stats.get("avg_latency_ms", 0.0),
        }

    async def get_chart_data(self, hours: int = 24) -> list[dict[str, Any]]:
        """Данные для графика активности — количество событий по часам (upgrade spec §2)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = await self.log_repo.count_by_hour(since=since)
        return [{"hour": row[0], "count": row[1]} for row in rows]

    async def get_log_by_id(self, log_id: int) -> Any:
        """Получение одной записи лога по числовому ID (upgrade spec §3)."""
        return await self.log_repo.get_by_id(log_id)

    async def export_logs(
        self,
        event_type: str | None = None,
        limit: int = 10000,
    ) -> AsyncGenerator[str, None]:
        """Генерация CSV-данных для экспорта логов (upgrade spec §4).

        [SRE_MARKER] CSV Injection защита: префикс одинарной кавычкой
        для значений, начинающихся с =, +, -, @, \\t, \\r.
        """
        logging.info(
            "CSV export started: event_type=%s limit=%s",
            event_type,
            limit,
        )
        count = 0
        yield "id,trace_id,event_type,created_at,payload\n"

        try:
            async for row in self.log_repo.list_for_export(
                event_type=event_type, limit=limit
            ):
                # Serialize payload to string
                if row.payload is None:
                    payload_str = ""
                elif isinstance(row.payload, str):
                    payload_str = row.payload
                else:
                    payload_str = json.dumps(row.payload)

                # CSV Injection защита: проверяем начало строки
                _dangerous_chars = ("=", "+", "-", "@", "\t", "\r")
                if payload_str and payload_str[0] in _dangerous_chars:
                    payload_str = "'" + payload_str

                # Также защищаем от формул внутри JSON-значений:
                # заменяем опасные символы в начале строковых значений
                for dc in ("=", "+", "@"):
                    payload_str = payload_str.replace(f'"{dc}', f"\"'{dc}")

                # Экранирование для CSV: обернуть в двойные кавычки, удвоить внутренние
                escaped_payload = '"' + payload_str.replace('"', '""') + '"'

                created_at = (
                    row.created_at.isoformat()
                    if hasattr(row.created_at, "isoformat")
                    else str(row.created_at)
                )

                yield f"{row.id},{row.trace_id},{row.event_type},{created_at},{escaped_payload}\n"
                count += 1
        except Exception as exc:
            logging.error("CSV export interrupted: %s", exc)
            yield "# ERROR: export interrupted\n"
            return

        logging.info("CSV export completed: %d records exported", count)

"""Logging service — single entry point for writing events to the audit log."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from app.domain.entities.log_entry import EventType
from app.infrastructure.database.repositories import LogRepository


class LogService:
    """Service for writing and reading audit logs."""

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
        """Record a prompt submission and LLM response event."""
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
        """Record a Guardrail trigger event."""
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
        """Record a system error."""
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
        """Retrieve a list of events for the UI log viewer."""
        if event_type is not None:
            return await self.log_repo.list_by_type(event_type, limit, offset)
        return await self.log_repo.list_all(limit, offset)

    async def get_logs_by_trace_id(self, trace_id: str) -> list[Any]:
        """Retrieve all events by trace_id."""
        return await self.log_repo.get_by_trace_id(trace_id)

    async def get_log_stats(self) -> dict[str, int]:
        """Retrieve statistics for the dashboard."""
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
        """Extended dashboard statistics (upgrade spec §1).

        Returns data matching the frontend StatsSummary interface:
        - total_requests, total_errors, avg_latency_ms, requests_today,
          error_rate, top_models, top_providers
        """
        base_stats = await self.get_log_stats()

        try:
            token_stats = await self.log_repo.aggregate_token_stats()
        except Exception as exc:
            logging.warning("Failed to aggregate token stats: %s", exc)
            token_stats = {"total_tokens": 0, "avg_latency_ms": 0.0}

        total_requests = base_stats.get("chat_requests", 0)
        total_errors = base_stats.get("system_errors", 0)
        error_rate = total_errors / total_requests if total_requests > 0 else 0.0

        # Count today's requests
        try:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_rows = await self.log_repo.count_by_hour(since=today_start)
            requests_today = sum(row[1] for row in today_rows)
        except Exception:
            requests_today = 0

        # Top models and providers from recent logs
        top_models: list[dict[str, Any]] = []
        top_providers: list[dict[str, Any]] = []
        try:
            recent_logs = await self.log_repo.list_by_type(
                EventType.CHAT_REQUEST, limit=500, offset=0
            )
            model_counts: dict[str, int] = {}
            provider_counts: dict[str, int] = {}
            for log in recent_logs:
                payload = log.payload
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if isinstance(payload, dict):
                    prompt = payload.get("prompt", {})
                    if isinstance(prompt, dict):
                        model = prompt.get("model", "unknown")
                        model_counts[model] = model_counts.get(model, 0) + 1
                    prov = payload.get("provider_name", "")
                    if prov:
                        provider_counts[prov] = provider_counts.get(prov, 0) + 1

            top_models = sorted(
                [{"model": k, "count": v} for k, v in model_counts.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:5]
            top_providers = sorted(
                [{"provider": k, "count": v} for k, v in provider_counts.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:5]
        except Exception as exc:
            logging.warning("Failed to compute top models/providers: %s", exc)

        return {
            # Legacy keys (for existing tests and /api/logs/stats compatibility)
            "total": base_stats.get("total", 0),
            "chat_requests": total_requests,
            "guardrail_incidents": base_stats.get("guardrail_incidents", 0),
            "system_errors": total_errors,
            "total_tokens": token_stats.get("total_tokens", 0),
            "avg_latency_ms": token_stats.get("avg_latency_ms", 0.0),
            # Frontend-compatible keys (for StatsSummary interface)
            "total_requests": total_requests,
            "total_errors": total_errors,
            "requests_today": requests_today,
            "error_rate": error_rate,
            "top_models": top_models,
            "top_providers": top_providers,
        }

    async def get_chart_data(self, hours: int = 24) -> list[dict[str, Any]]:
        """Activity chart data — event counts by hour (upgrade spec §2)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = await self.log_repo.count_by_hour(since=since)
        return [{"hour": row[0], "count": row[1]} for row in rows]

    async def get_log_by_id(self, log_id: int) -> Any:
        """Retrieve a single log record by numeric ID (upgrade spec §3)."""
        return await self.log_repo.get_by_id(log_id)

    async def export_logs(
        self,
        event_type: str | None = None,
        limit: int = 10000,
    ) -> AsyncGenerator[str, None]:
        """Generate CSV data for log export (upgrade spec §4).

        [SRE_MARKER] CSV Injection protection: single-quote prefix
        for values starting with =, +, -, @, \\t, \\r.
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

                # CSV Injection protection: check string prefix
                _dangerous_chars = ("=", "+", "-", "@", "\t", "\r")
                if payload_str and payload_str[0] in _dangerous_chars:
                    payload_str = "'" + payload_str

                # Also protect against formulas inside JSON values:
                # replace dangerous characters at the start of string values
                for dc in ("=", "+", "@"):
                    payload_str = payload_str.replace(f'"{dc}', f"\"'{dc}")

                # CSV escaping: wrap in double quotes, double internal quotes
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

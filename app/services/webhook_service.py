"""WebhookService — processing incoming webhook reports from providers."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.database.repositories import LogRepository
from app.services.log_service import LogService

_UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class WebhookService:
    """Service for processing incoming webhook reports about security incidents."""

    def __init__(self, log_service: LogService, log_repo: LogRepository) -> None:
        """[YEL-1] Concrete types instead of Any for dependency injection."""
        self.log_service = log_service
        self.log_repo = log_repo

    async def process_guardrail_incident(
        self, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Process an incoming webhook report about a Guardrail trigger."""

        # §5: Empty or None payload → rejected
        if not payload:
            return {"status": "rejected", "reason": "empty payload"}

        # §4 step 1: Extract trace_id
        trace_id_source = "webhook"
        trace_id = payload.get("trace_id")

        if not trace_id:
            metadata = payload.get("metadata", {})
            trace_id = metadata.get("trace_id") if isinstance(metadata, dict) else None

        if not trace_id:
            trace_id = str(uuid.uuid4())
            trace_id_source = "generated"

        # §4 step 2: Validate trace_id format
        if not _UUID_V4_RE.match(trace_id):
            logging.warning("Invalid trace_id format: %s", trace_id)

        # §4 step 3: Check linkage to original request
        try:
            existing_logs = await self.log_repo.get_by_trace_id(trace_id)
            linked_to_prompt = any(
                getattr(log, "event_type", None) == "chat_request"
                for log in existing_logs
            )
        except Exception as exc:
            logging.error("DB read error during trace lookup: %s", exc)
            return {"status": "error"}

        # §4 step 4: Build incident record
        incident_payload: dict[str, Any] = {
            "original_webhook_body": payload,
            "trace_id_source": trace_id_source,
            "linked_to_prompt": linked_to_prompt,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        # §4 step 5: Write to audit log
        try:
            await self.log_service.log_guardrail_incident(trace_id, incident_payload)
        except Exception as exc:
            logging.error("DB write error during incident logging: %s", exc)
            return {"status": "error"}

        # §4 step 6: Return confirmation
        return {
            "status": "accepted",
            "trace_id": trace_id,
            "linked_to_prompt": linked_to_prompt,
        }

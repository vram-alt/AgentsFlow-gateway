"""
Webhook router — HTTP handler for incoming webhook reports from providers.

Spec: app/api/routes/webhook_spec.md
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings
from app.api.dependencies.di import get_webhook_service
from app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["Webhook"])

MAX_PAYLOAD_SIZE: int = 1 * 1024 * 1024  # 1 MB
MAX_NESTING_DEPTH: int = 10


def _check_nesting_depth(obj: Any, current_depth: int = 0) -> int:
    """Return the maximum nesting depth of a JSON-like structure.

    A flat dict ``{"key": "val"}`` has depth 1.
    ``{"a": {"b": "c"}}`` has depth 2, etc.
    """
    if isinstance(obj, dict):
        if not obj:
            return current_depth + 1
        return max(_check_nesting_depth(v, current_depth + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return current_depth + 1
        return max(_check_nesting_depth(item, current_depth + 1) for item in obj)
    return current_depth


def _require_webhook_secret(request: Request) -> None:
    """Validate the shared X-Webhook-Secret header for custom webhook endpoints."""
    settings = get_settings()
    secret = request.headers.get("x-webhook-secret")
    if not secret or not hmac.compare_digest(
        secret.encode("utf-8"),
        (settings.webhook_secret or "").encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing X-Webhook-Secret"
        )


async def _read_verified_payload(request: Request) -> dict[str, Any]:
    """Authenticate, size-check, and parse a webhook payload."""
    _require_webhook_secret(request)

    content_length_header = request.headers.get("content-length")
    if content_length_header is not None:
        try:
            if int(content_length_header) > MAX_PAYLOAD_SIZE:
                raise HTTPException(status_code=413, detail="Payload Too Large")
        except ValueError:
            pass

    body_bytes = await request.body()
    if len(body_bytes) > MAX_PAYLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Payload Too Large")

    try:
        payload: dict[str, Any] = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Payload must be a JSON object")

    depth = _check_nesting_depth(payload)
    if depth > MAX_NESTING_DEPTH:
        raise HTTPException(
            status_code=422,
            detail=f"JSON nesting depth {depth} exceeds maximum of {MAX_NESTING_DEPTH}",
        )
    return payload


def _extract_trace_id(payload: dict[str, Any]) -> str:
    """Extract a trace_id from webhook payloads or generate a fallback UUID."""
    trace_id = payload.get("trace_id")
    if isinstance(trace_id, str) and trace_id.strip():
        return trace_id

    metadata = payload.get("metadata", {})
    if isinstance(metadata, dict):
        metadata_trace = metadata.get("trace_id")
        if isinstance(metadata_trace, str) and metadata_trace.strip():
            return metadata_trace

    return str(uuid.uuid4())


def _extract_text_from_section(section: Any) -> str:
    """Best-effort text extraction from Portkey webhook request/response sections."""
    if not isinstance(section, dict):
        return ""

    parts: list[str] = []
    direct_text = section.get("text")
    if isinstance(direct_text, str) and direct_text.strip():
        parts.append(direct_text.strip())

    json_body = section.get("json", {})
    if isinstance(json_body, dict):
        messages = json_body.get("messages", [])
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    parts.append(content.strip())
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            text = item.get("text")
                            if isinstance(text, str) and text.strip():
                                parts.append(text.strip())

        input_value = json_body.get("input")
        if isinstance(input_value, str) and input_value.strip():
            parts.append(input_value.strip())

    return "\n".join(part for part in parts if part)


@router.post("")
async def receive_webhook(
    request: Request,
    webhook_service: WebhookService = Depends(get_webhook_service),
) -> dict[str, Any]:
    """
    POST /api/webhook — receive incoming webhook reports.

    Steps:
    1. Validate X-Webhook-Secret header (401).
    2. Check Content-Length / body size (413).
    3. Parse JSON body (422).
    4. Check nesting depth (422).
    5. Call service, return result (200).
    [SRE_MARKER] Service error/rejected status -> still HTTP 200.
    [SRE_MARKER] RuntimeError -> HTTP 500.
    """
    payload = await _read_verified_payload(request)

    # --- 5. Call service ---
    # [SRE_MARKER] RuntimeError -> HTTP 500
    try:
        result = await webhook_service.process_guardrail_incident(payload)
    except RuntimeError as exc:
        logger.error("RuntimeError in webhook service: %s", exc)
        raise HTTPException(status_code=500, detail="Internal Server Error") from exc

    # [SRE_MARKER] Service error/rejected status -> still HTTP 200
    return result


@router.post("/custom/validate")
async def validate_custom_webhook(
    request: Request,
    mode: str = "contains",
    terms: str | None = None,
    pattern: str | None = None,
    target: str = "request",
    webhook_service: WebhookService = Depends(get_webhook_service),
) -> dict[str, Any]:
    """Custom Portkey Webhook endpoint for beginner-friendly validation rules.

    This route is safe-by-default and optional: it does not affect existing
    `/api/webhook` behavior. It lets a user create a Portkey Webhook guardrail
    that validates request/response text using simple contains or regex rules.
    """
    payload = await _read_verified_payload(request)
    trace_id = _extract_trace_id(payload)

    request_text = _extract_text_from_section(payload.get("request", {}))
    response_text = _extract_text_from_section(payload.get("response", {}))

    if target == "response":
        text_to_check = response_text
    elif target == "both":
        text_to_check = "\n".join(part for part in (request_text, response_text) if part)
    else:
        target = "request"
        text_to_check = request_text

    verdict = True
    reason = "No custom validation rule matched"
    matched: list[str] = []

    normalized_mode = mode.strip().lower()
    if normalized_mode == "regex":
        if not pattern:
            raise HTTPException(
                status_code=422,
                detail="Query parameter 'pattern' is required when mode=regex",
            )
        try:
            compiled = re.compile(pattern, flags=re.IGNORECASE)
        except re.error as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid regex pattern: {exc}",
            ) from exc

        regex_match = compiled.search(text_to_check or "")
        if regex_match:
            verdict = False
            matched = [regex_match.group(0)]
            reason = f"Blocked by custom regex rule: {regex_match.group(0)}"
    else:
        blocked_terms = [term.strip() for term in (terms or "").split(",") if term.strip()]
        lowered_text = (text_to_check or "").lower()
        matched = [term for term in blocked_terms if term.lower() in lowered_text]
        if matched:
            verdict = False
            reason = "Blocked by custom contains rule: " + ", ".join(matched[:5])

    try:
        await webhook_service.process_guardrail_incident(
            {
                "trace_id": trace_id,
                "metadata": {
                    "trace_id": trace_id,
                    "custom_guardrail_route": "validate",
                    "mode": normalized_mode,
                    "target": target,
                },
                "custom_guardrail": {
                    "verdict": verdict,
                    "reason": reason,
                    "matched": matched,
                },
                "request": payload.get("request", {}),
                "response": payload.get("response", {}),
                "eventType": "customValidate",
            }
        )
    except RuntimeError as exc:
        logger.warning("Custom webhook validation logging failed: %s", exc)

    return {
        "verdict": verdict,
        "reason": reason,
        "matched": matched,
        "target": target,
        "mode": normalized_mode,
    }


@router.post("/custom/log")
async def receive_custom_log(
    request: Request,
    label: str = "custom-policy-log",
    webhook_service: WebhookService = Depends(get_webhook_service),
) -> dict[str, Any]:
    """Custom Portkey Log endpoint that records payloads into the app audit log."""
    payload = await _read_verified_payload(request)
    trace_id = _extract_trace_id(payload)

    enriched_payload = dict(payload)
    metadata = enriched_payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "trace_id": trace_id,
            "custom_guardrail_route": "log",
            "label": label,
        }
    )
    enriched_payload["metadata"] = metadata
    enriched_payload["trace_id"] = trace_id
    enriched_payload["eventType"] = enriched_payload.get("eventType") or "customLog"

    try:
        await webhook_service.process_guardrail_incident(enriched_payload)
    except RuntimeError as exc:
        logger.error("RuntimeError in custom log webhook service: %s", exc)
        raise HTTPException(status_code=500, detail="Internal Server Error") from exc

    return {
        "status": "logged",
        "trace_id": trace_id,
        "label": label,
        "verdict": True,
    }

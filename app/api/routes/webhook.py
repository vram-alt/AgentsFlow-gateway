"""
Webhook router — HTTP handler for incoming webhook reports from providers.

Spec: app/api/routes/webhook_spec.md
"""

from __future__ import annotations

import hmac
import json
import logging
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
    settings = get_settings()

    # --- 1. Auth: X-Webhook-Secret ---
    # [SRE_MARKER] Timing-safe comparison via hmac.compare_digest
    # [RED-3] Uses the same hmac.compare_digest pattern as middleware auth
    secret = request.headers.get("x-webhook-secret")
    if not secret or not hmac.compare_digest(
        secret.encode("utf-8"),
        (settings.webhook_secret or "").encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing X-Webhook-Secret"
        )

    # --- 2. Payload size check (Content-Length header) ---
    content_length_header = request.headers.get("content-length")
    if content_length_header is not None:
        try:
            if int(content_length_header) > MAX_PAYLOAD_SIZE:
                raise HTTPException(status_code=413, detail="Payload Too Large")
        except ValueError:
            pass

    # --- 2b. Read body and check actual size ---
    body_bytes = await request.body()
    if len(body_bytes) > MAX_PAYLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Payload Too Large")

    # --- 3. Parse JSON ---
    try:
        payload: dict[str, Any] = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Payload must be a JSON object")

    # --- 4. Nesting depth check ---
    depth = _check_nesting_depth(payload)
    if depth > MAX_NESTING_DEPTH:
        raise HTTPException(
            status_code=422,
            detail=f"JSON nesting depth {depth} exceeds maximum of {MAX_NESTING_DEPTH}",
        )

    # --- 5. Call service ---
    # [SRE_MARKER] RuntimeError -> HTTP 500
    try:
        result = await webhook_service.process_guardrail_incident(payload)
    except RuntimeError as exc:
        logger.error("RuntimeError in webhook service: %s", exc)
        raise HTTPException(status_code=500, detail="Internal Server Error") from exc

    # [SRE_MARKER] Service error/rejected status -> still HTTP 200
    return result

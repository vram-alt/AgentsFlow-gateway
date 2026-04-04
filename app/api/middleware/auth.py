"""
HTTP Basic Auth & Webhook Secret dependencies with rate limiting.

Spec: app/api/middleware/middleware_spec.md

[RED-2] WARNING: The in-memory rate limiter below uses per-process dict storage.
It does NOT work correctly in multi-worker deployments (e.g., gunicorn with
multiple uvicorn workers). Each worker maintains its own independent counter,
so an attacker can distribute brute-force attempts across workers.
For production, replace with a shared store such as Redis + sliding-window
algorithm. This is acceptable for the current single-worker POC.
"""

from __future__ import annotations

import hmac
import os
import time

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

# ---------------------------------------------------------------------------
# In-memory rate limiter state
# ---------------------------------------------------------------------------
# [RED-2] WARNING: This in-memory rate limiter is NOT multi-worker safe.
# In a multi-worker deployment (gunicorn -w N), each worker has its own
# _failed_attempts dict. An attacker can bypass the limit by distributing
# requests across workers. For production, use Redis-backed rate limiting.
# Module-level dict exposed for test fixture compatibility (_reset_rate_limiter).
# Key: client IP (str) → Value: dict with "count" (int) and "first_failure" (float)
_failed_attempts: dict[str, dict[str, float | int]] = {}

_MAX_FAILURES = 5
_WINDOW_SECONDS = 60


def _get_limiter(request: Request) -> dict[str, dict[str, float | int]]:
    """Return the per-app rate limiter dict, creating it lazily on app state.

    Each FastAPI app instance gets its own rate limiter storage.
    This ensures test isolation when each test creates a new app.
    """
    app_state = request.app.state
    if not hasattr(app_state, "_failed_attempts"):
        app_state._failed_attempts: dict[str, dict[str, float | int]] = {}
    return app_state._failed_attempts  # type: ignore[return-value]


def _get_client_ip(request: Request) -> str:
    """Extract client IP from the request."""
    if request.client is not None:
        return request.client.host
    return "unknown"


def _check_rate_limit(request: Request, client_ip: str) -> None:
    """
    Check if the client IP has exceeded the rate limit.
    Raises HTTP 429 if blocked. Must be called BEFORE credential validation.
    """
    limiter = _get_limiter(request)
    record = limiter.get(client_ip)
    if record is None:
        return

    now = time.time()
    first_failure = float(record["first_failure"])

    # TTL expired — clear the record
    if now - first_failure >= _WINDOW_SECONDS:
        limiter.pop(client_ip, None)
        return

    if int(record["count"]) >= _MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later.",
        )


def _record_failure(request: Request, client_ip: str) -> None:
    """Record a failed authentication attempt for the given IP."""
    limiter = _get_limiter(request)
    now = time.time()
    record = limiter.get(client_ip)

    if record is None:
        limiter[client_ip] = {"count": 1, "first_failure": now}
        return

    first_failure = float(record["first_failure"])
    # If the window has expired, start a new window
    if now - first_failure >= _WINDOW_SECONDS:
        limiter[client_ip] = {"count": 1, "first_failure": now}
    else:
        record["count"] = int(record["count"]) + 1


def _reset_failures(request: Request, client_ip: str) -> None:
    """Reset the failure counter for the given IP on successful auth."""
    limiter = _get_limiter(request)
    limiter.pop(client_ip, None)


# ---------------------------------------------------------------------------
# verify_basic_auth
# ---------------------------------------------------------------------------


def verify_basic_auth(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Validate HTTP Basic credentials and return username.

    [SRE_MARKER] Uses hmac.compare_digest for timing-attack resistance.
    [SRE_MARKER] Applies in-memory rate limiting for brute-force protection.
    """
    client_ip = _get_client_ip(request)

    # Rate limit check BEFORE credential validation
    _check_rate_limit(request, client_ip)

    expected_username = os.environ.get("ADMIN_USERNAME", "")
    expected_password = os.environ.get("ADMIN_PASSWORD", "")

    username_correct = hmac.compare_digest(
        credentials.username.encode("utf-8"),
        expected_username.encode("utf-8"),
    )
    password_correct = hmac.compare_digest(
        credentials.password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )

    if username_correct and password_correct:
        _reset_failures(request, client_ip)
        return credentials.username

    _record_failure(request, client_ip)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


# ---------------------------------------------------------------------------
# verify_webhook_secret
# ---------------------------------------------------------------------------


def verify_webhook_secret(
    request: Request,
    x_webhook_secret: str = Header(...),
) -> bool:
    """Validate the X-Webhook-Secret header.

    [SRE_MARKER] Uses hmac.compare_digest for timing-attack resistance.
    [SRE_MARKER] Applies in-memory rate limiting for brute-force protection.
    """
    client_ip = _get_client_ip(request)

    # Rate limit check BEFORE credential validation
    _check_rate_limit(request, client_ip)

    expected_secret = os.environ.get("WEBHOOK_SECRET", "")

    if hmac.compare_digest(
        x_webhook_secret.encode("utf-8"),
        expected_secret.encode("utf-8"),
    ):
        _reset_failures(request, client_ip)
        return True

    _record_failure(request, client_ip)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid webhook secret",
    )


# ---------------------------------------------------------------------------
# get_current_user — реальная FastAPI-зависимость, делегирующая verify_basic_auth
# ---------------------------------------------------------------------------


def get_current_user(
    username: str = Depends(verify_basic_auth),
) -> str:
    """FastAPI dependency that delegates to verify_basic_auth.

    Returns the authenticated username.
    """
    return username

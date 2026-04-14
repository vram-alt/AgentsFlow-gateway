"""
FastAPI dependency injection providers.

Spec: app/api/dependencies/dependencies_spec.md

[SRE_MARKER]: Fail-fast DATABASE_URL validation in repository factories.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Pre-load session.py — if the module is not loaded, patch() in tests
# cannot resolve it. Import errors are suppressed (SRE: session.py
# validates DATABASE_URL itself and raises ValueError).
import sys as _sys
import types as _types

try:
    import app.infrastructure.database.session as _session_mod  # noqa: F401

    from app.infrastructure.database.session import get_db_session
except (ValueError, RuntimeError, TypeError):
    # [RED-4] Narrowed from `except Exception` to specific expected errors:
    #   - ValueError: invalid DATABASE_URL configuration
    #   - RuntimeError: missing runtime dependencies
    #   - TypeError: SQLAlchemy engine kwargs mismatch (e.g. pool_size with SQLite/NullPool)
    # Critical errors like ImportError, SyntaxError, ModuleNotFoundError will now
    # propagate immediately instead of being silently swallowed.
    _mod_name = "app.infrastructure.database.session"
    if _mod_name not in _sys.modules:
        _stub = _types.ModuleType(_mod_name)
        _stub.get_settings = None  # type: ignore[attr-defined]
        _stub.get_db_session = None  # type: ignore[attr-defined]
        _sys.modules[_mod_name] = _stub

    # Fallback: define a no-op get_db_session so Depends(...) doesn't fail at import
    async def get_db_session():  # type: ignore[no-redef]
        yield None  # type: ignore[misc]


import httpx
from fastapi import HTTPException

from app.domain.contracts.gateway_provider import GatewayProvider
from app.infrastructure.adapters.portkey_adapter import PortkeyAdapter
from app.infrastructure.database.repositories import (
    LogRepository,
    PolicyRepository,
    ProviderRepository,
)
from app.services.chat_service import ChatService
from app.services.config_service import ConfigService
from app.services.log_service import LogService
from app.services.policy_service import PolicyService
from app.services.provider_service import ProviderService
from app.services.tester_service import TesterService
from app.services.webhook_service import WebhookService

# ── Adapter singleton (stateless, §2.4) ──────────────────────────────
_adapter_instance: PortkeyAdapter | None = None

# ── Isolated HTTP client singleton for TesterService (§4) ──────
_tester_http_client: httpx.AsyncClient | None = None


def _validate_database_url() -> None:
    """[SRE_MARKER] Fail-fast: validate DATABASE_URL before creating dependencies.

    If the variable is explicitly set in the environment but empty or missing the '://' scheme,
    raises ValueError with an informative message.
    If the variable is absent from os.environ — skip (pydantic-settings
    will load from the .env file).
    """
    if "DATABASE_URL" not in os.environ:
        return  # not explicitly set — pydantic-settings will load from .env
    database_url = os.environ["DATABASE_URL"]
    if not database_url or not database_url.strip():
        raise ValueError(
            "DATABASE_URL is empty or missing — "
            "database connection URL must be configured"
        )
    if "://" not in database_url:
        raise ValueError(
            f"Invalid DATABASE_URL: {database_url!r} — "
            "database connection URL must contain a scheme (e.g. sqlite+aiosqlite://)"
        )


# ======================================================================
# §2.1 — Factory: get_provider_repo
# ======================================================================


def get_provider_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ProviderRepository:
    """Create a ProviderRepository with the provided DB session.

    [SRE_MARKER]: Validates DATABASE_URL before creation.
    """
    _validate_database_url()
    return ProviderRepository(session=session)


# ======================================================================
# §2.2 — Factory: get_policy_repo
# ======================================================================


def get_policy_repo(
    session: AsyncSession = Depends(get_db_session),
) -> PolicyRepository:
    """Create a PolicyRepository with the provided DB session."""
    _validate_database_url()
    return PolicyRepository(session=session)


# ======================================================================
# §2.3 — Factory: get_log_repo
# ======================================================================


def get_log_repo(session: AsyncSession = Depends(get_db_session)) -> LogRepository:
    """Create a LogRepository with the provided DB session."""
    _validate_database_url()
    return LogRepository(session=session)


# ======================================================================
# §2.4 — Factory: get_adapter (stateless singleton)
# ======================================================================


def get_adapter() -> GatewayProvider:
    """Return the PortkeyAdapter singleton.

    Spec §2.4: adapter is stateless, reused across requests.
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = PortkeyAdapter()
    return _adapter_instance


# ======================================================================
# §2.5 — Factory: get_log_service
# ======================================================================


def get_log_service(
    log_repo: LogRepository = Depends(get_log_repo),
) -> LogService:
    """Create a LogService with LogRepository (from get_log_repo).

    Spec §2.5: dependency — LogRepository (from get_log_repo).
    When called directly without arguments (unit tests) — creates LogRepository
    with session=None for compatibility.
    """
    if not isinstance(log_repo, LogRepository):
        log_repo = LogRepository(session=None)  # type: ignore[arg-type]
    return LogService(log_repo=log_repo)


# ======================================================================
# §2.6 — Factory: get_chat_service
# ======================================================================


def get_chat_service(
    provider_repo: ProviderRepository = Depends(get_provider_repo),
    policy_repo: PolicyRepository = Depends(get_policy_repo),
    log_service: LogService = Depends(get_log_service),
    adapter: GatewayProvider = Depends(get_adapter),
) -> ChatService:
    """Create a ChatService with ProviderRepository, PolicyRepository, LogService, and GatewayProvider.

    Spec §2.6: dependencies — ProviderRepository (from get_provider_repo),
    PolicyRepository (from get_policy_repo), LogService (from get_log_service),
    GatewayProvider (from get_adapter).
    """
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(policy_repo, PolicyRepository):
        policy_repo = PolicyRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(log_service, LogService):
        log_service = get_log_service()
    if not isinstance(adapter, GatewayProvider):
        adapter = get_adapter()
    return ChatService(
        provider_repo=provider_repo,
        policy_repo=policy_repo,
        log_service=log_service,
        adapter=adapter,
    )


# ======================================================================
# §2.7 — Factory: get_policy_service
# ======================================================================


def get_policy_service(
    policy_repo: PolicyRepository = Depends(get_policy_repo),
    provider_repo: ProviderRepository = Depends(get_provider_repo),
    log_service: LogService = Depends(get_log_service),
    adapter: GatewayProvider = Depends(get_adapter),
) -> PolicyService:
    """Create a PolicyService with PolicyRepository, ProviderRepository, LogService, GatewayProvider.

    Spec §2.7: dependencies — PolicyRepository (from get_policy_repo),
    ProviderRepository (from get_provider_repo), LogService (from get_log_service),
    GatewayProvider (from get_adapter).
    """
    if not isinstance(policy_repo, PolicyRepository):
        policy_repo = PolicyRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(log_service, LogService):
        log_service = get_log_service()
    if not isinstance(adapter, GatewayProvider):
        adapter = get_adapter()
    return PolicyService(
        policy_repo=policy_repo,
        provider_repo=provider_repo,
        adapter=adapter,
        log_service=log_service,
    )


# ======================================================================
# Factory: get_config_service
# ======================================================================


def get_config_service(
    provider_repo: ProviderRepository = Depends(get_provider_repo),
    adapter: GatewayProvider = Depends(get_adapter),
) -> ConfigService:
    """Create a ConfigService with ProviderRepository and GatewayProvider."""
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(adapter, GatewayProvider):
        adapter = get_adapter()
    return ConfigService(provider_repo=provider_repo, adapter=adapter)


# ======================================================================
# §2.8 — Factory: get_webhook_service
# ======================================================================


def get_webhook_service(
    log_service: LogService = Depends(get_log_service),
    log_repo: LogRepository = Depends(get_log_repo),
) -> WebhookService:
    """Create a WebhookService with LogService and LogRepository.

    Spec §2.8: dependencies — LogService (from get_log_service),
    LogRepository (from get_log_repo).
    """
    if not isinstance(log_repo, LogRepository):
        log_repo = LogRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(log_service, LogService):
        log_service = get_log_service(log_repo=log_repo)
    return WebhookService(log_service=log_service, log_repo=log_repo)


# ======================================================================
# get_provider_service (additional factory)
# ======================================================================


def get_provider_service(
    provider_repo: ProviderRepository = Depends(get_provider_repo),
) -> ProviderService:
    """Create a ProviderService with ProviderRepository.

    Used for CRUD operations on providers.
    """
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    return ProviderService(provider_repo=provider_repo)


# ======================================================================
# [UPGRADE] §3 — get_http_client (dependencies_upgrade_spec.md)
# ======================================================================


def get_http_client() -> httpx.AsyncClient:
    """Provide the reusable httpx.AsyncClient from the adapter.

    [SRE_MARKER] If adapter is None → HTTP 503 'Service not ready'.
    """
    adapter = get_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return adapter.get_http_client()


# ======================================================================
# [UPGRADE] §4 — get_tester_http_client (dependencies_upgrade_spec.md)
# ======================================================================


def get_tester_http_client() -> httpx.AsyncClient:
    """Provide an isolated httpx.AsyncClient for TesterService.

    [SRE_MARKER] Isolated connection pool to prevent cascading failures.
    If adapter is None → HTTP 503 'Service not ready'.
    """
    global _tester_http_client
    adapter = get_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    if _tester_http_client is None:
        try:
            from app.config import get_settings

            timeout = get_settings().external_http_timeout
        except Exception:
            timeout = 30
        _tester_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=10),
        )
    return _tester_http_client


# ======================================================================
# [UPGRADE] §1 — get_tester_service (dependencies_upgrade_spec.md)
# ======================================================================


def get_tester_service(
    provider_repo: ProviderRepository = Depends(get_provider_repo),
    http_client: httpx.AsyncClient = Depends(get_tester_http_client),
) -> TesterService:
    """Create a TesterService with ProviderRepository and httpx.AsyncClient.

    Spec upgrade §1: dependencies — ProviderRepository (from get_provider_repo),
    httpx.AsyncClient (from get_tester_http_client).
    """
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(http_client, httpx.AsyncClient):
        http_client = get_tester_http_client()
    return TesterService(provider_repo=provider_repo, http_client=http_client)

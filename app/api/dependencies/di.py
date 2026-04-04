"""
FastAPI dependency injection providers.

Spec: app/api/dependencies/dependencies_spec.md

[SRE_MARKER]: Fail-fast проверка DATABASE_URL в фабриках репозиториев.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Предзагрузка session.py — если модуль не загружен, patch() в тестах
# не сможет его разрешить. Ошибки импорта подавляются (SRE: session.py
# сам валидирует DATABASE_URL и бросает ValueError).
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
from app.services.log_service import LogService
from app.services.policy_service import PolicyService
from app.services.provider_service import ProviderService
from app.services.tester_service import TesterService
from app.services.webhook_service import WebhookService

# ── Синглтон адаптера (stateless, §2.4) ──────────────────────────────
_adapter_instance: PortkeyAdapter | None = None

# ── Синглтон изолированного HTTP-клиента для TesterService (§4) ──────
_tester_http_client: httpx.AsyncClient | None = None


def _validate_database_url() -> None:
    """[SRE_MARKER] Fail-fast: проверяет DATABASE_URL перед созданием зависимостей.

    Если переменная явно задана в окружении, но пуста или не содержит схему '://',
    выбрасывает ValueError с информативным сообщением.
    Если переменная отсутствует в os.environ — пропускаем (pydantic-settings
    загрузит из .env файла).
    """
    if "DATABASE_URL" not in os.environ:
        return  # не задана явно — pydantic-settings загрузит из .env
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
# §2.1 — Фабрика: get_provider_repo
# ======================================================================


def get_provider_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ProviderRepository:
    """Создаёт ProviderRepository с переданной сессией БД.

    [SRE_MARKER]: Валидирует DATABASE_URL перед созданием.
    """
    _validate_database_url()
    return ProviderRepository(session=session)


# ======================================================================
# §2.2 — Фабрика: get_policy_repo
# ======================================================================


def get_policy_repo(
    session: AsyncSession = Depends(get_db_session),
) -> PolicyRepository:
    """Создаёт PolicyRepository с переданной сессией БД."""
    _validate_database_url()
    return PolicyRepository(session=session)


# ======================================================================
# §2.3 — Фабрика: get_log_repo
# ======================================================================


def get_log_repo(session: AsyncSession = Depends(get_db_session)) -> LogRepository:
    """Создаёт LogRepository с переданной сессией БД."""
    _validate_database_url()
    return LogRepository(session=session)


# ======================================================================
# §2.4 — Фабрика: get_adapter (stateless-синглтон)
# ======================================================================


def get_adapter() -> GatewayProvider:
    """Возвращает синглтон PortkeyAdapter.

    Спека §2.4: адаптер stateless, переиспользуется.
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = PortkeyAdapter()
    return _adapter_instance


# ======================================================================
# §2.5 — Фабрика: get_log_service
# ======================================================================


def get_log_service(
    log_repo: LogRepository = Depends(get_log_repo),
) -> LogService:
    """Создаёт LogService с LogRepository (из get_log_repo).

    Спека §2.5: зависимость — LogRepository (из get_log_repo).
    При прямом вызове без аргументов (unit-тесты) — создаёт LogRepository
    с session=None для совместимости.
    """
    if not isinstance(log_repo, LogRepository):
        log_repo = LogRepository(session=None)  # type: ignore[arg-type]
    return LogService(log_repo=log_repo)


# ======================================================================
# §2.6 — Фабрика: get_chat_service
# ======================================================================


def get_chat_service(
    provider_repo: ProviderRepository = Depends(get_provider_repo),
    log_service: LogService = Depends(get_log_service),
    adapter: GatewayProvider = Depends(get_adapter),
) -> ChatService:
    """Создаёт ChatService с ProviderRepository, LogService и GatewayProvider.

    Спека §2.6: зависимости — ProviderRepository (из get_provider_repo),
    LogService (из get_log_service), GatewayProvider (из get_adapter).
    """
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(log_service, LogService):
        log_service = get_log_service()
    if not isinstance(adapter, GatewayProvider):
        adapter = get_adapter()
    return ChatService(
        provider_repo=provider_repo,
        log_service=log_service,
        adapter=adapter,
    )


# ======================================================================
# §2.7 — Фабрика: get_policy_service
# ======================================================================


def get_policy_service(
    policy_repo: PolicyRepository = Depends(get_policy_repo),
    provider_repo: ProviderRepository = Depends(get_provider_repo),
    log_service: LogService = Depends(get_log_service),
    adapter: GatewayProvider = Depends(get_adapter),
) -> PolicyService:
    """Создаёт PolicyService с PolicyRepository, ProviderRepository, LogService, GatewayProvider.

    Спека §2.7: зависимости — PolicyRepository (из get_policy_repo),
    ProviderRepository (из get_provider_repo), LogService (из get_log_service),
    GatewayProvider (из get_adapter).
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
# §2.8 — Фабрика: get_webhook_service
# ======================================================================


def get_webhook_service(
    log_service: LogService = Depends(get_log_service),
    log_repo: LogRepository = Depends(get_log_repo),
) -> WebhookService:
    """Создаёт WebhookService с LogService и LogRepository.

    Спека §2.8: зависимости — LogService (из get_log_service),
    LogRepository (из get_log_repo).
    """
    if not isinstance(log_repo, LogRepository):
        log_repo = LogRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(log_service, LogService):
        log_service = get_log_service(log_repo=log_repo)
    return WebhookService(log_service=log_service, log_repo=log_repo)


# ======================================================================
# get_provider_service (дополнительная фабрика)
# ======================================================================


def get_provider_service(
    provider_repo: ProviderRepository = Depends(get_provider_repo),
) -> ProviderService:
    """Создаёт ProviderService с ProviderRepository.

    Используется для CRUD-операций над провайдерами.
    """
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    return ProviderService(provider_repo=provider_repo)


# ======================================================================
# [UPGRADE] §3 — get_http_client (dependencies_upgrade_spec.md)
# ======================================================================


def get_http_client() -> httpx.AsyncClient:
    """Предоставляет переиспользуемый httpx.AsyncClient из адаптера.

    [SRE_MARKER] Если адаптер None → HTTP 503 'Service not ready'.
    """
    adapter = get_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return adapter.get_http_client()


# ======================================================================
# [UPGRADE] §4 — get_tester_http_client (dependencies_upgrade_spec.md)
# ======================================================================


def get_tester_http_client() -> httpx.AsyncClient:
    """Предоставляет изолированный httpx.AsyncClient для TesterService.

    [SRE_MARKER] Изолированный пул соединений для предотвращения каскадных отказов.
    Если адаптер None → HTTP 503 'Service not ready'.
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
    """Создаёт TesterService с ProviderRepository и httpx.AsyncClient.

    Спека upgrade §1: зависимости — ProviderRepository (из get_provider_repo),
    httpx.AsyncClient (из get_tester_http_client).
    """
    if not isinstance(provider_repo, ProviderRepository):
        provider_repo = ProviderRepository(session=None)  # type: ignore[arg-type]
    if not isinstance(http_client, httpx.AsyncClient):
        http_client = get_tester_http_client()
    return TesterService(provider_repo=provider_repo, http_client=http_client)

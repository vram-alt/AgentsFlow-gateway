"""
ProviderService — LLM provider management service.
Wrapper over ProviderRepository for CRUD operations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

import httpx

from app.domain.utils.network import _is_private_ip
from app.infrastructure.database.models import ProviderModel
from app.infrastructure.database.repositories import ProviderRepository

logger = logging.getLogger(__name__)


class ProviderService:
    """Provider management service — wrapper over ProviderRepository."""

    def __init__(self, provider_repo: ProviderRepository) -> None:
        self.provider_repo = provider_repo

    async def list_providers(self, only_active: bool = True) -> Sequence[ProviderModel]:
        """List all providers."""
        return await self.provider_repo.list_all(only_active=only_active)

    async def create_provider(
        self,
        name: str,
        api_key: str,
        base_url: str,
    ) -> ProviderModel:
        """Create a new provider."""
        return await self.provider_repo.create(
            name=name,
            api_key=api_key,
            base_url=base_url,
        )

    async def update_provider(
        self,
        provider_id: int,
        name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> ProviderModel | None:
        """Update a provider."""
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if api_key is not None:
            fields["api_key"] = api_key
        if base_url is not None:
            fields["base_url"] = base_url
        return await self.provider_repo.update(provider_id, **fields)

    async def delete_provider(self, provider_id: int) -> bool:
        """Soft delete a provider."""
        return await self.provider_repo.soft_delete(provider_id)

    async def toggle_active(self, provider_id: int) -> ProviderModel | None:
        """Toggle is_active status of a provider."""
        return await self.provider_repo.toggle_active(provider_id)

    async def check_health(
        self, http_client: httpx.AsyncClient
    ) -> list[dict[str, Any]]:
        """Health check for all active providers (upgrade spec §1)."""
        providers = await self.provider_repo.list_all(only_active=True)
        logger.info("Starting health check for %d providers", len(providers))

        results: list[dict[str, Any]] = []

        async def _check_one(provider: Any) -> dict[str, Any]:
            parsed = urlparse(provider.base_url)
            hostname = parsed.hostname or ""

            # [RED-3] SSRF validation with DNS rebinding protection
            if _is_private_ip(hostname):
                logger.warning(
                    "Private IP detected in base_url for provider %s",
                    provider.name,
                )
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "base_url_masked": f"{parsed.scheme}://{parsed.hostname}",
                    "is_active": True,
                    "status": "error",
                    "response_time_ms": None,
                }

            masked_url = f"{parsed.scheme}://{parsed.hostname}"
            start = time.monotonic()
            try:
                await http_client.request("HEAD", provider.base_url, timeout=5.0)
                elapsed = round((time.monotonic() - start) * 1000, 2)
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "base_url_masked": masked_url,
                    "is_active": True,
                    "status": "healthy",
                    "response_time_ms": elapsed,
                }
            except httpx.TimeoutException:
                logger.warning("Health check timeout for provider %s", provider.name)
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "base_url_masked": masked_url,
                    "is_active": True,
                    "status": "timeout",
                    "response_time_ms": None,
                }
            except httpx.ConnectError:
                logger.warning(
                    "Health check unreachable for provider %s", provider.name
                )
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "base_url_masked": masked_url,
                    "is_active": True,
                    "status": "unreachable",
                    "response_time_ms": None,
                }
            except Exception as exc:
                logger.warning(
                    "Health check error for provider %s: %s", provider.name, exc
                )
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "base_url_masked": masked_url,
                    "is_active": True,
                    "status": "error",
                    "response_time_ms": None,
                }

        try:
            tasks = [_check_one(p) for p in providers]
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=False),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            # All unfinished providers get timeout status
            logger.warning("Overall health check timeout exceeded")

        healthy = sum(1 for r in results if r.get("status") == "healthy")
        unhealthy = len(results) - healthy
        logger.info(
            "Health check completed: %d healthy, %d unhealthy", healthy, unhealthy
        )

        return results

"""
ConfigService — Portkey Config management service.
Proxies CRUD operations to the Portkey Configs API via the adapter.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Union

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.infrastructure.database.repositories import ProviderRepository

logger = logging.getLogger(__name__)

_ERROR_CODE_STATUS: dict[str, int] = {
    "AUTH_FAILED": 424,
    "VALIDATION_ERROR": 400,
    "RATE_LIMITED": 429,
    "TIMEOUT": 504,
    "PROVIDER_ERROR": 502,
    "UNKNOWN": 500,
}


def _make_error(error_code: str, message: str) -> GatewayError:
    return GatewayError(
        trace_id=str(uuid.uuid4()),
        error_code=error_code,
        message=message,
        status_code=_ERROR_CODE_STATUS.get(error_code, 500),
    )


class ConfigService:
    """Service for managing Portkey configs (cloud-only, no local DB)."""

    def __init__(
        self,
        provider_repo: ProviderRepository,
        adapter: GatewayProvider,
    ) -> None:
        self._provider_repo = provider_repo
        self._adapter = adapter

    async def _get_provider_credentials(
        self, provider_name: str = "portkey"
    ) -> tuple[str, str] | GatewayError:
        """Look up the active provider's api_key and base_url."""
        provider = await self._provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return _make_error(
                "AUTH_FAILED",
                f"Provider '{provider_name}' not found or is inactive. "
                "Configure it in Configuration → Providers first.",
            )
        return provider.api_key, provider.base_url

    # ── Config CRUD ──────────────────────────────────────────────────

    async def create_config(
        self,
        name: str,
        config_body: dict[str, Any],
        is_default: int = 0,
        provider_name: str = "portkey",
    ) -> Union[dict, GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds

        payload: dict[str, Any] = {
            "name": name,
            "config": config_body,
        }
        if is_default:
            payload["isDefault"] = is_default

        result = await self._adapter.create_config(payload, api_key, base_url)
        if isinstance(result, GatewayError):
            return result

        logger.info("Config created: id=%s", result.get("id"))
        return result

    async def list_configs(
        self, provider_name: str = "portkey"
    ) -> Union[list[dict], GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds
        return await self._adapter.list_configs(api_key, base_url)

    async def retrieve_config(
        self, slug: str, provider_name: str = "portkey"
    ) -> Union[dict, GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds
        return await self._adapter.retrieve_config(slug, api_key, base_url)

    async def update_config(
        self,
        slug: str,
        name: str | None = None,
        config_body: dict[str, Any] | None = None,
        status: str | None = None,
        provider_name: str = "portkey",
    ) -> Union[dict, GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if config_body is not None:
            payload["config"] = config_body
        if status is not None:
            payload["status"] = status

        if not payload:
            return _make_error("VALIDATION_ERROR", "No fields to update")

        result = await self._adapter.update_config(slug, payload, api_key, base_url)
        if isinstance(result, GatewayError):
            return result

        logger.info("Config updated: slug=%s", slug)
        return result

    async def delete_config(
        self, slug: str, provider_name: str = "portkey"
    ) -> Union[bool, GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds

        result = await self._adapter.delete_config(slug, api_key, base_url)
        if isinstance(result, GatewayError):
            return result

        logger.info("Config deleted: slug=%s", slug)
        return result

    async def toggle_config(
        self, slug: str, provider_name: str = "portkey"
    ) -> Union[dict, GatewayError]:
        """Toggle config status between active and inactive."""
        # First retrieve current config to determine status
        current = await self.retrieve_config(slug, provider_name)
        if isinstance(current, GatewayError):
            return current

        current_status = current.get("status", "active")
        new_status = "inactive" if current_status == "active" else "active"

        return await self.update_config(
            slug=slug, status=new_status, provider_name=provider_name
        )

    # ── Guardrails (for config UI selection) ─────────────────────────

    async def list_guardrails(
        self, provider_name: str = "portkey"
    ) -> Union[list[dict], GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds
        return await self._adapter.list_guardrails(api_key, base_url)

    # ── Integrations ─────────────────────────────────────────────────

    async def list_integrations(
        self, provider_name: str = "portkey"
    ) -> Union[list[dict], GatewayError]:
        creds = await self._get_provider_credentials(provider_name)
        if isinstance(creds, GatewayError):
            return creds
        api_key, base_url = creds
        return await self._adapter.list_integrations(api_key, base_url)

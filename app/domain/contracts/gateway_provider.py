"""Abstract GatewayProvider contract — interface for LLM provider adapters."""

from __future__ import annotations

import abc
from typing import Union

import httpx

from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse


class GatewayProvider(abc.ABC):
    """Base contract that every external LLM provider adapter must implement."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Unique provider name (e.g., 'portkey')."""

    @abc.abstractmethod
    async def send_prompt(
        self, prompt: UnifiedPrompt, api_key: str, base_url: str
    ) -> Union[UnifiedResponse, GatewayError]:
        """Send a request to the LLM provider."""

    @abc.abstractmethod
    async def create_guardrail(
        self, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Create a security policy (Guardrail) on the provider side."""

    @abc.abstractmethod
    async def update_guardrail(
        self, remote_id: str, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Update an existing security policy."""

    @abc.abstractmethod
    async def delete_guardrail(
        self, remote_id: str, api_key: str, base_url: str
    ) -> Union[bool, GatewayError]:
        """Delete a security policy on the provider side."""

    @abc.abstractmethod
    async def list_guardrails(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        """Retrieve the list of all security policies from the provider."""

    # ── Config CRUD ──────────────────────────────────────────────────

    @abc.abstractmethod
    async def create_config(
        self, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Create a config on the provider side."""

    @abc.abstractmethod
    async def list_configs(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        """List all configs from the provider."""

    @abc.abstractmethod
    async def retrieve_config(
        self, slug: str, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Retrieve a single config by slug."""

    @abc.abstractmethod
    async def update_config(
        self, slug: str, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Update an existing config."""

    @abc.abstractmethod
    async def delete_config(
        self, slug: str, api_key: str, base_url: str
    ) -> Union[bool, GatewayError]:
        """Delete a config on the provider side."""

    # ── Integrations ─────────────────────────────────────────────────

    @abc.abstractmethod
    async def list_integrations(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        """List LLM integrations from the provider."""

    # [GRN] Non-abstract methods with default implementations.
    # Concrete adapters SHOULD override these for proper resource management.
    # Not abstract to preserve backward compatibility with existing adapters.

    async def close(self) -> None:
        """Gracefully close the reusable HTTP client.

        Must be called during application shutdown to release resources.
        Default: no-op. Adapters with persistent connections should override.
        """

    def get_http_client(self) -> httpx.AsyncClient:
        """Return the reusable httpx.AsyncClient.

        Used by DI layer to share the HTTP client with other components.
        Default: creates a new client. Adapters should override for reuse.
        """
        return httpx.AsyncClient()

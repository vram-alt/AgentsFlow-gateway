"""
ProviderService — сервис управления провайдерами LLM.
Обёртка над ProviderRepository для CRUD-операций.
"""

from __future__ import annotations

from typing import Any


class ProviderService:
    """Сервис управления провайдерами — обёртка над ProviderRepository."""

    def __init__(self, provider_repo: Any) -> None:
        self.provider_repo = provider_repo

    async def list_providers(self, only_active: bool = True) -> Any:
        """Список всех провайдеров."""
        return await self.provider_repo.list_all(only_active=only_active)

    async def create_provider(
        self,
        name: str,
        api_key: str,
        base_url: str,
    ) -> Any:
        """Создание нового провайдера."""
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
    ) -> Any:
        """Обновление провайдера."""
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if api_key is not None:
            fields["api_key"] = api_key
        if base_url is not None:
            fields["base_url"] = base_url
        return await self.provider_repo.update(provider_id, **fields)

    async def delete_provider(self, provider_id: int) -> Any:
        """Soft delete провайдера."""
        return await self.provider_repo.soft_delete(provider_id)

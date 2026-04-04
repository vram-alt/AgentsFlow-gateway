"""Абстрактный контракт GatewayProvider — интерфейс для адаптеров LLM-провайдеров."""

from __future__ import annotations

import abc
from typing import Union

import httpx

from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse


class GatewayProvider(abc.ABC):
    """Базовый контракт для каждого адаптера внешнего LLM-провайдера."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Уникальное имя провайдера (например, 'portkey')."""

    @abc.abstractmethod
    async def send_prompt(
        self, prompt: UnifiedPrompt, api_key: str, base_url: str
    ) -> Union[UnifiedResponse, GatewayError]:
        """Отправка запроса к LLM-провайдеру."""

    @abc.abstractmethod
    async def create_guardrail(
        self, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Создание политики безопасности (Guardrail) на стороне провайдера."""

    @abc.abstractmethod
    async def update_guardrail(
        self, remote_id: str, config: dict, api_key: str, base_url: str
    ) -> Union[dict, GatewayError]:
        """Обновление существующей политики безопасности."""

    @abc.abstractmethod
    async def delete_guardrail(
        self, remote_id: str, api_key: str, base_url: str
    ) -> Union[bool, GatewayError]:
        """Удаление политики безопасности на стороне провайдера."""

    @abc.abstractmethod
    async def list_guardrails(
        self, api_key: str, base_url: str
    ) -> Union[list[dict], GatewayError]:
        """Получение списка всех политик безопасности от провайдера."""

    # [GRN] Non-abstract methods with default implementations.
    # Concrete adapters SHOULD override these for proper resource management.
    # Not abstract to preserve backward compatibility with existing adapters.

    async def close(self) -> None:
        """Корректно закрывает переиспользуемый HTTP-клиент.

        Must be called during application shutdown to release resources.
        Default: no-op. Adapters with persistent connections should override.
        """

    def get_http_client(self) -> httpx.AsyncClient:
        """Возвращает переиспользуемый httpx.AsyncClient.

        Used by DI layer to share the HTTP client with other components.
        Default: creates a new client. Adapters should override for reuse.
        """
        return httpx.AsyncClient()

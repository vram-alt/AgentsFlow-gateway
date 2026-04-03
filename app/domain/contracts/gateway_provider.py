"""Абстрактный контракт GatewayProvider — интерфейс для адаптеров LLM-провайдеров."""

from __future__ import annotations

import abc
from typing import Union

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

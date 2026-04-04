"""
ChatService — оркестратор полного цикла отправки промпта к LLM через адаптер.

Спецификация: app/services/chat_service_spec.md
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import MessageItem, UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse
from app.infrastructure.database.repositories import ProviderRepository
from app.services.log_service import LogService

logger = logging.getLogger(__name__)


class ChatService:
    """Оркестратор чата: провайдер → адаптер → лог → ответ."""

    def __init__(
        self,
        provider_repo: ProviderRepository,
        log_service: LogService,
        adapter: GatewayProvider,
    ) -> None:
        """[YEL-1] Concrete types instead of Any for dependency injection."""
        self.provider_repo = provider_repo
        self.log_service = log_service
        self.adapter = adapter

    async def send_chat_message(
        self,
        model: str,
        messages: list[dict[str, str]],
        provider_name: str = "portkey",
        temperature: float | None = None,
        max_tokens: int | None = None,
        guardrail_ids: list[str] | None = None,
    ) -> UnifiedResponse | GatewayError:
        """Полный цикл: получить провайдера → вызвать адаптер → залогировать → вернуть."""

        trace_id = str(uuid.uuid4())
        result: UnifiedResponse | GatewayError

        # ── Шаг 1: Получение учётных данных провайдера ───────────────
        try:
            provider_record = await self.provider_repo.get_active_by_name(provider_name)
        except Exception as exc:
            logger.error("DB error fetching provider %s: %s", provider_name, exc)
            result = GatewayError(
                trace_id=trace_id,
                error_code="UNKNOWN",
                message=f"Database error: {exc}",
            )
            await self._safe_log(trace_id=trace_id, prompt=None, response=result)
            return result

        if provider_record is None:
            result = GatewayError(
                trace_id=trace_id,
                error_code="AUTH_FAILED",
                message=f"Provider '{provider_name}' not found or deactivated",
            )
            await self._safe_log(trace_id=trace_id, prompt=None, response=result)
            return result

        api_key: str = provider_record.api_key
        base_url: str = provider_record.base_url

        # ── Шаг 2: Формирование UnifiedPrompt ────────────────────────
        prompt = UnifiedPrompt(
            trace_id=trace_id,
            model=model,
            messages=[MessageItem(**m) for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            guardrail_ids=guardrail_ids if guardrail_ids is not None else [],
        )

        # ── Шаг 3: Отправка через адаптер ────────────────────────────
        try:
            result = await self.adapter.send_prompt(prompt, api_key, base_url)
        except Exception as exc:
            logger.error("Adapter exception: %s", exc)
            result = GatewayError(
                trace_id=trace_id,
                error_code="UNKNOWN",
                message=f"Adapter error: {exc}",
            )

        # ── Шаг 4: Логирование (не блокирует ответ) ──────────────────
        await self._safe_log(trace_id=trace_id, prompt=prompt, response=result)

        return result

    async def _safe_log(
        self,
        trace_id: str,
        prompt: UnifiedPrompt | None,
        response: UnifiedResponse | GatewayError,
    ) -> None:
        """Вызывает log_service.log_chat_request, подавляя любые исключения."""
        try:
            prompt_data: dict[str, Any] = (
                prompt.model_dump() if prompt is not None else {}
            )
            response_data: dict[str, Any] = (
                response.model_dump() if hasattr(response, "model_dump") else {}
            )
            await self.log_service.log_chat_request(
                trace_id=trace_id,
                prompt_data=prompt_data,
                response_data=response_data,
            )
        except Exception as exc:
            logger.warning("Logging failed (suppressed): %s", exc)

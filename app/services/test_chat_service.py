"""
Unit tests for ChatService — оркестратора чата.
Specification: app/services/chat_service_spec.md

TDD Red phase: all tests should fail with ImportError,
until ChatService is not implemented (chat_service.py содержит только # Placeholder).

All dependencies (ProviderRepository, LogService, GatewayProvider) — are strictly mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Import tested class (should fail during Red phase) ──────────────
from app.services.chat_service import ChatService

# ── Импорт доменных объектов (already implemented) ──────────────────────────
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import MessageItem, UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse, UsageInfo


# ═══════════════════════════════════════════════════════════════════════════
# Constants для тестов
# ═══════════════════════════════════════════════════════════════════════════

VALID_TRACE_ID = "123e4567-e89b-42d3-a456-426614174000"
SAMPLE_MODEL = "gpt-4"
SAMPLE_MESSAGES = [{"role": "user", "content": "Hello, world!"}]
SAMPLE_API_KEY = "sk-test-key-12345"
SAMPLE_BASE_URL = "https://api.portkey.ai"
SAMPLE_PROVIDER_NAME = "portkey"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_provider_repo():
    """Mock ProviderRepository with async methods."""
    repo = AsyncMock()
    # По умолчанию: провайдер найден и активен
    provider_record = MagicMock()
    provider_record.api_key = SAMPLE_API_KEY
    provider_record.base_url = SAMPLE_BASE_URL
    provider_record.name = SAMPLE_PROVIDER_NAME
    provider_record.is_active = True
    repo.get_active_by_name = AsyncMock(return_value=provider_record)
    return repo


@pytest.fixture
def mock_log_service():
    """Mock LogService with async methods."""
    svc = AsyncMock()
    svc.log_chat_request = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def mock_adapter():
    """Мок GatewayProvider (адаптер) с async-методами."""
    adapter = AsyncMock()
    adapter.provider_name = SAMPLE_PROVIDER_NAME
    # Default: successful response
    adapter.send_prompt = AsyncMock(
        return_value=UnifiedResponse(
            trace_id=VALID_TRACE_ID,
            content="Hello! How can I help you?",
            model=SAMPLE_MODEL,
            usage=UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )
    )
    return adapter


@pytest.fixture
def service(mock_provider_repo, mock_log_service, mock_adapter):
    """Instance of ChatService with mocked dependencies."""
    return ChatService(
        provider_repo=mock_provider_repo,
        log_service=mock_log_service,
        adapter=mock_adapter,
    )


@pytest.fixture
def sample_unified_response():
    """Пример успешного UnifiedResponse."""
    return UnifiedResponse(
        trace_id=VALID_TRACE_ID,
        content="Hello! How can I help you?",
        model=SAMPLE_MODEL,
        usage=UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Конструктор (specification §2)
# ═══════════════════════════════════════════════════════════════════════════


class TestChatServiceConstructor:
    """Constructor tests for ChatService (specification §2)."""

    def test_constructor_accepts_all_dependencies(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """ChatService accepts provider_repo, log_service, adapter."""
        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        assert svc is not None

    def test_constructor_stores_provider_repo(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """Dependency provider_repo сохраняется как атрибут."""
        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        assert svc.provider_repo is mock_provider_repo

    def test_constructor_stores_log_service(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """Dependency log_service сохраняется как атрибут."""
        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        assert svc.log_service is mock_log_service

    def test_constructor_stores_adapter(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """Dependency adapter сохраняется как атрибут."""
        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        assert svc.adapter is mock_adapter


# ═══════════════════════════════════════════════════════════════════════════
# 2. Успешный проход (Happy Path) — спецификация §3
# ═══════════════════════════════════════════════════════════════════════════


class TestSendChatMessageHappyPath:
    """Успешный сценарий: политика OK -> провайдер OK -> лог OK -> ответ."""

    @pytest.mark.asyncio
    async def test_returns_unified_response_on_success(self, service, mock_adapter):
        """При успешном вызове возвращается UnifiedResponse."""
        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, UnifiedResponse)

    @pytest.mark.asyncio
    async def test_calls_provider_repo_get_active_by_name(
        self, service, mock_provider_repo
    ):
        """Шаг 2: вызывает provider_repo.get_active_by_name с provider_name."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
            provider_name="portkey",
        )
        mock_provider_repo.get_active_by_name.assert_awaited_once_with("portkey")

    @pytest.mark.asyncio
    async def test_default_provider_name_is_portkey(self, service, mock_provider_repo):
        """provider_name по умолчанию = 'portkey' (specification §3)."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_provider_repo.get_active_by_name.assert_awaited_once_with("portkey")

    @pytest.mark.asyncio
    async def test_calls_adapter_send_prompt(self, service, mock_adapter):
        """Шаг 4: вызывает adapter.send_prompt с UnifiedPrompt, api_key, base_url."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_adapter.send_prompt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_adapter_receives_correct_api_key_and_base_url(
        self, service, mock_adapter
    ):
        """adapter.send_prompt получает api_key и base_url из записи a provider."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        call_args = mock_adapter.send_prompt.call_args
        # Позиционные или именованные — проверяем наличие api_key и base_url
        args, kwargs = call_args
        # send_prompt(prompt, api_key, base_url)
        if len(args) >= 3:
            assert args[1] == SAMPLE_API_KEY
            assert args[2] == SAMPLE_BASE_URL
        else:
            assert kwargs.get("api_key") == SAMPLE_API_KEY
            assert kwargs.get("base_url") == SAMPLE_BASE_URL

    @pytest.mark.asyncio
    async def test_adapter_receives_unified_prompt(self, service, mock_adapter):
        """adapter.send_prompt получает UnifiedPrompt как первый аргумент."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        call_args = mock_adapter.send_prompt.call_args
        prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("prompt")
        assert isinstance(prompt_arg, UnifiedPrompt)

    @pytest.mark.asyncio
    async def test_prompt_contains_correct_model(self, service, mock_adapter):
        """UnifiedPrompt содержит переданную модель."""
        await service.send_chat_message(
            model="gpt-4-turbo",
            messages=SAMPLE_MESSAGES,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.model == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_prompt_contains_messages_as_message_items(
        self, service, mock_adapter
    ):
        """UnifiedPrompt.messages — список MessageItem из переданных словарей."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=[{"role": "user", "content": "Test"}],
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert len(prompt_arg.messages) == 1
        assert isinstance(prompt_arg.messages[0], MessageItem)
        assert prompt_arg.messages[0].role == "user"
        assert prompt_arg.messages[0].content == "Test"

    @pytest.mark.asyncio
    async def test_prompt_trace_id_is_valid_uuid4(self, service, mock_adapter):
        """Шаг 1: trace_id в UnifiedPrompt — валидный UUID v4."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        parsed = uuid.UUID(prompt_arg.trace_id)
        assert parsed.version == 4

    @pytest.mark.asyncio
    async def test_prompt_temperature_passed_through(self, service, mock_adapter):
        """temperature передаётся в UnifiedPrompt, если задана."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
            temperature=0.7,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.temperature == 0.7

    @pytest.mark.asyncio
    async def test_prompt_max_tokens_passed_through(self, service, mock_adapter):
        """max_tokens передаётся в UnifiedPrompt, если задан."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
            max_tokens=1024,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.max_tokens == 1024

    @pytest.mark.asyncio
    async def test_prompt_guardrail_ids_passed_through(self, service, mock_adapter):
        """guardrail_ids передаются в UnifiedPrompt, если заданы."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
            guardrail_ids=["gr-001", "gr-002"],
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.guardrail_ids == ["gr-001", "gr-002"]

    @pytest.mark.asyncio
    async def test_prompt_guardrail_ids_default_empty(self, service, mock_adapter):
        """guardrail_ids по умолчанию — пустой список."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.guardrail_ids == []

    @pytest.mark.asyncio
    async def test_prompt_temperature_none_by_default(self, service, mock_adapter):
        """temperature defaults to None."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.temperature is None

    @pytest.mark.asyncio
    async def test_prompt_max_tokens_none_by_default(self, service, mock_adapter):
        """max_tokens defaults to None."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.max_tokens is None

    @pytest.mark.asyncio
    async def test_log_service_called_on_success(self, service, mock_log_service):
        """Шаг 5: log_service.log_chat_request вызывается при успехе."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_log_service.log_chat_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_service_receives_trace_id(
        self, service, mock_log_service, mock_adapter
    ):
        """log_service.log_chat_request получает trace_id из промпта."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        call_kwargs = mock_log_service.log_chat_request.call_args
        args, kwargs = call_kwargs
        # trace_id должен быть передан (позиционно или именованно)
        trace_id_value = kwargs.get("trace_id") or args[0]
        parsed = uuid.UUID(trace_id_value)
        assert parsed.version == 4

    @pytest.mark.asyncio
    async def test_response_content_matches_adapter_output(self, service, mock_adapter):
        """Возвращённый UnifiedResponse содержит content от адаптера."""
        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert result.content == "Hello! How can I help you?"

    @pytest.mark.asyncio
    async def test_each_call_generates_unique_trace_id(self, service, mock_adapter):
        """Каждый вызов send_chat_message генерирует уникальный trace_id."""
        await service.send_chat_message(model=SAMPLE_MODEL, messages=SAMPLE_MESSAGES)
        trace_id_1 = mock_adapter.send_prompt.call_args[0][0].trace_id

        mock_adapter.send_prompt.reset_mock()
        # Нужен новый ответ с другим trace_id для второго вызова
        mock_adapter.send_prompt.return_value = UnifiedResponse(
            trace_id="550e8400-e29b-41d4-a716-446655440000",
            content="Second response",
            model=SAMPLE_MODEL,
        )
        await service.send_chat_message(model=SAMPLE_MODEL, messages=SAMPLE_MESSAGES)
        trace_id_2 = mock_adapter.send_prompt.call_args[0][0].trace_id

        assert trace_id_1 != trace_id_2


# ═══════════════════════════════════════════════════════════════════════════
# 3. Провайдер не найден / деактивирован (specification §4, AUTH_FAILED)
# ═══════════════════════════════════════════════════════════════════════════


class TestSendChatMessageProviderNotFound:
    """Provider not found или деактивирован → GatewayError(AUTH_FAILED)."""

    @pytest.mark.asyncio
    async def test_returns_gateway_error_when_provider_not_found(
        self, service, mock_provider_repo
    ):
        """If provider_repo.get_active_by_name вернул None → GatewayError."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_error_code_is_auth_failed_when_provider_not_found(
        self, service, mock_provider_repo
    ):
        """error_code = 'AUTH_FAILED' при отсутствии a provider."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert result.error_code == "AUTH_FAILED"

    @pytest.mark.asyncio
    async def test_error_message_mentions_provider(self, service, mock_provider_repo):
        """Сообщение ошибки содержит информацию о провайдере."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result.message, str)
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_adapter_not_called_when_provider_not_found(
        self, service, mock_provider_repo, mock_adapter
    ):
        """Адаптер НЕ вызывается, if provider not found."""
        mock_provider_repo.get_active_by_name.return_value = None

        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_adapter.send_prompt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_service_called_on_provider_not_found(
        self, service, mock_provider_repo, mock_log_service
    ):
        """Логирование вызывается даже при отсутствии a provider."""
        mock_provider_repo.get_active_by_name.return_value = None

        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_log_service.log_chat_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gateway_error_has_valid_trace_id(self, service, mock_provider_repo):
        """GatewayError содержит валидный UUID v4 trace_id."""
        mock_provider_repo.get_active_by_name.return_value = None

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        parsed = uuid.UUID(result.trace_id)
        assert parsed.version == 4


# ═══════════════════════════════════════════════════════════════════════════
# 4. Ошибка БД при получении провайдера (specification §4, UNKNOWN)
# ═══════════════════════════════════════════════════════════════════════════


class TestSendChatMessageProviderDbError:
    """Ошибка БД при получении провайдера → GatewayError(UNKNOWN)."""

    @pytest.mark.asyncio
    async def test_returns_gateway_error_on_db_exception(
        self, service, mock_provider_repo
    ):
        """[SRE_MARKER] Ошибка БД при get_active_by_name → GatewayError."""
        mock_provider_repo.get_active_by_name.side_effect = Exception(
            "DB connection lost"
        )

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_error_code_is_unknown_on_db_exception(
        self, service, mock_provider_repo
    ):
        """[SRE_MARKER] error_code = 'UNKNOWN' при ошибке БД."""
        mock_provider_repo.get_active_by_name.side_effect = Exception("DB timeout")

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert result.error_code == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_adapter_not_called_on_db_exception(
        self, service, mock_provider_repo, mock_adapter
    ):
        """[SRE_MARKER] Адаптер НЕ вызывается при ошибке БД."""
        mock_provider_repo.get_active_by_name.side_effect = Exception("DB down")

        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_adapter.send_prompt.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Адаптер вернул GatewayError (specification §4, проброс ошибки)
# ═══════════════════════════════════════════════════════════════════════════


class TestSendChatMessageAdapterReturnsError:
    """Адаптер вернул GatewayError → пробросить как есть + залогировать."""

    @pytest.fixture
    def adapter_error(self):
        """GatewayError от адаптера."""
        return GatewayError(
            trace_id=VALID_TRACE_ID,
            error_code="PROVIDER_ERROR",
            message="Model overloaded",
            status_code=503,
            provider_name="portkey",
        )

    @pytest.mark.asyncio
    async def test_returns_gateway_error_from_adapter(
        self, service, mock_adapter, adapter_error
    ):
        """If адаптер вернул GatewayError, он пробрасывается как есть."""
        mock_adapter.send_prompt.return_value = adapter_error

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, GatewayError)
        assert result.error_code == "PROVIDER_ERROR"

    @pytest.mark.asyncio
    async def test_adapter_error_message_preserved(
        self, service, mock_adapter, adapter_error
    ):
        """Сообщение ошибки от адаптера сохраняется."""
        mock_adapter.send_prompt.return_value = adapter_error

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert result.message == "Model overloaded"

    @pytest.mark.asyncio
    async def test_log_service_called_on_adapter_error(
        self, service, mock_adapter, mock_log_service, adapter_error
    ):
        """Логирование вызывается при ошибке адаптера."""
        mock_adapter.send_prompt.return_value = adapter_error

        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_log_service.log_chat_request.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Адаптер выбросил исключение (specification §4, UNKNOWN)
# ═══════════════════════════════════════════════════════════════════════════


class TestSendChatMessageAdapterException:
    """Адаптер выбросил непредвиденное исключение → GatewayError(UNKNOWN)."""

    @pytest.mark.asyncio
    async def test_returns_gateway_error_on_adapter_exception(
        self, service, mock_adapter
    ):
        """[SRE_MARKER] Непредвиденное исключение адаптера → GatewayError."""
        mock_adapter.send_prompt.side_effect = RuntimeError("Connection reset")

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_error_code_is_unknown_on_adapter_exception(
        self, service, mock_adapter
    ):
        """[SRE_MARKER] error_code = 'UNKNOWN' при исключении адаптера."""
        mock_adapter.send_prompt.side_effect = RuntimeError("Unexpected failure")

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert result.error_code == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_log_service_called_on_adapter_exception(
        self, service, mock_adapter, mock_log_service
    ):
        """[SRE_MARKER] Логирование вызывается при исключении адаптера."""
        mock_adapter.send_prompt.side_effect = RuntimeError("Crash")

        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        mock_log_service.log_chat_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gateway_error_has_valid_trace_id_on_exception(
        self, service, mock_adapter
    ):
        """[SRE_MARKER] GatewayError содержит валидный trace_id при исключении."""
        mock_adapter.send_prompt.side_effect = RuntimeError("Boom")

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        parsed = uuid.UUID(result.trace_id)
        assert parsed.version == 4


# ═══════════════════════════════════════════════════════════════════════════
# 7. Логирование не блокирует ответ (specification §3.5, §4)
# ═══════════════════════════════════════════════════════════════════════════


class TestLoggingDoesNotBlockResponse:
    """[SRE_MARKER] Ошибка логирования не влияет на ответ пользователю."""

    @pytest.mark.asyncio
    async def test_success_response_returned_even_if_logging_fails(
        self, service, mock_log_service
    ):
        """Успешный ответ возвращается, даже если log_service падает."""
        mock_log_service.log_chat_request.side_effect = Exception("Log DB down")

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, UnifiedResponse)

    @pytest.mark.asyncio
    async def test_error_response_returned_even_if_logging_fails(
        self, service, mock_provider_repo, mock_log_service
    ):
        """GatewayError возвращается, даже если log_service падает."""
        mock_provider_repo.get_active_by_name.return_value = None
        mock_log_service.log_chat_request.side_effect = Exception("Log DB down")

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(result, GatewayError)

    @pytest.mark.asyncio
    async def test_logging_exception_suppressed_silently(
        self, service, mock_log_service
    ):
        """[SRE_MARKER] Исключение логирования подавляется — не пробрасывается."""
        mock_log_service.log_chat_request.side_effect = OSError("Disk full")

        # Не должно выбросить исключение
        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════
# 8. Порядок вызовов оркестрации (specification §3)
# ═══════════════════════════════════════════════════════════════════════════


class TestOrchestrationOrder:
    """Проверка правильного порядка вызовов в оркестрации."""

    @pytest.mark.asyncio
    async def test_provider_repo_called_before_adapter(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """provider_repo.get_active_by_name вызывается ДО adapter.send_prompt."""
        call_order: list[str] = []

        async def track_repo(*args, **kwargs):
            call_order.append("provider_repo")
            provider_record = MagicMock()
            provider_record.api_key = SAMPLE_API_KEY
            provider_record.base_url = SAMPLE_BASE_URL
            provider_record.name = SAMPLE_PROVIDER_NAME
            provider_record.is_active = True
            return provider_record

        async def track_adapter(*args, **kwargs):
            call_order.append("adapter")
            return UnifiedResponse(
                trace_id=VALID_TRACE_ID,
                content="OK",
                model=SAMPLE_MODEL,
            )

        mock_provider_repo.get_active_by_name = AsyncMock(side_effect=track_repo)
        mock_adapter.send_prompt = AsyncMock(side_effect=track_adapter)

        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        await svc.send_chat_message(model=SAMPLE_MODEL, messages=SAMPLE_MESSAGES)

        assert call_order.index("provider_repo") < call_order.index("adapter")

    @pytest.mark.asyncio
    async def test_adapter_called_before_log_service(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """adapter.send_prompt вызывается ДО log_service.log_chat_request."""
        call_order: list[str] = []

        async def track_adapter(*args, **kwargs):
            call_order.append("adapter")
            return UnifiedResponse(
                trace_id=VALID_TRACE_ID,
                content="OK",
                model=SAMPLE_MODEL,
            )

        async def track_log(*args, **kwargs):
            call_order.append("log_service")
            return None

        mock_adapter.send_prompt = AsyncMock(side_effect=track_adapter)
        mock_log_service.log_chat_request = AsyncMock(side_effect=track_log)

        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        await svc.send_chat_message(model=SAMPLE_MODEL, messages=SAMPLE_MESSAGES)

        assert "adapter" in call_order
        assert "log_service" in call_order
        assert call_order.index("adapter") < call_order.index("log_service")

    @pytest.mark.asyncio
    async def test_full_orchestration_order(
        self, mock_provider_repo, mock_log_service, mock_adapter
    ):
        """Полный порядок: provider_repo → adapter → log_service."""
        call_order: list[str] = []

        async def track_repo(*args, **kwargs):
            call_order.append("provider_repo")
            provider_record = MagicMock()
            provider_record.api_key = SAMPLE_API_KEY
            provider_record.base_url = SAMPLE_BASE_URL
            provider_record.name = SAMPLE_PROVIDER_NAME
            provider_record.is_active = True
            return provider_record

        async def track_adapter(*args, **kwargs):
            call_order.append("adapter")
            return UnifiedResponse(
                trace_id=VALID_TRACE_ID,
                content="OK",
                model=SAMPLE_MODEL,
            )

        async def track_log(*args, **kwargs):
            call_order.append("log_service")
            return None

        mock_provider_repo.get_active_by_name = AsyncMock(side_effect=track_repo)
        mock_adapter.send_prompt = AsyncMock(side_effect=track_adapter)
        mock_log_service.log_chat_request = AsyncMock(side_effect=track_log)

        svc = ChatService(
            provider_repo=mock_provider_repo,
            log_service=mock_log_service,
            adapter=mock_adapter,
        )
        await svc.send_chat_message(model=SAMPLE_MODEL, messages=SAMPLE_MESSAGES)

        assert call_order == ["provider_repo", "adapter", "log_service"]

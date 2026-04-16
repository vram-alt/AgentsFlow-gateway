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

DETERMINISTIC_LOCAL_CHECK_CASES = [
    pytest.param(
        {"id": "default.sentenceCount", "parameters": {"minSentences": 1, "maxSentences": 3}},
        {"request": {"text": "First sentence. Second sentence."}},
        id="sentence-count",
    ),
    pytest.param(
        {"id": "default.wordCount", "parameters": {"minWords": 2, "maxWords": 10}},
        {"request": {"text": "three simple words"}},
        id="word-count",
    ),
    pytest.param(
        {"id": "default.characterCount", "parameters": {"minCharacters": 5, "maxCharacters": 30}},
        {"request": {"text": "hello world"}},
        id="character-count",
    ),
    pytest.param(
        {"id": "default.uppercaseCheck", "parameters": {"not": False}},
        {"request": {"text": "HELLO WORLD"}},
        id="uppercase-check",
    ),
    pytest.param(
        {"id": "default.lowercaseDetection", "parameters": {"format": "lowercase"}},
        {"request": {"text": "hello world"}},
        id="lowercase-check",
    ),
    pytest.param(
        {"id": "default.endsWith", "parameters": {"Suffix": "."}},
        {"request": {"text": "Ends with a dot."}},
        id="ends-with",
    ),
    pytest.param(
        {"id": "default.jsonSchema", "parameters": {"schema": {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}}},
        {"request": {"text": '{"key": "value"}'}},
        id="json-schema",
    ),
    pytest.param(
        {"id": "default.jsonKeys", "parameters": {"keys": ["key1", "key2"], "operator": "all"}},
        {"request": {"text": '{"key1": "value", "key2": 2}'}},
        id="json-keys",
    ),
    pytest.param(
        {"id": "default.validUrls", "parameters": {"onlyDNS": False}},
        {"request": {"text": "Visit https://example.com/docs for more info."}},
        id="valid-urls",
    ),
    pytest.param(
        {"id": "default.containsCode", "parameters": {"format": "sql"}},
        {"request": {"text": "SELECT * FROM users WHERE id = 1;"}},
        id="contains-code",
    ),
    pytest.param(
        {"id": "default.notNull", "parameters": {"not": False}},
        {"request": {"text": "non-empty content"}},
        id="not-null",
    ),
    pytest.param(
        {"id": "default.contains", "parameters": {"words": ["blocked-word"], "operator": "any"}},
        {"request": {"text": "This contains blocked-word in the prompt."}},
        id="contains",
    ),
    pytest.param(
        {"id": "default.modelWhitelist", "parameters": {"Models": ["gpt-4o"], "Inverse": False}},
        {"request": {"text": "hello", "json": {"model": "gpt-4o"}}},
        id="model-whitelist",
    ),
    pytest.param(
        {"id": "default.modelRules", "parameters": {"rules": {"tier": ["gpt-4o"]}, "not": False}},
        {"request": {"text": "hello", "json": {"model": "gpt-4o"}}, "metadata": {"tier": "premium"}},
        id="model-rules",
    ),
    pytest.param(
        {"id": "default.allowedRequestTypes", "parameters": {"allowedTypes": ["chat"], "blockedTypes": []}},
        {"request": {"text": "hello"}},
        id="allowed-request-types",
    ),
    pytest.param(
        {"id": "default.requiredMetadataKeys", "parameters": {"metadataKeys": ["user_id", "session_id"], "operator": "all"}},
        {"request": {"text": "hello"}, "metadata": {"user_id": "u-1", "session_id": "s-1"}},
        id="required-metadata-keys",
    ),
    pytest.param(
        {"id": "default.requiredMetadataKeyValuePairs", "parameters": {"metadataPairs": {"environment": "production"}, "operator": "all"}},
        {"request": {"text": "hello"}, "metadata": {"environment": "production"}},
        id="required-metadata-kv",
    ),
]


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
def mock_policy_repo():
    """Mock PolicyRepository with async methods."""
    repo = AsyncMock()
    repo.list_all = AsyncMock(return_value=[])
    return repo


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
def service(mock_provider_repo, mock_policy_repo, mock_log_service, mock_adapter):
    """Instance of ChatService with mocked dependencies."""
    return ChatService(
        provider_repo=mock_provider_repo,
        policy_repo=mock_policy_repo,
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
    async def test_active_cloud_guardrails_auto_apply_when_none_selected(
        self, service, mock_policy_repo, mock_adapter
    ):
        """Active cloud guardrails should be applied by default even when the UI sends none."""
        active_cloud_policy = MagicMock(
            id=11,
            name="Cloud block",
            remote_id="gr-cloud-001",
            body={"deny": True},
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [active_cloud_policy]

        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
        )

        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.guardrail_ids == ["gr-cloud-001"]

    @pytest.mark.asyncio
    async def test_active_local_guardrail_can_block_before_llm_call(
        self, service, mock_policy_repo, mock_adapter
    ):
        """Active local webhook/regex-style policies should block in the gateway before the LLM call."""
        local_policy = MagicMock(
            id=21,
            name="Block blocked-word",
            remote_id=None,
            body={
                "checks": [
                    {
                        "id": "default.regexMatch",
                        "parameters": {
                            "rule": "blocked-word",
                            "not": True,
                        },
                    }
                ],
                "actions": {"onFail": "block", "onPass": "allow"},
                "deny": True,
            },
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [local_policy]

        result = await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=[{"role": "user", "content": "This contains blocked-word."}],
        )

        assert isinstance(result, UnifiedResponse)
        assert result.guardrail_blocked is True
        assert "Block blocked-word" in result.content
        mock_adapter.send_prompt.assert_not_awaited()

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

    @pytest.mark.asyncio
    async def test_prompt_contains_metadata_when_provided(self, service, mock_adapter):
        """Chat metadata should be carried into the unified prompt."""
        await service.send_chat_message(
            model=SAMPLE_MODEL,
            messages=SAMPLE_MESSAGES,
            metadata={"agent_id": "HR Onboarding Assistant Agent"},
        )

        prompt_arg = mock_adapter.send_prompt.call_args[0][0]
        assert prompt_arg.metadata["agent_id"] == "HR Onboarding Assistant Agent"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Провайдер не найден / деактивирован (specification §4, AUTH_FAILED)
# ═══════════════════════════════════════════════════════════════════════════


class TestDeterministicLocalGuardrails:
    """Deterministic Portkey BASIC guardrails should evaluate correctly in local mode."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("check", "request_payload"), DETERMINISTIC_LOCAL_CHECK_CASES)
    async def test_each_new_deterministic_check_can_pass_locally(
        self, service, check, request_payload
    ):
        """Each newly added deterministic check should produce a passing local verdict for valid input."""
        result = await service._evaluate_local_check(check, request_payload)

        assert result["id"] == check["id"]
        assert result["verdict"] is True
        assert isinstance(result["explanation"], str)
        assert result["explanation"]


# ═══════════════════════════════════════════════════════════════════════════
# Deep audit: edge-case tests for every local evaluator
# ═══════════════════════════════════════════════════════════════════════════


class TestModelWhitelistCaseInsensitive:
    """Model whitelist must match case-insensitively."""

    @pytest.mark.asyncio
    async def test_model_matches_different_casing(self, service):
        check = {"id": "default.modelWhitelist", "parameters": {"Models": ["gemini-2.5-flash"], "Inverse": False}}
        payload = {"request": {"text": "", "json": {"model": "Gemini-2.5-Flash"}}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_model_matches_uppercase(self, service):
        check = {"id": "default.modelWhitelist", "parameters": {"Models": ["gpt-4o"], "Inverse": False}}
        payload = {"request": {"text": "", "json": {"model": "GPT-4O"}}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_model_not_in_whitelist_blocks(self, service):
        check = {"id": "default.modelWhitelist", "parameters": {"Models": ["gpt-4o"], "Inverse": False}}
        payload = {"request": {"text": "", "json": {"model": "claude-3"}}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_inverse_whitelist_blocks_listed_model(self, service):
        check = {"id": "default.modelWhitelist", "parameters": {"Models": ["gpt-4o"], "Inverse": True}}
        payload = {"request": {"text": "", "json": {"model": "gpt-4o"}}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_inverse_whitelist_allows_unlisted_model(self, service):
        check = {"id": "default.modelWhitelist", "parameters": {"Models": ["gpt-4o"], "Inverse": True}}
        payload = {"request": {"text": "", "json": {"model": "claude-3"}}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_empty_models_list_blocks_any_model(self, service):
        check = {"id": "default.modelWhitelist", "parameters": {"Models": [], "Inverse": False}}
        payload = {"request": {"text": "", "json": {"model": "gpt-4o"}}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestModelRulesCaseInsensitive:
    """Model rules must compare model names case-insensitively."""

    @pytest.mark.asyncio
    async def test_rules_match_different_casing(self, service):
        check = {"id": "default.modelRules", "parameters": {"rules": {"tier": ["gpt-4o"]}, "not": False}}
        payload = {"request": {"text": "", "json": {"model": "GPT-4O"}}, "metadata": {"tier": "premium"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_rules_reject_unlisted_model(self, service):
        check = {"id": "default.modelRules", "parameters": {"rules": {"tier": ["gpt-4o"]}, "not": False}}
        payload = {"request": {"text": "", "json": {"model": "claude-3"}}, "metadata": {"tier": "premium"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestLowercaseCheckInversion:
    """Lowercase check should support 'not' parameter inversion like uppercase."""

    @pytest.mark.asyncio
    async def test_lowercase_pass(self, service):
        check = {"id": "default.lowercaseDetection", "parameters": {}}
        payload = {"request": {"text": "all lowercase text"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_lowercase_fail_for_uppercase(self, service):
        check = {"id": "default.lowercaseDetection", "parameters": {}}
        payload = {"request": {"text": "NOT lowercase"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_lowercase_inverted_pass(self, service):
        check = {"id": "default.lowercaseDetection", "parameters": {"not": True}}
        payload = {"request": {"text": "NOT lowercase"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_lowercase_inverted_fail(self, service):
        check = {"id": "default.lowercaseDetection", "parameters": {"not": True}}
        payload = {"request": {"text": "all lowercase text"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestRangeCheckSafeParsing:
    """Range-based checks must not crash on non-numeric parameter values."""

    @pytest.mark.asyncio
    async def test_sentence_count_non_numeric_param(self, service):
        check = {"id": "default.sentenceCount", "parameters": {"minSentences": "abc", "maxSentences": "xyz"}}
        payload = {"request": {"text": "One sentence."}}
        result = await service._evaluate_local_check(check, payload)
        assert isinstance(result["verdict"], bool)
        assert "explanation" in result

    @pytest.mark.asyncio
    async def test_word_count_non_numeric_param(self, service):
        check = {"id": "default.wordCount", "parameters": {"minWords": "abc"}}
        payload = {"request": {"text": "some words"}}
        result = await service._evaluate_local_check(check, payload)
        assert isinstance(result["verdict"], bool)

    @pytest.mark.asyncio
    async def test_character_count_non_numeric_param(self, service):
        check = {"id": "default.characterCount", "parameters": {"minCharacters": "bad"}}
        payload = {"request": {"text": "text"}}
        result = await service._evaluate_local_check(check, payload)
        assert isinstance(result["verdict"], bool)


class TestSentenceCountEdgeCases:
    """Sentence count edge cases."""

    @pytest.mark.asyncio
    async def test_empty_text(self, service):
        check = {"id": "default.sentenceCount", "parameters": {"minSentences": 1}}
        payload = {"request": {"text": ""}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_exceeds_max(self, service):
        check = {"id": "default.sentenceCount", "parameters": {"maxSentences": 1}}
        payload = {"request": {"text": "First. Second. Third."}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestWordCountEdgeCases:
    """Word count edge cases."""

    @pytest.mark.asyncio
    async def test_empty_text(self, service):
        check = {"id": "default.wordCount", "parameters": {"minWords": 1}}
        payload = {"request": {"text": ""}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_exceeds_max(self, service):
        check = {"id": "default.wordCount", "parameters": {"maxWords": 2}}
        payload = {"request": {"text": "too many words here"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestCharacterCountEdgeCases:
    """Character count edge cases."""

    @pytest.mark.asyncio
    async def test_empty_text_below_min(self, service):
        check = {"id": "default.characterCount", "parameters": {"minCharacters": 1}}
        payload = {"request": {"text": ""}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_exceeds_max(self, service):
        check = {"id": "default.characterCount", "parameters": {"maxCharacters": 3}}
        payload = {"request": {"text": "toolong"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestUppercaseEdgeCases:
    """Uppercase check edge cases."""

    @pytest.mark.asyncio
    async def test_mixed_case_fails(self, service):
        check = {"id": "default.uppercaseCheck", "parameters": {}}
        payload = {"request": {"text": "Hello"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_inverted_mixed_case_passes(self, service):
        check = {"id": "default.uppercaseCheck", "parameters": {"not": True}}
        payload = {"request": {"text": "Hello"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_empty_text_fails(self, service):
        check = {"id": "default.uppercaseCheck", "parameters": {}}
        payload = {"request": {"text": ""}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestEndsWithEdgeCases:
    """EndsWith check edge cases."""

    @pytest.mark.asyncio
    async def test_missing_suffix_fails(self, service):
        check = {"id": "default.endsWith", "parameters": {}}
        payload = {"request": {"text": "hello."}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_wrong_suffix_fails(self, service):
        check = {"id": "default.endsWith", "parameters": {"Suffix": "!"}}
        payload = {"request": {"text": "hello."}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_trailing_whitespace_handled(self, service):
        check = {"id": "default.endsWith", "parameters": {"Suffix": "."}}
        payload = {"request": {"text": "hello.   "}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True


class TestJsonSchemaEdgeCases:
    """JSON Schema check edge cases."""

    @pytest.mark.asyncio
    async def test_non_json_text_fails(self, service):
        check = {"id": "default.jsonSchema", "parameters": {"schema": {"type": "object"}}}
        payload = {"request": {"text": "not json"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_missing_required_key(self, service):
        check = {"id": "default.jsonSchema", "parameters": {"schema": {"type": "object", "required": ["missing_key"]}}}
        payload = {"request": {"text": '{"other": 1}'}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_missing_schema_param(self, service):
        check = {"id": "default.jsonSchema", "parameters": {}}
        payload = {"request": {"text": '{"key": 1}'}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestJsonKeysEdgeCases:
    """JSON Keys check edge cases."""

    @pytest.mark.asyncio
    async def test_operator_none_passes_when_no_keys_present(self, service):
        check = {"id": "default.jsonKeys", "parameters": {"keys": ["secret"], "operator": "none"}}
        payload = {"request": {"text": '{"public": 1}'}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_operator_any_passes_with_one_match(self, service):
        check = {"id": "default.jsonKeys", "parameters": {"keys": ["a", "b"], "operator": "any"}}
        payload = {"request": {"text": '{"a": 1}'}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_operator_all_fails_when_missing_key(self, service):
        check = {"id": "default.jsonKeys", "parameters": {"keys": ["a", "b"], "operator": "all"}}
        payload = {"request": {"text": '{"a": 1}'}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestContainsCheckEdgeCases:
    """Contains check edge cases."""

    @pytest.mark.asyncio
    async def test_operator_none_passes_when_no_words_found(self, service):
        check = {"id": "default.contains", "parameters": {"words": ["forbidden"], "operator": "none"}}
        payload = {"request": {"text": "clean text"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_operator_none_fails_when_word_found(self, service):
        check = {"id": "default.contains", "parameters": {"words": ["clean"], "operator": "none"}}
        payload = {"request": {"text": "clean text"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_operator_all_fails_when_partial(self, service):
        check = {"id": "default.contains", "parameters": {"words": ["hello", "world"], "operator": "all"}}
        payload = {"request": {"text": "hello there"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestNotNullEdgeCases:
    """NotNull check edge cases."""

    @pytest.mark.asyncio
    async def test_empty_string_fails(self, service):
        check = {"id": "default.notNull", "parameters": {}}
        payload = {"request": {"text": ""}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_whitespace_only_fails(self, service):
        check = {"id": "default.notNull", "parameters": {}}
        payload = {"request": {"text": "   "}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_inverted_empty_passes(self, service):
        check = {"id": "default.notNull", "parameters": {"not": True}}
        payload = {"request": {"text": ""}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True


class TestContainsCodeEdgeCases:
    """ContainsCode check edge cases."""

    @pytest.mark.asyncio
    async def test_python_detected(self, service):
        check = {"id": "default.containsCode", "parameters": {"format": "python"}}
        payload = {"request": {"text": "def hello():\n    pass"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_plain_text_no_code(self, service):
        check = {"id": "default.containsCode", "parameters": {"format": "python"}}
        payload = {"request": {"text": "just a normal sentence"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestValidUrlsEdgeCases:
    """ValidUrls check edge cases."""

    @pytest.mark.asyncio
    async def test_no_urls_passes(self, service):
        check = {"id": "default.validUrls", "parameters": {}}
        payload = {"request": {"text": "No URLs here."}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_valid_url_passes(self, service):
        check = {"id": "default.validUrls", "parameters": {}}
        payload = {"request": {"text": "Go to https://example.com"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True


class TestAllowedRequestTypesEdgeCases:
    """AllowedRequestTypes check edge cases."""

    @pytest.mark.asyncio
    async def test_chat_blocked(self, service):
        check = {"id": "default.allowedRequestTypes", "parameters": {"blockedTypes": ["chat"]}}
        payload = {"request": {"text": "hello"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_chat_not_in_allowed_fails(self, service):
        check = {"id": "default.allowedRequestTypes", "parameters": {"allowedTypes": ["embedding"]}}
        payload = {"request": {"text": "hello"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestRegexCheckEdgeCases:
    """Regex check edge cases."""

    @pytest.mark.asyncio
    async def test_regex_match_passes(self, service):
        check = {"id": "default.regexMatch", "parameters": {"rule": r"\d{3}-\d{4}"}}
        payload = {"request": {"text": "Call 555-1234"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True

    @pytest.mark.asyncio
    async def test_regex_no_match_fails(self, service):
        check = {"id": "default.regexMatch", "parameters": {"rule": r"\d{3}-\d{4}"}}
        payload = {"request": {"text": "No phone number"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_regex_inverted_blocks_match(self, service):
        check = {"id": "default.regexMatch", "parameters": {"rule": "badword", "not": True}}
        payload = {"request": {"text": "contains badword"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_regex_invalid_pattern(self, service):
        check = {"id": "default.regexMatch", "parameters": {"rule": "[invalid"}}
        payload = {"request": {"text": "test"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False

    @pytest.mark.asyncio
    async def test_regex_missing_rule(self, service):
        check = {"id": "default.regexMatch", "parameters": {}}
        payload = {"request": {"text": "test"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is False


class TestUnsupportedCheckSkipped:
    """Unsupported check types should be skipped with verdict=True."""

    @pytest.mark.asyncio
    async def test_unknown_check_passes(self, service):
        check = {"id": "custom.unknownCheck", "parameters": {}}
        payload = {"request": {"text": "test"}}
        result = await service._evaluate_local_check(check, payload)
        assert result["verdict"] is True
        assert "Unsupported" in result["explanation"]


class TestPolicyBlockingE2E:
    """End-to-end: a failing local policy with deny=True blocks the request."""

    @pytest.mark.asyncio
    async def test_model_not_in_whitelist_blocks_request(
        self, service, mock_policy_repo, mock_adapter
    ):
        """A model NOT in the whitelist should block the request entirely."""
        local_policy = MagicMock(
            id=99,
            name="Model gate",
            remote_id=None,
            body={
                "checks": [{"id": "default.modelWhitelist", "parameters": {"Models": ["gpt-4o"], "Inverse": False}}],
                "actions": {"onFail": "block"},
                "deny": True,
            },
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [local_policy]

        result = await service.send_chat_message(
            model="claude-3",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert isinstance(result, UnifiedResponse)
        assert result.guardrail_blocked is True
        assert "Model gate" in result.content
        mock_adapter.send_prompt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_model_in_whitelist_allows_request(
        self, service, mock_policy_repo, mock_adapter
    ):
        """A model IN the whitelist should allow the request through."""
        local_policy = MagicMock(
            id=100,
            name="Model gate",
            remote_id=None,
            body={
                "checks": [{"id": "default.modelWhitelist", "parameters": {"Models": ["gemini-2.5-flash", "gpt-4o"], "Inverse": False}}],
                "actions": {"onFail": "block", "onPass": "allow"},
                "deny": True,
            },
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [local_policy]

        result = await service.send_chat_message(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "hello"}],
        )

        assert isinstance(result, UnifiedResponse)
        assert result.guardrail_blocked is not True
        mock_adapter.send_prompt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_model_whitelist_case_insensitive_e2e(
        self, service, mock_policy_repo, mock_adapter
    ):
        """Model whitelist match must be case-insensitive end-to-end."""
        local_policy = MagicMock(
            id=101,
            name="Model gate CI",
            remote_id=None,
            body={
                "checks": [{"id": "default.modelWhitelist", "parameters": {"Models": ["gemini-2.5-flash"], "Inverse": False}}],
                "actions": {"onFail": "block"},
                "deny": True,
            },
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [local_policy]

        result = await service.send_chat_message(
            model="GEMINI-2.5-FLASH",
            messages=[{"role": "user", "content": "hello"}],
        )

        assert isinstance(result, UnifiedResponse)
        assert result.guardrail_blocked is not True
        mock_adapter.send_prompt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_external_validation_blocks_before_provider_call_with_transformed_message(
        self, service, mock_policy_repo, mock_adapter
    ):
        """A failing external validation check should block before the Portkey request."""
        local_policy = MagicMock(
            id=102,
            name="External agent policy",
            remote_id=None,
            body={
                "checks": [
                    {
                        "id": "external.validation",
                        "parameters": {
                            "method": "POST",
                            "url": "https://example.com/policy/execute",
                            "eventType": "beforeRequestHook",
                            "verdictPath": "result.verdict",
                            "messagePath": "result.metadata.decision",
                            "transformedMessagePath": "result.transformedData.request.json.messages.0.content",
                            "bodyTemplate": {
                                "request": {"text": "{{request.latest_text}}"},
                                "eventType": "{{eventType}}",
                                "metadata": {"agent_id": "{{metadata.agent_id}}"},
                            },
                        },
                    }
                ],
                "actions": {"onFail": "block"},
                "deny": True,
            },
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [local_policy]

        response = MagicMock(status_code=200)
        response.json.return_value = {
            "result": {
                "verdict": False,
                "metadata": {"decision": "block", "policies": ["Mask Emails Policy"]},
                "transformedData": {
                    "request": {
                        "json": {
                            "messages": [
                                {"role": "user", "content": "Request blocked due to policy violation"}
                            ]
                        }
                    }
                },
            }
        }
        mock_client = AsyncMock()
        mock_client.request.return_value = response
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_client

        with patch("app.services.chat_service.httpx.AsyncClient", return_value=mock_cm):
            result = await service.send_chat_message(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "My email is alice@example.com"}],
                metadata={"agent_id": "HR Onboarding Assistant Agent"},
            )

        assert isinstance(result, UnifiedResponse)
        assert result.guardrail_blocked is True
        assert result.content == "Request blocked due to policy violation"
        mock_adapter.send_prompt.assert_not_awaited()
        request_kwargs = mock_client.request.await_args.kwargs
        assert request_kwargs["json"]["request"]["text"] == "My email is alice@example.com"
        assert request_kwargs["json"]["metadata"]["agent_id"] == "HR Onboarding Assistant Agent"

    @pytest.mark.asyncio
    async def test_external_validation_can_block_after_provider_response(
        self, service, mock_policy_repo, mock_adapter
    ):
        """After-response external validation should be able to replace the LLM output."""
        local_policy = MagicMock(
            id=103,
            name="External response policy",
            remote_id=None,
            body={
                "checks": [
                    {
                        "id": "external.validation",
                        "parameters": {
                            "method": "POST",
                            "url": "https://example.com/policy/execute",
                            "eventType": "afterResponseHook",
                            "verdictPath": "result.verdict",
                            "transformedMessagePath": "result.transformedData.request.json.messages.0.content",
                            "bodyTemplate": {
                                "request": {"text": "{{request.latest_text}}"},
                                "response": {"text": "{{response.text}}"},
                                "metadata": {"agent_id": "{{metadata.agent_id}}"},
                            },
                        },
                    }
                ],
                "actions": {"onFail": "block"},
                "deny": True,
            },
            is_active=True,
        )
        mock_policy_repo.list_all.return_value = [local_policy]

        response = MagicMock(status_code=200)
        response.json.return_value = {
            "result": {
                "verdict": False,
                "transformedData": {
                    "request": {
                        "json": {
                            "messages": [
                                {"role": "user", "content": "Response blocked due to policy violation"}
                            ]
                        }
                    }
                },
            }
        }
        mock_client = AsyncMock()
        mock_client.request.return_value = response
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_client

        with patch("app.services.chat_service.httpx.AsyncClient", return_value=mock_cm):
            result = await service.send_chat_message(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "Tell me something sensitive"}],
                metadata={"agent_id": "Finance Assistant"},
            )

        assert isinstance(result, UnifiedResponse)
        assert result.guardrail_blocked is True
        assert result.content == "Response blocked due to policy violation"
        mock_adapter.send_prompt.assert_awaited_once()


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

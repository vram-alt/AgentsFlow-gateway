"""
TDD Red phase: тесты для Pydantic-моделей DTO UnifiedPrompt и MessageItem.

Tested models (из unified_prompt.py):
  - MessageItem — вложенная frozen Pydantic V2 модель сообщения диалога.
  - UnifiedPrompt — frozen Pydantic V2 DTO для стандартизированного
    представления запроса пользователя к LLM-провайдеру.

Specification: unified_prompt_spec.md
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.domain.dto.unified_prompt import MessageItem, UnifiedPrompt


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture()
def valid_trace_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def valid_messages() -> list[dict]:
    return [
        {"role": "system", "content": "Ты — полезный ассистент."},
        {"role": "user", "content": "Привет, как дела?"},
    ]


@pytest.fixture()
def valid_data(valid_trace_id: str, valid_messages: list[dict]) -> dict:
    return {"trace_id": valid_trace_id, "model": "gpt-4o", "messages": valid_messages}


@pytest.fixture()
def full_data(valid_trace_id: str, valid_messages: list[dict]) -> dict:
    return {
        "trace_id": valid_trace_id,
        "model": "gpt-4o",
        "messages": valid_messages,
        "temperature": 0.7,
        "max_tokens": 1024,
        "guardrail_ids": ["policy-001", "policy-002"],
        "metadata": {"user_id": "u-123", "session": "s-456"},
    }


# ==========================================================================
# MessageItem — создание
# ==========================================================================


class TestMessageItemCreation:
    @pytest.mark.parametrize("role", ["system", "user", "assistant"])
    def test_valid_roles_accepted(self, role: str) -> None:
        msg = MessageItem(role=role, content="Текст")
        assert msg.role == role

    def test_content_preserved(self) -> None:
        msg = MessageItem(role="user", content="Привет!")
        assert msg.content == "Привет!"

    def test_is_pydantic_base_model(self) -> None:
        from pydantic import BaseModel

        assert isinstance(MessageItem(role="user", content="x"), BaseModel)


# ==========================================================================
# MessageItem — frozen
# ==========================================================================


class TestMessageItemFrozen:
    def test_cannot_modify_role(self) -> None:
        msg = MessageItem(role="user", content="x")
        with pytest.raises(ValidationError):
            msg.role = "system"

    def test_cannot_modify_content(self) -> None:
        msg = MessageItem(role="user", content="x")
        with pytest.raises(ValidationError):
            msg.content = "y"


# ==========================================================================
# MessageItem — валидация role
# ==========================================================================


class TestMessageItemRoleValidation:
    def test_invalid_role_rejected(self) -> None:
        """[SRE_MARKER] — произвольные роли могут привести к инъекции промпта."""
        with pytest.raises(ValidationError):
            MessageItem(role="admin", content="Текст")

    def test_empty_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MessageItem(role="", content="Текст")

    def test_role_case_sensitive(self) -> None:
        """[SRE_MARKER] — обход валидации через смену регистра."""
        for bad in ("User", "SYSTEM", "Assistant"):
            with pytest.raises(ValidationError):
                MessageItem(role=bad, content="Текст")

    def test_role_required(self) -> None:
        with pytest.raises(ValidationError):
            MessageItem(content="Текст")

    def test_role_none_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MessageItem(role=None, content="Текст")


# ==========================================================================
# MessageItem — валидация content
# ==========================================================================


class TestMessageItemContentValidation:
    def test_content_required(self) -> None:
        with pytest.raises(ValidationError):
            MessageItem(role="user")

    def test_content_accepts_unicode(self) -> None:
        msg = MessageItem(role="user", content="こんにちは 🌍 مرحبا")
        assert msg.content == "こんにちは 🌍 مرحبا"


# ==========================================================================
# UnifiedPrompt — создание
# ==========================================================================


class TestUnifiedPromptCreation:
    def test_valid_minimal(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        assert p.trace_id == valid_data["trace_id"]
        assert p.model == "gpt-4o"
        assert len(p.messages) == 2

    def test_valid_full(self, full_data: dict) -> None:
        p = UnifiedPrompt(**full_data)
        assert p.temperature == 0.7
        assert p.max_tokens == 1024
        assert p.guardrail_ids == ["policy-001", "policy-002"]
        assert p.metadata == {"user_id": "u-123", "session": "s-456"}

    def test_messages_are_message_item(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        for msg in p.messages:
            assert isinstance(msg, MessageItem)

    def test_is_pydantic_base_model(self, valid_data: dict) -> None:
        from pydantic import BaseModel

        assert isinstance(UnifiedPrompt(**valid_data), BaseModel)


# ==========================================================================
# UnifiedPrompt — значения по умолчанию
# ==========================================================================


class TestUnifiedPromptDefaults:
    def test_temperature_defaults_to_none(self, valid_data: dict) -> None:
        assert UnifiedPrompt(**valid_data).temperature is None

    def test_max_tokens_defaults_to_none(self, valid_data: dict) -> None:
        assert UnifiedPrompt(**valid_data).max_tokens is None

    def test_guardrail_ids_defaults_to_empty_list(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        assert p.guardrail_ids == []
        assert isinstance(p.guardrail_ids, list)

    def test_metadata_defaults_to_empty_dict(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        assert p.metadata == {}
        assert isinstance(p.metadata, dict)

    def test_guardrail_ids_not_shared(self, valid_data: dict) -> None:
        """[SRE_MARKER] — default_factory: каждый экземпляр получает свой список."""
        assert (
            UnifiedPrompt(**valid_data).guardrail_ids
            is not UnifiedPrompt(**valid_data).guardrail_ids
        )

    def test_metadata_not_shared(self, valid_data: dict) -> None:
        """[SRE_MARKER] — default_factory: каждый экземпляр получает свой словарь."""
        assert (
            UnifiedPrompt(**valid_data).metadata
            is not UnifiedPrompt(**valid_data).metadata
        )


# ==========================================================================
# UnifiedPrompt — frozen
# ==========================================================================


class TestUnifiedPromptFrozen:
    def test_cannot_modify_trace_id(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        with pytest.raises(ValidationError):
            p.trace_id = str(uuid.uuid4())

    def test_cannot_modify_model(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        with pytest.raises(ValidationError):
            p.model = "claude-3-opus"

    def test_cannot_modify_messages(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**valid_data)
        with pytest.raises(ValidationError):
            p.messages = []

    def test_cannot_modify_temperature(self, full_data: dict) -> None:
        p = UnifiedPrompt(**full_data)
        with pytest.raises(ValidationError):
            p.temperature = 1.5

    def test_cannot_modify_max_tokens(self, full_data: dict) -> None:
        p = UnifiedPrompt(**full_data)
        with pytest.raises(ValidationError):
            p.max_tokens = 2048

    def test_cannot_modify_guardrail_ids(self, full_data: dict) -> None:
        p = UnifiedPrompt(**full_data)
        with pytest.raises(ValidationError):
            p.guardrail_ids = ["new"]

    def test_cannot_modify_metadata(self, full_data: dict) -> None:
        p = UnifiedPrompt(**full_data)
        with pytest.raises(ValidationError):
            p.metadata = {"new": "data"}


# ==========================================================================
# UnifiedPrompt — валидация trace_id
# ==========================================================================


class TestUnifiedPromptTraceId:
    def test_trace_id_required(self) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

    def test_empty_string_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "trace_id": ""})

    def test_invalid_uuid_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "trace_id": "not-a-uuid"})

    def test_uuid_v1_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — UUID v1 содержит MAC-адрес, только v4 допустим."""
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "trace_id": str(uuid.uuid1())})

    def test_valid_uuid_v4_accepted(self, valid_data: dict) -> None:
        v = str(uuid.uuid4())
        assert UnifiedPrompt(**{**valid_data, "trace_id": v}).trace_id == v


# ==========================================================================
# UnifiedPrompt — валидация model
# ==========================================================================


class TestUnifiedPromptModel:
    def test_model_required(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(
                trace_id=valid_trace_id, messages=[{"role": "user", "content": "Hi"}]
            )

    def test_accepts_various_ids(self, valid_data: dict) -> None:
        for mid in ("gpt-4o", "gpt-3.5-turbo", "claude-3-opus", "llama-3-70b"):
            assert UnifiedPrompt(**{**valid_data, "model": mid}).model == mid


# ==========================================================================
# UnifiedPrompt — валидация messages
# ==========================================================================


class TestUnifiedPromptMessages:
    def test_messages_required(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(trace_id=valid_trace_id, model="gpt-4o")

    def test_empty_list_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — пустой запрос к LLM — вектор DoS-атаки."""
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "messages": []})

    def test_single_item_accepted(self, valid_data: dict) -> None:
        p = UnifiedPrompt(
            **{**valid_data, "messages": [{"role": "user", "content": "Hi"}]}
        )
        assert len(p.messages) == 1

    def test_multiple_items_accepted(self, valid_data: dict) -> None:
        msgs = [
            {"role": "system", "content": "Sys"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Bye"},
        ]
        assert len(UnifiedPrompt(**{**valid_data, "messages": msgs}).messages) == 4

    def test_invalid_role_in_message_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(
                **{**valid_data, "messages": [{"role": "bad", "content": "x"}]}
            )


# ==========================================================================
# UnifiedPrompt — валидация temperature
# ==========================================================================


class TestUnifiedPromptTemperature:
    def test_none_accepted(self, valid_data: dict) -> None:
        assert UnifiedPrompt(**{**valid_data, "temperature": None}).temperature is None

    @pytest.mark.parametrize("val", [0.0, 0.5, 1.0, 2.0])
    def test_valid_range_accepted(self, valid_data: dict, val: float) -> None:
        assert UnifiedPrompt(**{**valid_data, "temperature": val}).temperature == val

    def test_negative_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — отрицательная temperature не поддерживается провайдерами."""
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "temperature": -0.1})

    def test_above_2_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — temperature > 2.0 ведёт к бессмысленной генерации."""
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "temperature": 2.1})

    def test_large_value_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "temperature": 100.0})


# ==========================================================================
# UnifiedPrompt — валидация max_tokens
# ==========================================================================


class TestUnifiedPromptMaxTokens:
    def test_none_accepted(self, valid_data: dict) -> None:
        assert UnifiedPrompt(**{**valid_data, "max_tokens": None}).max_tokens is None

    @pytest.mark.parametrize("val", [1, 1024, 128000])
    def test_positive_accepted(self, valid_data: dict, val: int) -> None:
        assert UnifiedPrompt(**{**valid_data, "max_tokens": val}).max_tokens == val

    def test_zero_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — max_tokens=0 бессмысленно, пустой ответ a provider."""
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "max_tokens": 0})

    def test_negative_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — отрицательный max_tokens не имеет смысла."""
        with pytest.raises(ValidationError):
            UnifiedPrompt(**{**valid_data, "max_tokens": -1})


# ==========================================================================
# UnifiedPrompt — guardrail_ids и metadata
# ==========================================================================


class TestUnifiedPromptGuardrailIds:
    def test_accepts_list_of_strings(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**{**valid_data, "guardrail_ids": ["p1", "p2"]})
        assert p.guardrail_ids == ["p1", "p2"]

    def test_accepts_empty_list(self, valid_data: dict) -> None:
        assert UnifiedPrompt(**{**valid_data, "guardrail_ids": []}).guardrail_ids == []


class TestUnifiedPromptMetadata:
    def test_accepts_dict(self, valid_data: dict) -> None:
        p = UnifiedPrompt(**{**valid_data, "metadata": {"k": "v"}})
        assert p.metadata == {"k": "v"}

    def test_accepts_nested_dict(self, valid_data: dict) -> None:
        nested = {"a": {"b": {"c": "deep"}}}
        assert UnifiedPrompt(**{**valid_data, "metadata": nested}).metadata == nested

    def test_accepts_empty_dict(self, valid_data: dict) -> None:
        assert UnifiedPrompt(**{**valid_data, "metadata": {}}).metadata == {}


# ==========================================================================
# UnifiedPrompt — сериализация
# ==========================================================================


class TestUnifiedPromptSerialization:
    def test_model_dump_returns_dict(self, full_data: dict) -> None:
        data = UnifiedPrompt(**full_data).model_dump()
        assert isinstance(data, dict)
        for key in (
            "trace_id",
            "model",
            "messages",
            "temperature",
            "max_tokens",
            "guardrail_ids",
            "metadata",
        ):
            assert key in data

    def test_model_dump_json_returns_string(self, valid_data: dict) -> None:
        json_str = UnifiedPrompt(**valid_data).model_dump_json()
        assert isinstance(json_str, str)
        assert valid_data["trace_id"] in json_str


# ==========================================================================
# UnifiedPrompt — обязательные поля отсутствуют
# ==========================================================================


class TestUnifiedPromptMissingFields:
    def test_missing_all(self) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt()

    def test_missing_trace_id(self) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])

    def test_missing_model(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(
                trace_id=valid_trace_id, messages=[{"role": "user", "content": "Hi"}]
            )

    def test_missing_messages(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedPrompt(trace_id=valid_trace_id, model="gpt-4o")

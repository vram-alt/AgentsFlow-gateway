"""
TDD Red phase: тесты для Pydantic-моделей DTO UnifiedResponse и UsageInfo.

Tested models (из unified_response.py):
  - UsageInfo — вложенная frozen Pydantic V2 модель статистики токенов.
  - UnifiedResponse — frozen Pydantic V2 DTO для стандартизированного
    представления ответа от LLM-провайдера.

Specification: unified_response_spec.md
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.domain.dto.unified_response import UnifiedResponse, UsageInfo


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture()
def valid_trace_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def valid_usage_data() -> dict:
    return {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


@pytest.fixture()
def valid_usage(valid_usage_data: dict) -> UsageInfo:
    return UsageInfo(**valid_usage_data)


@pytest.fixture()
def valid_data(valid_trace_id: str) -> dict:
    return {
        "trace_id": valid_trace_id,
        "content": "Привет! Я — ассистент.",
        "model": "gpt-4o",
    }


@pytest.fixture()
def full_data(valid_trace_id: str, valid_usage_data: dict) -> dict:
    return {
        "trace_id": valid_trace_id,
        "content": "Ответ модели.",
        "model": "gpt-4o",
        "usage": valid_usage_data,
        "provider_raw": {"id": "chatcmpl-abc123", "object": "chat.completion"},
        "guardrail_blocked": True,
        "guardrail_details": {"reason": "toxic_content", "score": 0.95},
    }


# ==========================================================================
# UsageInfo — создание
# ==========================================================================


class TestUsageInfoCreation:
    def test_valid_creation(self, valid_usage_data: dict) -> None:
        u = UsageInfo(**valid_usage_data)
        assert u.prompt_tokens == 10
        assert u.completion_tokens == 20
        assert u.total_tokens == 30

    def test_zero_values_accepted(self) -> None:
        u = UsageInfo(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0

    def test_large_values_accepted(self) -> None:
        u = UsageInfo(
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            total_tokens=1_500_000,
        )
        assert u.total_tokens == 1_500_000

    def test_is_pydantic_base_model(self, valid_usage_data: dict) -> None:
        assert isinstance(UsageInfo(**valid_usage_data), BaseModel)


# ==========================================================================
# UsageInfo — frozen
# ==========================================================================


class TestUsageInfoFrozen:
    def test_cannot_modify_prompt_tokens(self, valid_usage: UsageInfo) -> None:
        with pytest.raises(ValidationError):
            valid_usage.prompt_tokens = 999

    def test_cannot_modify_completion_tokens(self, valid_usage: UsageInfo) -> None:
        with pytest.raises(ValidationError):
            valid_usage.completion_tokens = 999

    def test_cannot_modify_total_tokens(self, valid_usage: UsageInfo) -> None:
        with pytest.raises(ValidationError):
            valid_usage.total_tokens = 999


# ==========================================================================
# UsageInfo — валидация: неотрицательные целые
# ==========================================================================


class TestUsageInfoValidation:
    def test_negative_prompt_tokens_rejected(self) -> None:
        """[SRE_MARKER] — отрицательные токены могут исказить биллинг."""
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=-1, completion_tokens=0, total_tokens=0)

    def test_negative_completion_tokens_rejected(self) -> None:
        """[SRE_MARKER] — отрицательные токены могут исказить биллинг."""
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=0, completion_tokens=-5, total_tokens=0)

    def test_negative_total_tokens_rejected(self) -> None:
        """[SRE_MARKER] — отрицательные токены могут исказить биллинг."""
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=0, completion_tokens=0, total_tokens=-100)

    def test_prompt_tokens_required(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo(completion_tokens=10, total_tokens=10)

    def test_completion_tokens_required(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=10, total_tokens=10)

    def test_total_tokens_required(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=10, completion_tokens=10)

    def test_all_fields_required(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo()

    def test_float_rejected_for_prompt_tokens(self) -> None:
        """[SRE_MARKER] — дробные токены не имеют смысла, strict int."""
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=10.5, completion_tokens=0, total_tokens=10)

    def test_float_rejected_for_completion_tokens(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=0, completion_tokens=5.5, total_tokens=5)

    def test_float_rejected_for_total_tokens(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens=0, completion_tokens=0, total_tokens=1.1)

    def test_string_rejected_for_tokens(self) -> None:
        with pytest.raises(ValidationError):
            UsageInfo(prompt_tokens="ten", completion_tokens=0, total_tokens=10)


# ==========================================================================
# UnifiedResponse — создание
# ==========================================================================


class TestUnifiedResponseCreation:
    def test_valid_minimal(self, valid_data: dict) -> None:
        r = UnifiedResponse(**valid_data)
        assert r.trace_id == valid_data["trace_id"]
        assert r.content == valid_data["content"]
        assert r.model == "gpt-4o"

    def test_valid_full(self, full_data: dict) -> None:
        r = UnifiedResponse(**full_data)
        assert r.content == "Ответ модели."
        assert r.model == "gpt-4o"
        assert r.usage is not None
        assert r.usage.prompt_tokens == 10
        assert r.provider_raw == {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
        }
        assert r.guardrail_blocked is True
        assert r.guardrail_details == {"reason": "toxic_content", "score": 0.95}

    def test_usage_is_usage_info_instance(self, full_data: dict) -> None:
        r = UnifiedResponse(**full_data)
        assert isinstance(r.usage, UsageInfo)

    def test_is_pydantic_base_model(self, valid_data: dict) -> None:
        assert isinstance(UnifiedResponse(**valid_data), BaseModel)


# ==========================================================================
# UnifiedResponse — значения по умолчанию
# ==========================================================================


class TestUnifiedResponseDefaults:
    def test_usage_defaults_to_none(self, valid_data: dict) -> None:
        assert UnifiedResponse(**valid_data).usage is None

    def test_provider_raw_defaults_to_empty_dict(self, valid_data: dict) -> None:
        r = UnifiedResponse(**valid_data)
        assert r.provider_raw == {}
        assert isinstance(r.provider_raw, dict)

    def test_guardrail_blocked_defaults_to_false(self, valid_data: dict) -> None:
        assert UnifiedResponse(**valid_data).guardrail_blocked is False

    def test_guardrail_details_defaults_to_none(self, valid_data: dict) -> None:
        assert UnifiedResponse(**valid_data).guardrail_details is None

    def test_provider_raw_not_shared(self, valid_data: dict) -> None:
        """[SRE_MARKER] — default_factory: каждый экземпляр получает свой словарь."""
        assert (
            UnifiedResponse(**valid_data).provider_raw
            is not UnifiedResponse(**valid_data).provider_raw
        )


# ==========================================================================
# UnifiedResponse — frozen
# ==========================================================================


class TestUnifiedResponseFrozen:
    def test_cannot_modify_trace_id(self, valid_data: dict) -> None:
        r = UnifiedResponse(**valid_data)
        with pytest.raises(ValidationError):
            r.trace_id = str(uuid.uuid4())

    def test_cannot_modify_content(self, valid_data: dict) -> None:
        r = UnifiedResponse(**valid_data)
        with pytest.raises(ValidationError):
            r.content = "Новый контент"

    def test_cannot_modify_model(self, valid_data: dict) -> None:
        r = UnifiedResponse(**valid_data)
        with pytest.raises(ValidationError):
            r.model = "claude-3-opus"

    def test_cannot_modify_usage(self, full_data: dict) -> None:
        r = UnifiedResponse(**full_data)
        with pytest.raises(ValidationError):
            r.usage = None

    def test_cannot_modify_provider_raw(self, full_data: dict) -> None:
        r = UnifiedResponse(**full_data)
        with pytest.raises(ValidationError):
            r.provider_raw = {"new": "data"}

    def test_cannot_modify_guardrail_blocked(self, full_data: dict) -> None:
        r = UnifiedResponse(**full_data)
        with pytest.raises(ValidationError):
            r.guardrail_blocked = False

    def test_cannot_modify_guardrail_details(self, full_data: dict) -> None:
        r = UnifiedResponse(**full_data)
        with pytest.raises(ValidationError):
            r.guardrail_details = None


# ==========================================================================
# UnifiedResponse — валидация trace_id
# ==========================================================================


class TestUnifiedResponseTraceId:
    def test_trace_id_required(self) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(content="Hello", model="gpt-4o")

    def test_empty_string_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(**{**valid_data, "trace_id": ""})

    def test_invalid_uuid_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(**{**valid_data, "trace_id": "not-a-uuid"})

    def test_uuid_v1_rejected(self, valid_data: dict) -> None:
        """[SRE_MARKER] — UUID v1 содержит MAC-адрес, только v4 допустим."""
        with pytest.raises(ValidationError):
            UnifiedResponse(**{**valid_data, "trace_id": str(uuid.uuid1())})

    def test_valid_uuid_v4_accepted(self, valid_data: dict) -> None:
        v = str(uuid.uuid4())
        assert UnifiedResponse(**{**valid_data, "trace_id": v}).trace_id == v


# ==========================================================================
# UnifiedResponse — валидация content
# ==========================================================================


class TestUnifiedResponseContent:
    def test_content_required(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(trace_id=valid_trace_id, model="gpt-4o")

    def test_empty_string_accepted(self, valid_data: dict) -> None:
        """Specification: content может быть пустой строкой (если заблокирован Guardrail)."""
        r = UnifiedResponse(**{**valid_data, "content": ""})
        assert r.content == ""

    def test_content_accepts_unicode(self, valid_data: dict) -> None:
        r = UnifiedResponse(**{**valid_data, "content": "こんにちは 🌍 مرحبا"})
        assert r.content == "こんにちは 🌍 مرحبا"

    def test_content_preserves_multiline(self, valid_data: dict) -> None:
        text = "Строка 1\nСтрока 2\nСтрока 3"
        r = UnifiedResponse(**{**valid_data, "content": text})
        assert r.content == text


# ==========================================================================
# UnifiedResponse — валидация model
# ==========================================================================


class TestUnifiedResponseModel:
    def test_model_required(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(trace_id=valid_trace_id, content="Hello")

    def test_accepts_various_model_ids(self, valid_data: dict) -> None:
        for mid in ("gpt-4o", "gpt-3.5-turbo", "claude-3-opus", "llama-3-70b"):
            assert UnifiedResponse(**{**valid_data, "model": mid}).model == mid


# ==========================================================================
# UnifiedResponse — валидация usage
# ==========================================================================


class TestUnifiedResponseUsage:
    def test_none_accepted(self, valid_data: dict) -> None:
        assert UnifiedResponse(**{**valid_data, "usage": None}).usage is None

    def test_valid_usage_dict_accepted(self, valid_data: dict) -> None:
        r = UnifiedResponse(
            **{
                **valid_data,
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 10,
                    "total_tokens": 15,
                },
            }
        )
        assert r.usage is not None
        assert r.usage.prompt_tokens == 5
        assert r.usage.completion_tokens == 10
        assert r.usage.total_tokens == 15

    def test_invalid_usage_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(**{**valid_data, "usage": {"prompt_tokens": -1}})

    def test_usage_missing_fields_rejected(self, valid_data: dict) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(**{**valid_data, "usage": {"prompt_tokens": 10}})


# ==========================================================================
# UnifiedResponse — валидация provider_raw
# ==========================================================================


class TestUnifiedResponseProviderRaw:
    def test_accepts_dict(self, valid_data: dict) -> None:
        raw = {"id": "abc", "status": 200}
        r = UnifiedResponse(**{**valid_data, "provider_raw": raw})
        assert r.provider_raw == raw

    def test_accepts_empty_dict(self, valid_data: dict) -> None:
        r = UnifiedResponse(**{**valid_data, "provider_raw": {}})
        assert r.provider_raw == {}

    def test_accepts_nested_dict(self, valid_data: dict) -> None:
        nested = {"response": {"choices": [{"text": "hi"}]}}
        r = UnifiedResponse(**{**valid_data, "provider_raw": nested})
        assert r.provider_raw == nested


# ==========================================================================
# UnifiedResponse — валидация guardrail_blocked
# ==========================================================================


class TestUnifiedResponseGuardrailBlocked:
    def test_true_accepted(self, valid_data: dict) -> None:
        r = UnifiedResponse(**{**valid_data, "guardrail_blocked": True})
        assert r.guardrail_blocked is True

    def test_false_accepted(self, valid_data: dict) -> None:
        r = UnifiedResponse(**{**valid_data, "guardrail_blocked": False})
        assert r.guardrail_blocked is False


# ==========================================================================
# UnifiedResponse — валидация guardrail_details
# ==========================================================================


class TestUnifiedResponseGuardrailDetails:
    def test_none_accepted(self, valid_data: dict) -> None:
        r = UnifiedResponse(**{**valid_data, "guardrail_details": None})
        assert r.guardrail_details is None

    def test_dict_accepted(self, valid_data: dict) -> None:
        details = {"reason": "pii_detected", "fields": ["email", "phone"]}
        r = UnifiedResponse(**{**valid_data, "guardrail_details": details})
        assert r.guardrail_details == details

    def test_empty_dict_accepted(self, valid_data: dict) -> None:
        r = UnifiedResponse(**{**valid_data, "guardrail_details": {}})
        assert r.guardrail_details == {}


# ==========================================================================
# UnifiedResponse — сериализация
# ==========================================================================


class TestUnifiedResponseSerialization:
    def test_model_dump_returns_dict(self, full_data: dict) -> None:
        data = UnifiedResponse(**full_data).model_dump()
        assert isinstance(data, dict)
        for key in (
            "trace_id",
            "content",
            "model",
            "usage",
            "provider_raw",
            "guardrail_blocked",
            "guardrail_details",
        ):
            assert key in data

    def test_model_dump_json_returns_string(self, valid_data: dict) -> None:
        json_str = UnifiedResponse(**valid_data).model_dump_json()
        assert isinstance(json_str, str)
        assert valid_data["trace_id"] in json_str

    def test_model_dump_usage_is_dict(self, full_data: dict) -> None:
        data = UnifiedResponse(**full_data).model_dump()
        assert isinstance(data["usage"], dict)
        assert "prompt_tokens" in data["usage"]


# ==========================================================================
# UnifiedResponse — обязательные поля отсутствуют
# ==========================================================================


class TestUnifiedResponseMissingFields:
    def test_missing_all(self) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse()

    def test_missing_trace_id(self) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(content="Hello", model="gpt-4o")

    def test_missing_content(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(trace_id=valid_trace_id, model="gpt-4o")

    def test_missing_model(self, valid_trace_id: str) -> None:
        with pytest.raises(ValidationError):
            UnifiedResponse(trace_id=valid_trace_id, content="Hello")


# ==========================================================================
# UnifiedResponse — guardrail-сценарий (blocked + empty content)
# ==========================================================================


class TestUnifiedResponseGuardrailScenario:
    """[SRE_MARKER] — Guardrail-блокировка: content пуст, blocked=True, details заполнены."""

    def test_blocked_with_empty_content(self, valid_data: dict) -> None:
        r = UnifiedResponse(
            **{
                **valid_data,
                "content": "",
                "guardrail_blocked": True,
                "guardrail_details": {"reason": "toxic"},
            }
        )
        assert r.content == ""
        assert r.guardrail_blocked is True
        assert r.guardrail_details == {"reason": "toxic"}

    def test_blocked_without_details(self, valid_data: dict) -> None:
        r = UnifiedResponse(
            **{
                **valid_data,
                "content": "",
                "guardrail_blocked": True,
                "guardrail_details": None,
            }
        )
        assert r.guardrail_blocked is True
        assert r.guardrail_details is None

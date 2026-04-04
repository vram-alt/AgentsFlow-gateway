"""
TDD Red phase: тесты для Pydantic-моделей сущности LogEntry.

Tested schemas (из log_entry.py):
  - EventType (str Enum)
  - LogEntryCreate
  - LogEntry

Architectural rule: logs are immutable — no Update schema.
No SQLAlchemy / DB — pure Pydantic validation only.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# Import tested models (should fail during Red phase since log_entry.py is empty)
# --------------------------------------------------------------------------
from app.domain.entities.log_entry import (
    EventType,
    LogEntry,
    LogEntryCreate,
)


# ==========================================================================
# Fixtures
# ==========================================================================

VALID_TRACE_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"


@pytest.fixture()
def valid_log_data() -> dict:
    """Minimal set of required fields for creating a log record."""
    return {
        "trace_id": VALID_TRACE_ID,
        "event_type": EventType.CHAT_REQUEST,
        "payload": {"prompt": "Hello", "response": "Hi there"},
    }


@pytest.fixture()
def full_log_data(valid_log_data: dict) -> dict:
    """Full set of fields, including id and created_at."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        **valid_log_data,
        "id": 1,
        "created_at": now,
    }


# ==========================================================================
# EventType — строковое перечисление
# ==========================================================================


class TestEventType:
    """Tests for Enum EventType."""

    def test_chat_request_value(self) -> None:
        """CHAT_REQUEST has string value 'chat_request'."""
        assert EventType.CHAT_REQUEST == "chat_request"
        assert EventType.CHAT_REQUEST.value == "chat_request"

    def test_guardrail_incident_value(self) -> None:
        """GUARDRAIL_INCIDENT has string value 'guardrail_incident'."""
        assert EventType.GUARDRAIL_INCIDENT == "guardrail_incident"
        assert EventType.GUARDRAIL_INCIDENT.value == "guardrail_incident"

    def test_system_error_value(self) -> None:
        """SYSTEM_ERROR has string value 'system_error'."""
        assert EventType.SYSTEM_ERROR == "system_error"
        assert EventType.SYSTEM_ERROR.value == "system_error"

    def test_exactly_three_members(self) -> None:
        """EventType contains exactly 3 values."""
        assert len(EventType) == 3

    def test_is_string_subclass(self) -> None:
        """EventType inherits from str — each member is a string."""
        for member in EventType:
            assert isinstance(member, str)

    def test_members_list(self) -> None:
        """All allowed values are listed."""
        values = {e.value for e in EventType}
        assert values == {"chat_request", "guardrail_incident", "system_error"}

    def test_lookup_by_value(self) -> None:
        """Can retrieve an Enum member by string value."""
        assert EventType("chat_request") is EventType.CHAT_REQUEST
        assert EventType("guardrail_incident") is EventType.GUARDRAIL_INCIDENT
        assert EventType("system_error") is EventType.SYSTEM_ERROR

    def test_invalid_value_raises(self) -> None:
        """Invalid value raises ValueError."""
        with pytest.raises(ValueError):
            EventType("unknown_event")


# ==========================================================================
# LogEntryCreate — схема для создания записи лога
# ==========================================================================


class TestLogEntryCreate:
    """LogEntryCreate: обязательные поля trace_id, event_type, payload."""

    def test_valid_creation(self, valid_log_data: dict) -> None:
        """Creation of LogEntryCreate with valid data."""
        entry = LogEntryCreate(**valid_log_data)
        assert entry.trace_id == VALID_TRACE_ID
        assert entry.event_type == EventType.CHAT_REQUEST
        assert entry.payload == {"prompt": "Hello", "response": "Hi there"}

    def test_all_event_types_accepted(self) -> None:
        """Все значения EventType принимаются."""
        base = {
            "trace_id": VALID_TRACE_ID,
            "payload": {"key": "value"},
        }
        for et in EventType:
            entry = LogEntryCreate(**{**base, "event_type": et})
            assert entry.event_type == et

    def test_event_type_from_string(self) -> None:
        """event_type accepts строковое значение и приводит к Enum."""
        entry = LogEntryCreate(
            trace_id=VALID_TRACE_ID,
            event_type="guardrail_incident",
            payload={"detail": "blocked"},
        )
        assert entry.event_type == EventType.GUARDRAIL_INCIDENT
        assert isinstance(entry.event_type, EventType)

    # ------------------------------------------------------------------
    # Валидация trace_id (формат UUID v4)
    # ------------------------------------------------------------------

    def test_trace_id_required(self) -> None:
        """trace_id — required field; without it ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate(
                event_type=EventType.CHAT_REQUEST,
                payload={"key": "value"},
            )

    def test_trace_id_valid_uuid_v4(self, valid_log_data: dict) -> None:
        """trace_id в формате UUID v4 проходит валидацию."""
        generated = str(uuid.uuid4())
        entry = LogEntryCreate(**{**valid_log_data, "trace_id": generated})
        assert entry.trace_id == generated

    def test_trace_id_invalid_format_rejected(self, valid_log_data: dict) -> None:
        """
        trace_id не в формате UUID is rejected.
        [SRE_MARKER] — невалидный trace_id сломает корреляцию логов.
        """
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": "not-a-uuid"})

    def test_trace_id_too_short_rejected(self, valid_log_data: dict) -> None:
        """trace_id короче 36 символов is rejected."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": "12345"})

    def test_trace_id_too_long_rejected(self, valid_log_data: dict) -> None:
        """trace_id длиннее 36 символов is rejected."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": VALID_TRACE_ID + "extra"})

    def test_trace_id_without_dashes_rejected(self, valid_log_data: dict) -> None:
        """UUID без дефисов (32 hex символа) is rejected — нужен формат с дефисами."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": uuid.uuid4().hex})

    def test_trace_id_uppercase_accepted(self, valid_log_data: dict) -> None:
        """UUID в верхнем регистре — допустимый формат (36 символов с дефисами)."""
        upper_uuid = str(uuid.uuid4()).upper()
        # Should either pass or be normalized — depends on implementation.
        # Specification says "UUID v4 format (36 characters with hyphens)".
        entry = LogEntryCreate(**{**valid_log_data, "trace_id": upper_uuid})
        assert len(entry.trace_id) == 36

    def test_trace_id_empty_string_rejected(self, valid_log_data: dict) -> None:
        """Empty string trace_id is rejected."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": ""})

    # ------------------------------------------------------------------
    # Валидация event_type (строго из Enum)
    # ------------------------------------------------------------------

    def test_event_type_required(self) -> None:
        """event_type — required field; without it ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate(
                trace_id=VALID_TRACE_ID,
                payload={"key": "value"},
            )

    def test_event_type_invalid_string_rejected(self, valid_log_data: dict) -> None:
        """
        Произвольная строка для event_type is rejected.
        [SRE_MARKER] — неизвестный тип события может обойти фильтрацию аудита.
        """
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "event_type": "unknown_event"})

    def test_event_type_none_rejected(self, valid_log_data: dict) -> None:
        """event_type cannot be None."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "event_type": None})

    def test_event_type_integer_rejected(self, valid_log_data: dict) -> None:
        """event_type cannot be an integer."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "event_type": 42})

    # ------------------------------------------------------------------
    # Валидация payload (не пустой словарь)
    # ------------------------------------------------------------------

    def test_payload_required(self) -> None:
        """payload — required field; without it ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate(
                trace_id=VALID_TRACE_ID,
                event_type=EventType.SYSTEM_ERROR,
            )

    def test_payload_empty_dict_rejected(self, valid_log_data: dict) -> None:
        """
        Пустой словарь payload is rejected (minimum 1 key).
        [SRE_MARKER] — пустой payload в аудит-логе бесполезен и может
        скрыть инцидент безопасности.
        """
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": {}})

    def test_payload_must_be_dict(self, valid_log_data: dict) -> None:
        """payload must be a dict, not a string."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": "not a dict"})

    def test_payload_list_rejected(self, valid_log_data: dict) -> None:
        """payload cannot be a list."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": [1, 2, 3]})

    def test_payload_none_rejected(self, valid_log_data: dict) -> None:
        """payload cannot be None."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": None})

    def test_payload_complex_nested_dict(self, valid_log_data: dict) -> None:
        """payload accepts a complex nested dict."""
        complex_payload = {
            "prompt": "Translate this",
            "response": {"text": "Переведи это", "tokens": 15},
            "metadata": {"model": "gpt-4", "latency_ms": 230},
        }
        entry = LogEntryCreate(**{**valid_log_data, "payload": complex_payload})
        assert entry.payload == complex_payload

    # ------------------------------------------------------------------
    # Отсутствие всех полей
    # ------------------------------------------------------------------

    def test_missing_all_fields(self) -> None:
        """Without required fields — ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate()


# ==========================================================================
# LogEntry — полная доменная сущность (иммутабельная запись аудита)
# ==========================================================================


class TestLogEntry:
    """LogEntry: полная сущность с id and created_at."""

    def test_valid_full_creation(self, full_log_data: dict) -> None:
        """Creation of полной сущности LogEntry with all fields."""
        entry = LogEntry(**full_log_data)
        assert entry.id == 1
        assert entry.trace_id == VALID_TRACE_ID
        assert entry.event_type == EventType.CHAT_REQUEST
        assert entry.payload == {"prompt": "Hello", "response": "Hi there"}
        assert isinstance(entry.created_at, datetime.datetime)

    def test_id_defaults_to_none(self, valid_log_data: dict) -> None:
        """id defaults to None (assigned by DB)."""
        entry = LogEntry(**valid_log_data)
        assert entry.id is None

    def test_created_at_auto_generated(self, valid_log_data: dict) -> None:
        """created_at is auto-generated via default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        entry = LogEntry(**valid_log_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert entry.created_at is not None
        assert before <= entry.created_at <= after

    def test_created_at_is_timezone_aware(self, valid_log_data: dict) -> None:
        """created_at must be timezone-aware (UTC)."""
        entry = LogEntry(**valid_log_data)
        assert entry.created_at.tzinfo is not None

    def test_created_at_utc_timezone(self, valid_log_data: dict) -> None:
        """created_at must be in UTC."""
        entry = LogEntry(**valid_log_data)
        assert entry.created_at.tzinfo == datetime.timezone.utc

    def test_each_instance_gets_unique_datetime(self, valid_log_data: dict) -> None:
        """
        default_factory вызывается при каждом создании экземпляра,
        а не один раз при импорте модуля.
        [SRE_MARKER] — защита от бага с общим datetime для всех экземпляров.
        Если created_at будет вычислен один раз при импорте, все логи
        получат одинаковый timestamp, что сломает аудит-трейл.
        """
        entry1 = LogEntry(**valid_log_data)
        entry2 = LogEntry(**valid_log_data)
        # datetime objects must be different instances
        assert entry1.created_at is not entry2.created_at

    def test_inherits_trace_id_validation(self, valid_log_data: dict) -> None:
        """LogEntry inherits validation of trace_id."""
        with pytest.raises(ValidationError):
            LogEntry(**{**valid_log_data, "trace_id": "not-a-uuid"})

    def test_inherits_event_type_validation(self, valid_log_data: dict) -> None:
        """LogEntry inherits validation of event_type."""
        with pytest.raises(ValidationError):
            LogEntry(**{**valid_log_data, "event_type": "invalid_type"})

    def test_inherits_payload_validation(self, valid_log_data: dict) -> None:
        """LogEntry inherits validation of payload (не пустой dict)."""
        with pytest.raises(ValidationError):
            LogEntry(**{**valid_log_data, "payload": {}})

    def test_id_accepts_integer(self, valid_log_data: dict) -> None:
        """id accepts an integer."""
        entry = LogEntry(**{**valid_log_data, "id": 42})
        assert entry.id == 42

    def test_id_accepts_none(self, valid_log_data: dict) -> None:
        """id accepts None."""
        entry = LogEntry(**{**valid_log_data, "id": None})
        assert entry.id is None

    def test_model_config_from_attributes(self, full_log_data: dict) -> None:
        """
        ConfigDict(from_attributes=True) позволяет создавать модель
        из ORM-объектов (атрибуты вместо dict).
        """

        class FakeORM:
            id = 1
            trace_id = VALID_TRACE_ID
            event_type = "chat_request"
            payload = {"prompt": "Hello", "response": "Hi there"}
            created_at = datetime.datetime.now(datetime.timezone.utc)

        entry = LogEntry.model_validate(FakeORM(), from_attributes=True)
        assert entry.id == 1
        assert entry.trace_id == VALID_TRACE_ID

    def test_serialization_to_dict(self, full_log_data: dict) -> None:
        """model_dump() возвращает словарь with all fields."""
        entry = LogEntry(**full_log_data)
        data = entry.model_dump()
        assert isinstance(data, dict)
        assert "id" in data
        assert "trace_id" in data
        assert "event_type" in data
        assert "payload" in data
        assert "created_at" in data

    def test_no_update_schema_exists(self) -> None:
        """
        Architectural rule: логи иммутабельны — схемы LogEntryUpdate НЕ существует.
        [SRE_MARKER] — если кто-то добавит LogEntryUpdate, аудит-лог
        станет мутабельным, что нарушит compliance.
        """
        import app.domain.entities.log_entry as log_entry_module

        assert not hasattr(log_entry_module, "LogEntryUpdate"), (
            "LogEntryUpdate НЕ должен существовать — логи иммутабельны!"
        )

    def test_event_type_serialized_as_string(self, valid_log_data: dict) -> None:
        """При сериализации event_type должен быть строкой, а не Enum-объектом."""
        entry = LogEntry(**valid_log_data)
        data = entry.model_dump()
        assert isinstance(data["event_type"], str)
        assert data["event_type"] == "chat_request"

    def test_created_at_can_be_overridden(self, valid_log_data: dict) -> None:
        """created_at можно задать явно (например, при восстановлении из БД)."""
        fixed_time = datetime.datetime(
            2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc
        )
        entry = LogEntry(**{**valid_log_data, "created_at": fixed_time})
        assert entry.created_at == fixed_time

    def test_payload_stored_as_dict(self, valid_log_data: dict) -> None:
        """
        payload хранится как dict в доменной сущности (не как строка).
        [SRE_MARKER] — если payload станет строкой, парсинг аудит-логов сломается.
        """
        entry = LogEntry(**valid_log_data)
        assert isinstance(entry.payload, dict)
        assert len(entry.payload) > 0

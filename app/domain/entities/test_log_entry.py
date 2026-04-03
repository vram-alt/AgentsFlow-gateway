"""
TDD Red-фаза: тесты для Pydantic-моделей сущности LogEntry.

Тестируемые схемы (из log_entry.py):
  - EventType (str Enum)
  - LogEntryCreate
  - LogEntry

Архитектурное правило: логи иммутабельны — схемы Update НЕТ.
Никакого SQLAlchemy / БД — только чистая Pydantic-валидация.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# Импорт тестируемых моделей (должен упасть на Red-фазе, т.к. log_entry.py пуст)
# --------------------------------------------------------------------------
from app.domain.entities.log_entry import (
    EventType,
    LogEntry,
    LogEntryCreate,
)


# ==========================================================================
# Фикстуры
# ==========================================================================

VALID_TRACE_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"


@pytest.fixture()
def valid_log_data() -> dict:
    """Минимальный набор обязательных полей для создания записи лога."""
    return {
        "trace_id": VALID_TRACE_ID,
        "event_type": EventType.CHAT_REQUEST,
        "payload": {"prompt": "Hello", "response": "Hi there"},
    }


@pytest.fixture()
def full_log_data(valid_log_data: dict) -> dict:
    """Полный набор полей, включая id и created_at."""
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
    """Тесты для Enum EventType."""

    def test_chat_request_value(self) -> None:
        """CHAT_REQUEST имеет строковое значение 'chat_request'."""
        assert EventType.CHAT_REQUEST == "chat_request"
        assert EventType.CHAT_REQUEST.value == "chat_request"

    def test_guardrail_incident_value(self) -> None:
        """GUARDRAIL_INCIDENT имеет строковое значение 'guardrail_incident'."""
        assert EventType.GUARDRAIL_INCIDENT == "guardrail_incident"
        assert EventType.GUARDRAIL_INCIDENT.value == "guardrail_incident"

    def test_system_error_value(self) -> None:
        """SYSTEM_ERROR имеет строковое значение 'system_error'."""
        assert EventType.SYSTEM_ERROR == "system_error"
        assert EventType.SYSTEM_ERROR.value == "system_error"

    def test_exactly_three_members(self) -> None:
        """EventType содержит ровно 3 значения."""
        assert len(EventType) == 3

    def test_is_string_subclass(self) -> None:
        """EventType наследует от str — каждый член является строкой."""
        for member in EventType:
            assert isinstance(member, str)

    def test_members_list(self) -> None:
        """Все допустимые значения перечислены."""
        values = {e.value for e in EventType}
        assert values == {"chat_request", "guardrail_incident", "system_error"}

    def test_lookup_by_value(self) -> None:
        """Можно получить член Enum по строковому значению."""
        assert EventType("chat_request") is EventType.CHAT_REQUEST
        assert EventType("guardrail_incident") is EventType.GUARDRAIL_INCIDENT
        assert EventType("system_error") is EventType.SYSTEM_ERROR

    def test_invalid_value_raises(self) -> None:
        """Невалидное значение вызывает ValueError."""
        with pytest.raises(ValueError):
            EventType("unknown_event")


# ==========================================================================
# LogEntryCreate — схема для создания записи лога
# ==========================================================================


class TestLogEntryCreate:
    """LogEntryCreate: обязательные поля trace_id, event_type, payload."""

    def test_valid_creation(self, valid_log_data: dict) -> None:
        """Создание LogEntryCreate с валидными данными."""
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
        """event_type принимает строковое значение и приводит к Enum."""
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
        """trace_id — обязательное поле; без него ValidationError."""
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
        trace_id не в формате UUID отклоняется.
        [SRE_MARKER] — невалидный trace_id сломает корреляцию логов.
        """
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": "not-a-uuid"})

    def test_trace_id_too_short_rejected(self, valid_log_data: dict) -> None:
        """trace_id короче 36 символов отклоняется."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": "12345"})

    def test_trace_id_too_long_rejected(self, valid_log_data: dict) -> None:
        """trace_id длиннее 36 символов отклоняется."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": VALID_TRACE_ID + "extra"})

    def test_trace_id_without_dashes_rejected(self, valid_log_data: dict) -> None:
        """UUID без дефисов (32 hex символа) отклоняется — нужен формат с дефисами."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": uuid.uuid4().hex})

    def test_trace_id_uppercase_accepted(self, valid_log_data: dict) -> None:
        """UUID в верхнем регистре — допустимый формат (36 символов с дефисами)."""
        upper_uuid = str(uuid.uuid4()).upper()
        # Должен либо пройти, либо быть нормализован — зависит от реализации.
        # Спецификация говорит «формат UUID v4 (36 символов с дефисами)».
        entry = LogEntryCreate(**{**valid_log_data, "trace_id": upper_uuid})
        assert len(entry.trace_id) == 36

    def test_trace_id_empty_string_rejected(self, valid_log_data: dict) -> None:
        """Пустая строка trace_id отклоняется."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "trace_id": ""})

    # ------------------------------------------------------------------
    # Валидация event_type (строго из Enum)
    # ------------------------------------------------------------------

    def test_event_type_required(self) -> None:
        """event_type — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate(
                trace_id=VALID_TRACE_ID,
                payload={"key": "value"},
            )

    def test_event_type_invalid_string_rejected(self, valid_log_data: dict) -> None:
        """
        Произвольная строка для event_type отклоняется.
        [SRE_MARKER] — неизвестный тип события может обойти фильтрацию аудита.
        """
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "event_type": "unknown_event"})

    def test_event_type_none_rejected(self, valid_log_data: dict) -> None:
        """event_type не может быть None."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "event_type": None})

    def test_event_type_integer_rejected(self, valid_log_data: dict) -> None:
        """event_type не может быть числом."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "event_type": 42})

    # ------------------------------------------------------------------
    # Валидация payload (не пустой словарь)
    # ------------------------------------------------------------------

    def test_payload_required(self) -> None:
        """payload — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate(
                trace_id=VALID_TRACE_ID,
                event_type=EventType.SYSTEM_ERROR,
            )

    def test_payload_empty_dict_rejected(self, valid_log_data: dict) -> None:
        """
        Пустой словарь payload отклоняется (минимум 1 ключ).
        [SRE_MARKER] — пустой payload в аудит-логе бесполезен и может
        скрыть инцидент безопасности.
        """
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": {}})

    def test_payload_must_be_dict(self, valid_log_data: dict) -> None:
        """payload должен быть словарём, а не строкой."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": "not a dict"})

    def test_payload_list_rejected(self, valid_log_data: dict) -> None:
        """payload не может быть списком."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": [1, 2, 3]})

    def test_payload_none_rejected(self, valid_log_data: dict) -> None:
        """payload не может быть None."""
        with pytest.raises(ValidationError):
            LogEntryCreate(**{**valid_log_data, "payload": None})

    def test_payload_complex_nested_dict(self, valid_log_data: dict) -> None:
        """payload принимает сложный вложенный словарь."""
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
        """Без обязательных полей — ValidationError."""
        with pytest.raises(ValidationError):
            LogEntryCreate()


# ==========================================================================
# LogEntry — полная доменная сущность (иммутабельная запись аудита)
# ==========================================================================


class TestLogEntry:
    """LogEntry: полная сущность с id и created_at."""

    def test_valid_full_creation(self, full_log_data: dict) -> None:
        """Создание полной сущности LogEntry со всеми полями."""
        entry = LogEntry(**full_log_data)
        assert entry.id == 1
        assert entry.trace_id == VALID_TRACE_ID
        assert entry.event_type == EventType.CHAT_REQUEST
        assert entry.payload == {"prompt": "Hello", "response": "Hi there"}
        assert isinstance(entry.created_at, datetime.datetime)

    def test_id_defaults_to_none(self, valid_log_data: dict) -> None:
        """id по умолчанию None (назначается БД)."""
        entry = LogEntry(**valid_log_data)
        assert entry.id is None

    def test_created_at_auto_generated(self, valid_log_data: dict) -> None:
        """created_at генерируется автоматически через default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        entry = LogEntry(**valid_log_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert entry.created_at is not None
        assert before <= entry.created_at <= after

    def test_created_at_is_timezone_aware(self, valid_log_data: dict) -> None:
        """created_at должен быть timezone-aware (UTC)."""
        entry = LogEntry(**valid_log_data)
        assert entry.created_at.tzinfo is not None

    def test_created_at_utc_timezone(self, valid_log_data: dict) -> None:
        """created_at должен быть именно в UTC."""
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
        # Объекты datetime должны быть разными экземплярами
        assert entry1.created_at is not entry2.created_at

    def test_inherits_trace_id_validation(self, valid_log_data: dict) -> None:
        """LogEntry наследует валидацию trace_id."""
        with pytest.raises(ValidationError):
            LogEntry(**{**valid_log_data, "trace_id": "not-a-uuid"})

    def test_inherits_event_type_validation(self, valid_log_data: dict) -> None:
        """LogEntry наследует валидацию event_type."""
        with pytest.raises(ValidationError):
            LogEntry(**{**valid_log_data, "event_type": "invalid_type"})

    def test_inherits_payload_validation(self, valid_log_data: dict) -> None:
        """LogEntry наследует валидацию payload (не пустой dict)."""
        with pytest.raises(ValidationError):
            LogEntry(**{**valid_log_data, "payload": {}})

    def test_id_accepts_integer(self, valid_log_data: dict) -> None:
        """id принимает целое число."""
        entry = LogEntry(**{**valid_log_data, "id": 42})
        assert entry.id == 42

    def test_id_accepts_none(self, valid_log_data: dict) -> None:
        """id принимает None."""
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
        """model_dump() возвращает словарь со всеми полями."""
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
        Архитектурное правило: логи иммутабельны — схемы LogEntryUpdate НЕ существует.
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

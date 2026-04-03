"""
TDD Red-фаза: тесты для Pydantic-моделей сущности Policy.

Тестируемые схемы (из policy.py):
  - PolicyBase
  - PolicyCreate
  - PolicyUpdate
  - Policy

Никакого SQLAlchemy / БД — только чистая Pydantic-валидация.
"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# Импорт тестируемых моделей (должен упасть на Red-фазе, т.к. policy.py пуст)
# --------------------------------------------------------------------------
from app.domain.entities.policy import (
    Policy,
    PolicyBase,
    PolicyCreate,
    PolicyUpdate,
)


# ==========================================================================
# Фикстуры
# ==========================================================================


@pytest.fixture()
def valid_policy_data() -> dict:
    """Минимальный набор обязательных полей для создания политики."""
    return {
        "name": "Block PII",
        "body": {"type": "guardrail", "action": "deny"},
    }


@pytest.fixture()
def full_policy_data(valid_policy_data: dict) -> dict:
    """Полный набор полей, включая id, remote_id, provider_id и даты."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        **valid_policy_data,
        "id": 1,
        "remote_id": "portkey-guard-abc123",
        "provider_id": 42,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


# ==========================================================================
# PolicyBase — базовая схема
# ==========================================================================


class TestPolicyBase:
    """Тесты для PolicyBase (общие поля + валидация)."""

    def test_valid_creation(self, valid_policy_data: dict) -> None:
        """Создание с валидными данными проходит без ошибок."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.name == "Block PII"
        assert policy.body == {"type": "guardrail", "action": "deny"}

    def test_is_active_defaults_to_true(self, valid_policy_data: dict) -> None:
        """Поле is_active по умолчанию True."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.is_active is True

    def test_is_active_explicit_false(self, valid_policy_data: dict) -> None:
        """Можно явно задать is_active=False."""
        policy = PolicyBase(**{**valid_policy_data, "is_active": False})
        assert policy.is_active is False

    # ------------------------------------------------------------------
    # Валидация name
    # ------------------------------------------------------------------

    def test_name_required(self) -> None:
        """name — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            PolicyBase(body={"key": "value"})

    def test_name_empty_string_rejected(self, valid_policy_data: dict) -> None:
        """Пустая строка name отклоняется (min 1 символ)."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "name": ""})

    def test_name_whitespace_only_rejected(self, valid_policy_data: dict) -> None:
        """Строка из пробелов отклоняется после strip."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "name": "   "})

    def test_name_stripped(self, valid_policy_data: dict) -> None:
        """Пробелы по краям name удаляются (strip_whitespace)."""
        policy = PolicyBase(**{**valid_policy_data, "name": "  Block PII  "})
        assert policy.name == "Block PII"

    def test_name_max_length_200(self, valid_policy_data: dict) -> None:
        """name длиной > 200 символов отклоняется."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "name": "A" * 201})

    def test_name_exactly_200_chars(self, valid_policy_data: dict) -> None:
        """name длиной ровно 200 символов — допустимо."""
        policy = PolicyBase(**{**valid_policy_data, "name": "A" * 200})
        assert len(policy.name) == 200

    def test_name_exactly_1_char(self, valid_policy_data: dict) -> None:
        """name длиной ровно 1 символ — допустимо."""
        policy = PolicyBase(**{**valid_policy_data, "name": "X"})
        assert policy.name == "X"

    # ------------------------------------------------------------------
    # Валидация body
    # ------------------------------------------------------------------

    def test_body_required(self) -> None:
        """body — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            PolicyBase(name="Test Policy")

    def test_body_empty_dict_rejected(self, valid_policy_data: dict) -> None:
        """
        Пустой словарь body отклоняется (минимум 1 ключ).
        [SRE_MARKER] — пустая политика не должна пройти валидацию,
        иначе в облако уйдёт guardrail без правил.
        """
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": {}})

    def test_body_must_be_dict(self, valid_policy_data: dict) -> None:
        """body должен быть словарём, а не строкой или списком."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": "not a dict"})

    def test_body_list_rejected(self, valid_policy_data: dict) -> None:
        """body не может быть списком."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": [1, 2, 3]})

    def test_body_none_rejected(self, valid_policy_data: dict) -> None:
        """body не может быть None."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": None})

    def test_body_complex_nested_dict(self, valid_policy_data: dict) -> None:
        """body принимает сложный вложенный словарь."""
        complex_body = {
            "guardrails": [
                {"type": "pii", "action": "deny"},
                {"type": "toxicity", "threshold": 0.8},
            ],
            "metadata": {"version": "1.0"},
        }
        policy = PolicyBase(**{**valid_policy_data, "body": complex_body})
        assert policy.body == complex_body

    # ------------------------------------------------------------------
    # Валидация remote_id (опциональное)
    # ------------------------------------------------------------------

    def test_remote_id_defaults_to_none(self, valid_policy_data: dict) -> None:
        """remote_id по умолчанию None."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.remote_id is None

    def test_remote_id_accepts_valid_string(self, valid_policy_data: dict) -> None:
        """remote_id принимает непустую строку."""
        policy = PolicyBase(**{**valid_policy_data, "remote_id": "guard-abc123"})
        assert policy.remote_id == "guard-abc123"

    def test_remote_id_empty_string_rejected(self, valid_policy_data: dict) -> None:
        """
        Пустая строка remote_id отклоняется.
        [SRE_MARKER] — пустой remote_id может сломать синхронизацию с облаком.
        """
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "remote_id": ""})

    def test_remote_id_accepts_none(self, valid_policy_data: dict) -> None:
        """remote_id явно принимает None."""
        policy = PolicyBase(**{**valid_policy_data, "remote_id": None})
        assert policy.remote_id is None

    # ------------------------------------------------------------------
    # Валидация provider_id (опциональное)
    # ------------------------------------------------------------------

    def test_provider_id_defaults_to_none(self, valid_policy_data: dict) -> None:
        """provider_id по умолчанию None."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.provider_id is None

    def test_provider_id_accepts_integer(self, valid_policy_data: dict) -> None:
        """provider_id принимает целое число."""
        policy = PolicyBase(**{**valid_policy_data, "provider_id": 5})
        assert policy.provider_id == 5

    def test_provider_id_accepts_none(self, valid_policy_data: dict) -> None:
        """provider_id явно принимает None."""
        policy = PolicyBase(**{**valid_policy_data, "provider_id": None})
        assert policy.provider_id is None

    # ------------------------------------------------------------------
    # Типы данных
    # ------------------------------------------------------------------

    def test_wrong_type_for_is_active(self, valid_policy_data: dict) -> None:
        """Нечисловая/небулева строка для is_active вызывает ошибку."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "is_active": "not_a_bool"})


# ==========================================================================
# PolicyCreate — схема для создания
# ==========================================================================


class TestPolicyCreate:
    """PolicyCreate наследует PolicyBase; все обязательные поля должны быть."""

    def test_valid_creation(self, valid_policy_data: dict) -> None:
        """Создание PolicyCreate с валидными данными."""
        policy = PolicyCreate(**valid_policy_data)
        assert policy.name == "Block PII"
        assert policy.body == {"type": "guardrail", "action": "deny"}
        assert policy.is_active is True

    def test_inherits_validation_from_base(self) -> None:
        """Валидация name/body наследуется от PolicyBase."""
        with pytest.raises(ValidationError):
            PolicyCreate(name="", body={"key": "value"})

    def test_missing_all_fields(self) -> None:
        """Без обязательных полей — ValidationError."""
        with pytest.raises(ValidationError):
            PolicyCreate()

    def test_missing_body(self) -> None:
        """Без body — ValidationError."""
        with pytest.raises(ValidationError):
            PolicyCreate(name="Test")

    def test_missing_name(self) -> None:
        """Без name — ValidationError."""
        with pytest.raises(ValidationError):
            PolicyCreate(body={"key": "value"})

    def test_body_empty_dict_rejected(self) -> None:
        """
        Пустой body при создании отклоняется.
        [SRE_MARKER] — нельзя создать политику без правил.
        """
        with pytest.raises(ValidationError):
            PolicyCreate(name="Test", body={})

    def test_with_optional_fields(self, valid_policy_data: dict) -> None:
        """Создание с опциональными полями remote_id и provider_id."""
        policy = PolicyCreate(
            **{**valid_policy_data, "remote_id": "remote-1", "provider_id": 10}
        )
        assert policy.remote_id == "remote-1"
        assert policy.provider_id == 10


# ==========================================================================
# PolicyUpdate — схема для частичного обновления
# ==========================================================================


class TestPolicyUpdate:
    """PolicyUpdate: все поля опциональны для PATCH-обновления."""

    def test_empty_update_allowed(self) -> None:
        """Можно создать PolicyUpdate без полей (все Optional)."""
        update = PolicyUpdate()
        assert update.name is None
        assert update.body is None
        assert update.is_active is None

    def test_partial_update_name_only(self) -> None:
        """Обновление только name."""
        update = PolicyUpdate(name="New Policy Name")
        assert update.name == "New Policy Name"
        assert update.body is None

    def test_partial_update_body_only(self) -> None:
        """Обновление только body."""
        new_body = {"type": "updated_guardrail", "action": "allow"}
        update = PolicyUpdate(body=new_body)
        assert update.body == new_body
        assert update.name is None

    def test_partial_update_is_active(self) -> None:
        """Обновление только is_active."""
        update = PolicyUpdate(is_active=False)
        assert update.is_active is False

    def test_update_name_validation_still_applies(self) -> None:
        """Если name передан, валидация (max 200) всё равно работает."""
        with pytest.raises(ValidationError):
            PolicyUpdate(name="A" * 201)

    def test_update_name_empty_rejected(self) -> None:
        """Если name передан, пустая строка отклоняется."""
        with pytest.raises(ValidationError):
            PolicyUpdate(name="")

    def test_update_body_empty_dict_rejected(self) -> None:
        """
        Если body передан, пустой словарь отклоняется.
        [SRE_MARKER] — обновление политики пустым body обнулит guardrail.
        """
        with pytest.raises(ValidationError):
            PolicyUpdate(body={})

    def test_update_body_non_dict_rejected(self) -> None:
        """Если body передан, он должен быть словарём."""
        with pytest.raises(ValidationError):
            PolicyUpdate(body="not a dict")

    def test_update_body_list_rejected(self) -> None:
        """Если body передан, список отклоняется."""
        with pytest.raises(ValidationError):
            PolicyUpdate(body=[1, 2, 3])

    def test_update_name_whitespace_stripped(self) -> None:
        """Пробелы по краям name удаляются при обновлении."""
        update = PolicyUpdate(name="  Updated Name  ")
        assert update.name == "Updated Name"

    def test_update_name_whitespace_only_rejected(self) -> None:
        """Строка из пробелов для name отклоняется при обновлении."""
        with pytest.raises(ValidationError):
            PolicyUpdate(name="   ")

    def test_update_multiple_fields(self) -> None:
        """Обновление нескольких полей одновременно."""
        update = PolicyUpdate(
            name="Updated",
            body={"new": "config"},
            is_active=False,
        )
        assert update.name == "Updated"
        assert update.body == {"new": "config"}
        assert update.is_active is False


# ==========================================================================
# Policy — полная доменная сущность
# ==========================================================================


class TestPolicy:
    """Policy: полная сущность с id, created_at, updated_at."""

    def test_valid_full_creation(self, full_policy_data: dict) -> None:
        """Создание полной сущности Policy со всеми полями."""
        policy = Policy(**full_policy_data)
        assert policy.id == 1
        assert policy.name == "Block PII"
        assert policy.body == {"type": "guardrail", "action": "deny"}
        assert policy.remote_id == "portkey-guard-abc123"
        assert policy.provider_id == 42
        assert policy.is_active is True
        assert isinstance(policy.created_at, datetime.datetime)
        assert isinstance(policy.updated_at, datetime.datetime)

    def test_id_defaults_to_none(self, valid_policy_data: dict) -> None:
        """id по умолчанию None (назначается БД)."""
        policy = Policy(**valid_policy_data)
        assert policy.id is None

    def test_created_at_auto_generated(self, valid_policy_data: dict) -> None:
        """created_at генерируется автоматически через default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        policy = Policy(**valid_policy_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert policy.created_at is not None
        assert before <= policy.created_at <= after

    def test_updated_at_auto_generated(self, valid_policy_data: dict) -> None:
        """updated_at генерируется автоматически через default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        policy = Policy(**valid_policy_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert policy.updated_at is not None
        assert before <= policy.updated_at <= after

    def test_created_at_is_timezone_aware(self, valid_policy_data: dict) -> None:
        """created_at должен быть timezone-aware (UTC)."""
        policy = Policy(**valid_policy_data)
        assert policy.created_at.tzinfo is not None

    def test_updated_at_is_timezone_aware(self, valid_policy_data: dict) -> None:
        """updated_at должен быть timezone-aware (UTC)."""
        policy = Policy(**valid_policy_data)
        assert policy.updated_at.tzinfo is not None

    def test_each_instance_gets_unique_datetime(self, valid_policy_data: dict) -> None:
        """
        default_factory вызывается при каждом создании экземпляра,
        а не один раз при импорте модуля.
        [SRE_MARKER] — защита от бага с общим datetime для всех экземпляров.
        """
        policy1 = Policy(**valid_policy_data)
        policy2 = Policy(**valid_policy_data)
        # Объекты datetime должны быть разными экземплярами
        assert policy1.created_at is not policy2.created_at

    def test_inherits_base_validation(self, valid_policy_data: dict) -> None:
        """Policy наследует валидацию от PolicyBase."""
        with pytest.raises(ValidationError):
            Policy(**{**valid_policy_data, "name": ""})

    def test_inherits_body_validation(self, valid_policy_data: dict) -> None:
        """Policy наследует валидацию body от PolicyBase."""
        with pytest.raises(ValidationError):
            Policy(**{**valid_policy_data, "body": {}})

    def test_id_accepts_integer(self, valid_policy_data: dict) -> None:
        """id принимает целое число."""
        policy = Policy(**{**valid_policy_data, "id": 42})
        assert policy.id == 42

    def test_id_accepts_none(self, valid_policy_data: dict) -> None:
        """id принимает None."""
        policy = Policy(**{**valid_policy_data, "id": None})
        assert policy.id is None

    def test_model_config_from_attributes(self, full_policy_data: dict) -> None:
        """
        ConfigDict(from_attributes=True) позволяет создавать модель
        из ORM-объектов (атрибуты вместо dict).
        """

        # Имитируем ORM-объект через простой namespace
        class FakeORM:
            id = 1
            name = "Block PII"
            body = '{"type": "guardrail", "action": "deny"}'
            remote_id = "portkey-guard-abc123"
            provider_id = 42
            is_active = True
            created_at = datetime.datetime.now(datetime.timezone.utc)
            updated_at = datetime.datetime.now(datetime.timezone.utc)

        policy = Policy.model_validate(FakeORM(), from_attributes=True)
        assert policy.id == 1
        assert policy.name == "Block PII"

    def test_serialization_to_dict(self, full_policy_data: dict) -> None:
        """model_dump() возвращает словарь со всеми полями."""
        policy = Policy(**full_policy_data)
        data = policy.model_dump()
        assert isinstance(data, dict)
        assert "id" in data
        assert "name" in data
        assert "body" in data
        assert "remote_id" in data
        assert "provider_id" in data
        assert "is_active" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_remote_id_and_provider_id_optional(self, valid_policy_data: dict) -> None:
        """remote_id и provider_id опциональны в полной сущности."""
        policy = Policy(**valid_policy_data)
        assert policy.remote_id is None
        assert policy.provider_id is None

    def test_body_stored_as_dict_in_domain(self, valid_policy_data: dict) -> None:
        """
        body хранится как dict в доменной сущности (не как строка).
        [SRE_MARKER] — если body станет строкой, сериализация в облако сломается.
        """
        policy = Policy(**valid_policy_data)
        assert isinstance(policy.body, dict)
        assert len(policy.body) > 0

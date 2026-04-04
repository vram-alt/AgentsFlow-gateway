"""
TDD Red phase: тесты для Pydantic-моделей сущности Policy.

Tested schemas (из policy.py):
  - PolicyBase
  - PolicyCreate
  - PolicyUpdate
  - Policy

No SQLAlchemy / DB — pure Pydantic validation only.
"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# Import tested models (should fail during Red phase since policy.py is empty)
# --------------------------------------------------------------------------
from app.domain.entities.policy import (
    Policy,
    PolicyBase,
    PolicyCreate,
    PolicyUpdate,
)


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture()
def valid_policy_data() -> dict:
    """Minimal set of required fields for creating a policy."""
    return {
        "name": "Block PII",
        "body": {"type": "guardrail", "action": "deny"},
    }


@pytest.fixture()
def full_policy_data(valid_policy_data: dict) -> dict:
    """Full set of fields, including id, remote_id, provider_id and timestamps."""
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
    """Tests for PolicyBase (shared fields + validation)."""

    def test_valid_creation(self, valid_policy_data: dict) -> None:
        """Creation with valid data succeeds without errors."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.name == "Block PII"
        assert policy.body == {"type": "guardrail", "action": "deny"}

    def test_is_active_defaults_to_true(self, valid_policy_data: dict) -> None:
        """Field is_active defaults to True."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.is_active is True

    def test_is_active_explicit_false(self, valid_policy_data: dict) -> None:
        """Can explicitly set is_active=False."""
        policy = PolicyBase(**{**valid_policy_data, "is_active": False})
        assert policy.is_active is False

    # ------------------------------------------------------------------
    # Валидация name
    # ------------------------------------------------------------------

    def test_name_required(self) -> None:
        """name — required field; without it ValidationError."""
        with pytest.raises(ValidationError):
            PolicyBase(body={"key": "value"})

    def test_name_empty_string_rejected(self, valid_policy_data: dict) -> None:
        """Empty string name is rejected (min 1 символ)."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "name": ""})

    def test_name_whitespace_only_rejected(self, valid_policy_data: dict) -> None:
        """Whitespace-only string is rejected after strip."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "name": "   "})

    def test_name_stripped(self, valid_policy_data: dict) -> None:
        """Leading/trailing whitespace in name is stripped (strip_whitespace)."""
        policy = PolicyBase(**{**valid_policy_data, "name": "  Block PII  "})
        assert policy.name == "Block PII"

    def test_name_max_length_200(self, valid_policy_data: dict) -> None:
        """name with length > 200 символов is rejected."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "name": "A" * 201})

    def test_name_exactly_200_chars(self, valid_policy_data: dict) -> None:
        """name with exactly 200 characters — is valid."""
        policy = PolicyBase(**{**valid_policy_data, "name": "A" * 200})
        assert len(policy.name) == 200

    def test_name_exactly_1_char(self, valid_policy_data: dict) -> None:
        """name with exactly 1 символ — допустимо."""
        policy = PolicyBase(**{**valid_policy_data, "name": "X"})
        assert policy.name == "X"

    # ------------------------------------------------------------------
    # Валидация body
    # ------------------------------------------------------------------

    def test_body_required(self) -> None:
        """body — required field; without it ValidationError."""
        with pytest.raises(ValidationError):
            PolicyBase(name="Test Policy")

    def test_body_empty_dict_rejected(self, valid_policy_data: dict) -> None:
        """
        Пустой словарь body is rejected (minimum 1 key).
        [SRE_MARKER] — пустая политика не должна пройти валидацию,
        иначе в облако уйдёт guardrail без правил.
        """
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": {}})

    def test_body_must_be_dict(self, valid_policy_data: dict) -> None:
        """body must be a dict, not a string или списком."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": "not a dict"})

    def test_body_list_rejected(self, valid_policy_data: dict) -> None:
        """body cannot be a list."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": [1, 2, 3]})

    def test_body_none_rejected(self, valid_policy_data: dict) -> None:
        """body cannot be None."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "body": None})

    def test_body_complex_nested_dict(self, valid_policy_data: dict) -> None:
        """body accepts a complex nested dict."""
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
        """remote_id defaults to None."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.remote_id is None

    def test_remote_id_accepts_valid_string(self, valid_policy_data: dict) -> None:
        """remote_id accepts a non-empty string."""
        policy = PolicyBase(**{**valid_policy_data, "remote_id": "guard-abc123"})
        assert policy.remote_id == "guard-abc123"

    def test_remote_id_empty_string_rejected(self, valid_policy_data: dict) -> None:
        """
        Пустая строка remote_id is rejected.
        [SRE_MARKER] — пустой remote_id может сломать синхронизацию с облаком.
        """
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "remote_id": ""})

    def test_remote_id_accepts_none(self, valid_policy_data: dict) -> None:
        """remote_id явно accepts None."""
        policy = PolicyBase(**{**valid_policy_data, "remote_id": None})
        assert policy.remote_id is None

    # ------------------------------------------------------------------
    # Валидация provider_id (опциональное)
    # ------------------------------------------------------------------

    def test_provider_id_defaults_to_none(self, valid_policy_data: dict) -> None:
        """provider_id defaults to None."""
        policy = PolicyBase(**valid_policy_data)
        assert policy.provider_id is None

    def test_provider_id_accepts_integer(self, valid_policy_data: dict) -> None:
        """provider_id accepts an integer."""
        policy = PolicyBase(**{**valid_policy_data, "provider_id": 5})
        assert policy.provider_id == 5

    def test_provider_id_accepts_none(self, valid_policy_data: dict) -> None:
        """provider_id явно accepts None."""
        policy = PolicyBase(**{**valid_policy_data, "provider_id": None})
        assert policy.provider_id is None

    # ------------------------------------------------------------------
    # Типы данных
    # ------------------------------------------------------------------

    def test_wrong_type_for_is_active(self, valid_policy_data: dict) -> None:
        """Non-numeric/non-boolean string for is_active raises an error."""
        with pytest.raises(ValidationError):
            PolicyBase(**{**valid_policy_data, "is_active": "not_a_bool"})


# ==========================================================================
# PolicyCreate — схема для создания
# ==========================================================================


class TestPolicyCreate:
    """PolicyCreate наследует PolicyBase; все обязательные поля должны быть."""

    def test_valid_creation(self, valid_policy_data: dict) -> None:
        """Creation of PolicyCreate with valid data."""
        policy = PolicyCreate(**valid_policy_data)
        assert policy.name == "Block PII"
        assert policy.body == {"type": "guardrail", "action": "deny"}
        assert policy.is_active is True

    def test_inherits_validation_from_base(self) -> None:
        """Validation of name/body is inherited from PolicyBase."""
        with pytest.raises(ValidationError):
            PolicyCreate(name="", body={"key": "value"})

    def test_missing_all_fields(self) -> None:
        """Without required fields — ValidationError."""
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
        Пустой body при создании is rejected.
        [SRE_MARKER] — нельзя создать политику без правил.
        """
        with pytest.raises(ValidationError):
            PolicyCreate(name="Test", body={})

    def test_with_optional_fields(self, valid_policy_data: dict) -> None:
        """Creation of с опциональными полями remote_id и provider_id."""
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
        """Can create PolicyUpdate without fields (all Optional)."""
        update = PolicyUpdate()
        assert update.name is None
        assert update.body is None
        assert update.is_active is None

    def test_partial_update_name_only(self) -> None:
        """Update only name."""
        update = PolicyUpdate(name="New Policy Name")
        assert update.name == "New Policy Name"
        assert update.body is None

    def test_partial_update_body_only(self) -> None:
        """Update only body."""
        new_body = {"type": "updated_guardrail", "action": "allow"}
        update = PolicyUpdate(body=new_body)
        assert update.body == new_body
        assert update.name is None

    def test_partial_update_is_active(self) -> None:
        """Update only is_active."""
        update = PolicyUpdate(is_active=False)
        assert update.is_active is False

    def test_update_name_validation_still_applies(self) -> None:
        """If name is provided, validation (max 200) still applies."""
        with pytest.raises(ValidationError):
            PolicyUpdate(name="A" * 201)

    def test_update_name_empty_rejected(self) -> None:
        """If name передан, пустая строка is rejected."""
        with pytest.raises(ValidationError):
            PolicyUpdate(name="")

    def test_update_body_empty_dict_rejected(self) -> None:
        """
        Если body передан, пустой словарь is rejected.
        [SRE_MARKER] — обновление политики пустым body обнулит guardrail.
        """
        with pytest.raises(ValidationError):
            PolicyUpdate(body={})

    def test_update_body_non_dict_rejected(self) -> None:
        """If body передан, он must be a dict."""
        with pytest.raises(ValidationError):
            PolicyUpdate(body="not a dict")

    def test_update_body_list_rejected(self) -> None:
        """If body передан, список is rejected."""
        with pytest.raises(ValidationError):
            PolicyUpdate(body=[1, 2, 3])

    def test_update_name_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace in name is stripped при обновлении."""
        update = PolicyUpdate(name="  Updated Name  ")
        assert update.name == "Updated Name"

    def test_update_name_whitespace_only_rejected(self) -> None:
        """Whitespace-only string для name is rejected при обновлении."""
        with pytest.raises(ValidationError):
            PolicyUpdate(name="   ")

    def test_update_multiple_fields(self) -> None:
        """Update multiple fields simultaneously."""
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
        """Creation of полной сущности Policy with all fields."""
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
        """id defaults to None (assigned by DB)."""
        policy = Policy(**valid_policy_data)
        assert policy.id is None

    def test_created_at_auto_generated(self, valid_policy_data: dict) -> None:
        """created_at is auto-generated via default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        policy = Policy(**valid_policy_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert policy.created_at is not None
        assert before <= policy.created_at <= after

    def test_updated_at_auto_generated(self, valid_policy_data: dict) -> None:
        """updated_at is auto-generated via default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        policy = Policy(**valid_policy_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert policy.updated_at is not None
        assert before <= policy.updated_at <= after

    def test_created_at_is_timezone_aware(self, valid_policy_data: dict) -> None:
        """created_at must be timezone-aware (UTC)."""
        policy = Policy(**valid_policy_data)
        assert policy.created_at.tzinfo is not None

    def test_updated_at_is_timezone_aware(self, valid_policy_data: dict) -> None:
        """updated_at must be timezone-aware (UTC)."""
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
        # datetime objects must be different instances
        assert policy1.created_at is not policy2.created_at

    def test_inherits_base_validation(self, valid_policy_data: dict) -> None:
        """Policy inherits validation of от PolicyBase."""
        with pytest.raises(ValidationError):
            Policy(**{**valid_policy_data, "name": ""})

    def test_inherits_body_validation(self, valid_policy_data: dict) -> None:
        """Policy inherits validation of body от PolicyBase."""
        with pytest.raises(ValidationError):
            Policy(**{**valid_policy_data, "body": {}})

    def test_id_accepts_integer(self, valid_policy_data: dict) -> None:
        """id accepts an integer."""
        policy = Policy(**{**valid_policy_data, "id": 42})
        assert policy.id == 42

    def test_id_accepts_none(self, valid_policy_data: dict) -> None:
        """id accepts None."""
        policy = Policy(**{**valid_policy_data, "id": None})
        assert policy.id is None

    def test_model_config_from_attributes(self, full_policy_data: dict) -> None:
        """
        ConfigDict(from_attributes=True) позволяет создавать модель
        из ORM-объектов (атрибуты вместо dict).
        """

        # Simulate an ORM object via a simple namespace
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
        """model_dump() возвращает словарь with all fields."""
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

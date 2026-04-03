"""
TDD Red-фаза: тесты для Pydantic-моделей сущности Provider.

Тестируемые схемы (из provider.py):
  - ProviderBase
  - ProviderCreate
  - ProviderUpdate
  - Provider

Никакого SQLAlchemy / БД — только чистая Pydantic-валидация.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# Импорт тестируемых моделей (должен упасть на Red-фазе, т.к. provider.py пуст)
# --------------------------------------------------------------------------
from app.domain.entities.provider import (
    Provider,
    ProviderBase,
    ProviderCreate,
    ProviderUpdate,
)


# ==========================================================================
# Фикстуры
# ==========================================================================


@pytest.fixture()
def valid_provider_data() -> dict:
    """Минимальный набор обязательных полей для создания провайдера."""
    return {
        "name": "Portkey",
        "api_key": "sk-test-key-12345",
        "base_url": "https://api.portkey.ai/v1",
    }


@pytest.fixture()
def full_provider_data(valid_provider_data: dict) -> dict:
    """Полный набор полей, включая id и даты."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        **valid_provider_data,
        "id": 1,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


# ==========================================================================
# ProviderBase — базовая схема
# ==========================================================================


class TestProviderBase:
    """Тесты для ProviderBase (общие поля + валидация)."""

    def test_valid_creation(self, valid_provider_data: dict) -> None:
        """Создание с валидными данными проходит без ошибок."""
        provider = ProviderBase(**valid_provider_data)
        assert provider.name == "Portkey"
        assert provider.api_key == "sk-test-key-12345"
        assert provider.base_url == "https://api.portkey.ai/v1"

    def test_is_active_defaults_to_true(self, valid_provider_data: dict) -> None:
        """Поле is_active по умолчанию True."""
        provider = ProviderBase(**valid_provider_data)
        assert provider.is_active is True

    def test_is_active_explicit_false(self, valid_provider_data: dict) -> None:
        """Можно явно задать is_active=False."""
        provider = ProviderBase(**{**valid_provider_data, "is_active": False})
        assert provider.is_active is False

    # ------------------------------------------------------------------
    # Валидация name
    # ------------------------------------------------------------------

    def test_name_required(self) -> None:
        """name — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            ProviderBase(api_key="key", base_url="https://example.com")

    def test_name_empty_string_rejected(self, valid_provider_data: dict) -> None:
        """Пустая строка name отклоняется (min 1 символ)."""
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "name": ""})

    def test_name_whitespace_only_rejected(self, valid_provider_data: dict) -> None:
        """Строка из пробелов отклоняется после strip."""
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "name": "   "})

    def test_name_stripped(self, valid_provider_data: dict) -> None:
        """Пробелы по краям name удаляются (strip_whitespace)."""
        provider = ProviderBase(**{**valid_provider_data, "name": "  Portkey  "})
        assert provider.name == "Portkey"

    def test_name_max_length_100(self, valid_provider_data: dict) -> None:
        """name длиной > 100 символов отклоняется."""
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "name": "A" * 101})

    def test_name_exactly_100_chars(self, valid_provider_data: dict) -> None:
        """name длиной ровно 100 символов — допустимо."""
        provider = ProviderBase(**{**valid_provider_data, "name": "A" * 100})
        assert len(provider.name) == 100

    # ------------------------------------------------------------------
    # Валидация api_key
    # ------------------------------------------------------------------

    def test_api_key_required(self) -> None:
        """api_key — обязательное поле."""
        with pytest.raises(ValidationError):
            ProviderBase(name="Test", base_url="https://example.com")

    def test_api_key_empty_string_rejected(self, valid_provider_data: dict) -> None:
        """Пустая строка api_key отклоняется (min 1 символ)."""
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "api_key": ""})

    # ------------------------------------------------------------------
    # Валидация base_url
    # ------------------------------------------------------------------

    def test_base_url_required(self) -> None:
        """base_url — обязательное поле."""
        with pytest.raises(ValidationError):
            ProviderBase(name="Test", api_key="key")

    def test_base_url_must_start_with_http(self, valid_provider_data: dict) -> None:
        """base_url без http:// или https:// отклоняется."""
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "base_url": "ftp://example.com"})

    def test_base_url_must_start_with_https(self, valid_provider_data: dict) -> None:
        """base_url с https:// допустим."""
        provider = ProviderBase(
            **{**valid_provider_data, "base_url": "https://api.example.com"}
        )
        assert provider.base_url == "https://api.example.com"

    def test_base_url_http_allowed(self, valid_provider_data: dict) -> None:
        """base_url с http:// допустим."""
        provider = ProviderBase(
            **{**valid_provider_data, "base_url": "http://localhost:8080"}
        )
        assert provider.base_url == "http://localhost:8080"

    def test_base_url_plain_string_rejected(self, valid_provider_data: dict) -> None:
        """Произвольная строка без схемы отклоняется."""
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "base_url": "just-a-string"})

    # ------------------------------------------------------------------
    # Типы данных
    # ------------------------------------------------------------------

    def test_wrong_type_for_is_active(self, valid_provider_data: dict) -> None:
        """Нечисловая/небулева строка для is_active вызывает ошибку или корректно приводится."""
        # Pydantic V2 по умолчанию приводит "true"/"false" к bool, но "not_a_bool" — нет
        with pytest.raises(ValidationError):
            ProviderBase(**{**valid_provider_data, "is_active": "not_a_bool"})


# ==========================================================================
# ProviderCreate — схема для создания
# ==========================================================================


class TestProviderCreate:
    """ProviderCreate наследует ProviderBase; все обязательные поля должны быть."""

    def test_valid_creation(self, valid_provider_data: dict) -> None:
        """Создание ProviderCreate с валидными данными."""
        provider = ProviderCreate(**valid_provider_data)
        assert provider.name == "Portkey"
        assert provider.api_key == "sk-test-key-12345"
        assert provider.base_url == "https://api.portkey.ai/v1"
        assert provider.is_active is True

    def test_inherits_validation_from_base(self) -> None:
        """Валидация name/api_key/base_url наследуется от ProviderBase."""
        with pytest.raises(ValidationError):
            ProviderCreate(name="", api_key="key", base_url="https://example.com")

    def test_missing_all_fields(self) -> None:
        """Без обязательных полей — ValidationError."""
        with pytest.raises(ValidationError):
            ProviderCreate()


# ==========================================================================
# ProviderUpdate — схема для частичного обновления
# ==========================================================================


class TestProviderUpdate:
    """ProviderUpdate: все поля опциональны для PATCH-обновления."""

    def test_empty_update_allowed(self) -> None:
        """Можно создать ProviderUpdate без полей (все Optional)."""
        update = ProviderUpdate()
        assert update.name is None
        assert update.api_key is None
        assert update.base_url is None
        assert update.is_active is None

    def test_partial_update_name_only(self) -> None:
        """Обновление только name."""
        update = ProviderUpdate(name="NewName")
        assert update.name == "NewName"
        assert update.api_key is None

    def test_partial_update_is_active(self) -> None:
        """Обновление только is_active."""
        update = ProviderUpdate(is_active=False)
        assert update.is_active is False

    def test_partial_update_base_url(self) -> None:
        """Обновление только base_url."""
        update = ProviderUpdate(base_url="https://new-api.example.com")
        assert update.base_url == "https://new-api.example.com"

    def test_update_name_validation_still_applies(self) -> None:
        """Если name передан, валидация (max 100) всё равно работает."""
        with pytest.raises(ValidationError):
            ProviderUpdate(name="A" * 101)

    def test_update_base_url_validation_still_applies(self) -> None:
        """Если base_url передан, валидация (http/https) всё равно работает."""
        with pytest.raises(ValidationError):
            ProviderUpdate(base_url="ftp://bad-url.com")

    def test_update_api_key_empty_rejected(self) -> None:
        """Если api_key передан, пустая строка отклоняется."""
        with pytest.raises(ValidationError):
            ProviderUpdate(api_key="")

    def test_update_name_empty_rejected(self) -> None:
        """Если name передан, пустая строка отклоняется."""
        with pytest.raises(ValidationError):
            ProviderUpdate(name="")


# ==========================================================================
# Provider — полная доменная сущность
# ==========================================================================


class TestProvider:
    """Provider: полная сущность с id, created_at, updated_at."""

    def test_valid_full_creation(self, full_provider_data: dict) -> None:
        """Создание полной сущности Provider со всеми полями."""
        provider = Provider(**full_provider_data)
        assert provider.id == 1
        assert provider.name == "Portkey"
        assert provider.api_key == "sk-test-key-12345"
        assert provider.base_url == "https://api.portkey.ai/v1"
        assert provider.is_active is True
        assert isinstance(provider.created_at, datetime.datetime)
        assert isinstance(provider.updated_at, datetime.datetime)

    def test_id_defaults_to_none(self, valid_provider_data: dict) -> None:
        """id по умолчанию None (назначается БД)."""
        provider = Provider(**valid_provider_data)
        assert provider.id is None

    def test_created_at_auto_generated(self, valid_provider_data: dict) -> None:
        """created_at генерируется автоматически через default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        provider = Provider(**valid_provider_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert provider.created_at is not None
        assert before <= provider.created_at <= after

    def test_updated_at_auto_generated(self, valid_provider_data: dict) -> None:
        """updated_at генерируется автоматически через default_factory."""
        before = datetime.datetime.now(datetime.timezone.utc)
        provider = Provider(**valid_provider_data)
        after = datetime.datetime.now(datetime.timezone.utc)
        assert provider.updated_at is not None
        assert before <= provider.updated_at <= after

    def test_created_at_is_timezone_aware(self, valid_provider_data: dict) -> None:
        """created_at должен быть timezone-aware (UTC)."""
        provider = Provider(**valid_provider_data)
        assert provider.created_at.tzinfo is not None

    def test_updated_at_is_timezone_aware(self, valid_provider_data: dict) -> None:
        """updated_at должен быть timezone-aware (UTC)."""
        provider = Provider(**valid_provider_data)
        assert provider.updated_at.tzinfo is not None

    def test_each_instance_gets_unique_datetime(
        self, valid_provider_data: dict
    ) -> None:
        """
        default_factory вызывается при каждом создании экземпляра,
        а не один раз при импорте модуля.
        [SRE_MARKER] — защита от бага с общим datetime для всех экземпляров.
        """
        provider1 = Provider(**valid_provider_data)
        provider2 = Provider(**valid_provider_data)
        # Объекты datetime должны быть разными экземплярами
        # (хотя значения могут совпасть при быстром выполнении)
        assert provider1.created_at is not provider2.created_at

    def test_inherits_base_validation(self, valid_provider_data: dict) -> None:
        """Provider наследует валидацию от ProviderBase."""
        with pytest.raises(ValidationError):
            Provider(**{**valid_provider_data, "name": ""})

    def test_id_accepts_integer(self, valid_provider_data: dict) -> None:
        """id принимает целое число."""
        provider = Provider(**{**valid_provider_data, "id": 42})
        assert provider.id == 42

    def test_id_accepts_none(self, valid_provider_data: dict) -> None:
        """id принимает None."""
        provider = Provider(**{**valid_provider_data, "id": None})
        assert provider.id is None

    def test_model_config_from_attributes(self, full_provider_data: dict) -> None:
        """
        ConfigDict(from_attributes=True) позволяет создавать модель
        из ORM-объектов (атрибуты вместо dict).
        """

        # Имитируем ORM-объект через простой namespace
        class FakeORM:
            id = 1
            name = "Portkey"
            api_key = "sk-test-key-12345"
            base_url = "https://api.portkey.ai/v1"
            is_active = True
            created_at = datetime.datetime.now(datetime.timezone.utc)
            updated_at = datetime.datetime.now(datetime.timezone.utc)

        provider = Provider.model_validate(FakeORM(), from_attributes=True)
        assert provider.id == 1
        assert provider.name == "Portkey"

    def test_serialization_to_dict(self, full_provider_data: dict) -> None:
        """model_dump() возвращает словарь со всеми полями."""
        provider = Provider(**full_provider_data)
        data = provider.model_dump()
        assert isinstance(data, dict)
        assert "id" in data
        assert "name" in data
        assert "api_key" in data
        assert "base_url" in data
        assert "is_active" in data
        assert "created_at" in data
        assert "updated_at" in data

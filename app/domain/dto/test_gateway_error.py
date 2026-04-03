"""
TDD Red-фаза: тесты для Pydantic-модели DTO GatewayError.

Тестируемая модель (из gateway_error.py):
  - GatewayError — frozen Pydantic V2 DTO для стандартизированного
    представления ошибки при взаимодействии с провайдером.

Спецификация: gateway_error_spec.md

Никаких внешних зависимостей кроме Pydantic — только чистая валидация.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# Импорт тестируемой модели (должен упасть на Red-фазе, т.к. gateway_error.py пуст)
# --------------------------------------------------------------------------
from app.domain.dto.gateway_error import GatewayError


# ==========================================================================
# Фикстуры
# ==========================================================================


@pytest.fixture()
def valid_trace_id() -> str:
    """Валидный UUID v4 для trace_id."""
    return str(uuid.uuid4())


@pytest.fixture()
def valid_gateway_error_data(valid_trace_id: str) -> dict:
    """Минимальный набор обязательных полей для создания GatewayError."""
    return {
        "trace_id": valid_trace_id,
        "error_code": "TIMEOUT",
        "message": "Превышен таймаут ожидания ответа от провайдера",
    }


@pytest.fixture()
def full_gateway_error_data(valid_trace_id: str) -> dict:
    """Полный набор полей, включая опциональные."""
    return {
        "trace_id": valid_trace_id,
        "error_code": "PROVIDER_ERROR",
        "message": "Внутренняя ошибка на стороне провайдера",
        "status_code": 502,
        "provider_name": "portkey",
        "details": {"raw_response": "Internal Server Error", "retry_count": 3},
    }


# ==========================================================================
# GatewayError — создание с валидными данными
# ==========================================================================


class TestGatewayErrorCreation:
    """Тесты создания GatewayError с валидными данными."""

    def test_valid_minimal_creation(self, valid_gateway_error_data: dict) -> None:
        """Создание с минимальным набором обязательных полей проходит без ошибок."""
        error = GatewayError(**valid_gateway_error_data)
        assert error.trace_id == valid_gateway_error_data["trace_id"]
        assert error.error_code == "TIMEOUT"
        assert error.message == "Превышен таймаут ожидания ответа от провайдера"

    def test_valid_full_creation(self, full_gateway_error_data: dict) -> None:
        """Создание с полным набором полей проходит без ошибок."""
        error = GatewayError(**full_gateway_error_data)
        assert error.trace_id == full_gateway_error_data["trace_id"]
        assert error.error_code == "PROVIDER_ERROR"
        assert error.message == "Внутренняя ошибка на стороне провайдера"
        assert error.status_code == 502
        assert error.provider_name == "portkey"
        assert error.details == {
            "raw_response": "Internal Server Error",
            "retry_count": 3,
        }

    def test_trace_id_is_valid_uuid_v4(self, valid_gateway_error_data: dict) -> None:
        """trace_id сохраняется как строка и является валидным UUID v4."""
        error = GatewayError(**valid_gateway_error_data)
        parsed = uuid.UUID(error.trace_id, version=4)
        assert str(parsed) == error.trace_id


# ==========================================================================
# GatewayError — значения по умолчанию
# ==========================================================================


class TestGatewayErrorDefaults:
    """Тесты значений по умолчанию для опциональных полей."""

    def test_status_code_defaults_to_500(self, valid_gateway_error_data: dict) -> None:
        """status_code по умолчанию 500."""
        error = GatewayError(**valid_gateway_error_data)
        assert error.status_code == 500

    def test_provider_name_defaults_to_none(
        self, valid_gateway_error_data: dict
    ) -> None:
        """provider_name по умолчанию None."""
        error = GatewayError(**valid_gateway_error_data)
        assert error.provider_name is None

    def test_details_defaults_to_empty_dict(
        self, valid_gateway_error_data: dict
    ) -> None:
        """details по умолчанию пустой словарь."""
        error = GatewayError(**valid_gateway_error_data)
        assert error.details == {}
        assert isinstance(error.details, dict)

    def test_details_default_is_not_shared_between_instances(
        self, valid_gateway_error_data: dict
    ) -> None:
        """
        [SRE_MARKER] — default_factory для details: каждый экземпляр
        получает свой собственный пустой словарь, а не общий мутабельный объект.
        """
        error1 = GatewayError(**valid_gateway_error_data)
        error2 = GatewayError(**valid_gateway_error_data)
        assert error1.details is not error2.details


# ==========================================================================
# GatewayError — frozen (неизменяемость)
# ==========================================================================


class TestGatewayErrorFrozen:
    """Тесты неизменяемости (frozen) модели."""

    def test_cannot_modify_trace_id(self, valid_gateway_error_data: dict) -> None:
        """Попытка изменить trace_id вызывает ошибку (frozen model)."""
        error = GatewayError(**valid_gateway_error_data)
        with pytest.raises(ValidationError):
            error.trace_id = str(uuid.uuid4())

    def test_cannot_modify_error_code(self, valid_gateway_error_data: dict) -> None:
        """Попытка изменить error_code вызывает ошибку (frozen model)."""
        error = GatewayError(**valid_gateway_error_data)
        with pytest.raises(ValidationError):
            error.error_code = "AUTH_FAILED"

    def test_cannot_modify_message(self, valid_gateway_error_data: dict) -> None:
        """Попытка изменить message вызывает ошибку (frozen model)."""
        error = GatewayError(**valid_gateway_error_data)
        with pytest.raises(ValidationError):
            error.message = "Новое сообщение"

    def test_cannot_modify_status_code(self, valid_gateway_error_data: dict) -> None:
        """Попытка изменить status_code вызывает ошибку (frozen model)."""
        error = GatewayError(**valid_gateway_error_data)
        with pytest.raises(ValidationError):
            error.status_code = 404

    def test_cannot_modify_provider_name(self, full_gateway_error_data: dict) -> None:
        """Попытка изменить provider_name вызывает ошибку (frozen model)."""
        error = GatewayError(**full_gateway_error_data)
        with pytest.raises(ValidationError):
            error.provider_name = "openai"

    def test_cannot_modify_details(self, full_gateway_error_data: dict) -> None:
        """Попытка заменить details вызывает ошибку (frozen model)."""
        error = GatewayError(**full_gateway_error_data)
        with pytest.raises(ValidationError):
            error.details = {"new": "data"}


# ==========================================================================
# GatewayError — валидация trace_id (UUID v4)
# ==========================================================================


class TestGatewayErrorTraceIdValidation:
    """Тесты валидации поля trace_id."""

    def test_trace_id_required(self) -> None:
        """trace_id — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError(error_code="TIMEOUT", message="Timeout")

    def test_trace_id_empty_string_rejected(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Пустая строка trace_id отклоняется."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "trace_id": ""})

    def test_trace_id_invalid_uuid_rejected(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Невалидный UUID отклоняется."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "trace_id": "not-a-uuid"})

    def test_trace_id_uuid_v1_rejected(self, valid_gateway_error_data: dict) -> None:
        """
        [SRE_MARKER] — UUID v1 содержит MAC-адрес и временную метку,
        что может привести к утечке информации. Только UUID v4 допустим.
        """
        uuid_v1 = str(uuid.uuid1())
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "trace_id": uuid_v1})

    def test_trace_id_valid_uuid_v4_accepted(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Валидный UUID v4 принимается."""
        valid_uuid = str(uuid.uuid4())
        error = GatewayError(**{**valid_gateway_error_data, "trace_id": valid_uuid})
        assert error.trace_id == valid_uuid


# ==========================================================================
# GatewayError — валидация error_code
# ==========================================================================


class TestGatewayErrorCodeValidation:
    """Тесты валидации поля error_code."""

    def test_error_code_required(self, valid_trace_id: str) -> None:
        """error_code — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError(trace_id=valid_trace_id, message="Some error")

    def test_error_code_empty_string_rejected(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Пустая строка error_code отклоняется."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "error_code": ""})

    def test_error_code_accepts_standard_codes(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Стандартные коды ошибок принимаются."""
        standard_codes = [
            "TIMEOUT",
            "AUTH_FAILED",
            "PROVIDER_ERROR",
            "VALIDATION_ERROR",
            "RATE_LIMITED",
            "UNKNOWN",
        ]
        for code in standard_codes:
            error = GatewayError(**{**valid_gateway_error_data, "error_code": code})
            assert error.error_code == code

    def test_error_code_accepts_custom_codes(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Произвольные непустые строки также принимаются как error_code."""
        error = GatewayError(
            **{**valid_gateway_error_data, "error_code": "CUSTOM_ERROR"}
        )
        assert error.error_code == "CUSTOM_ERROR"


# ==========================================================================
# GatewayError — валидация message
# ==========================================================================


class TestGatewayErrorMessageValidation:
    """Тесты валидации поля message."""

    def test_message_required(self, valid_trace_id: str) -> None:
        """message — обязательное поле; без него ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError(trace_id=valid_trace_id, error_code="TIMEOUT")

    def test_message_empty_string_rejected(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Пустая строка message отклоняется."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "message": ""})

    def test_message_accepts_long_text(self, valid_gateway_error_data: dict) -> None:
        """Длинное сообщение принимается."""
        long_message = "Ошибка " * 500
        error = GatewayError(**{**valid_gateway_error_data, "message": long_message})
        assert error.message == long_message


# ==========================================================================
# GatewayError — валидация status_code
# ==========================================================================


class TestGatewayErrorStatusCodeValidation:
    """Тесты валидации поля status_code."""

    def test_status_code_400_accepted(self, valid_gateway_error_data: dict) -> None:
        """Нижняя граница диапазона [400, 599] — 400 принимается."""
        error = GatewayError(**{**valid_gateway_error_data, "status_code": 400})
        assert error.status_code == 400

    def test_status_code_599_accepted(self, valid_gateway_error_data: dict) -> None:
        """Верхняя граница диапазона [400, 599] — 599 принимается."""
        error = GatewayError(**{**valid_gateway_error_data, "status_code": 599})
        assert error.status_code == 599

    def test_status_code_500_accepted(self, valid_gateway_error_data: dict) -> None:
        """Типичный серверный код 500 принимается."""
        error = GatewayError(**{**valid_gateway_error_data, "status_code": 500})
        assert error.status_code == 500

    def test_status_code_399_rejected(self, valid_gateway_error_data: dict) -> None:
        """
        [SRE_MARKER] — status_code < 400 отклоняется.
        Коды 2xx/3xx не являются ошибками и не должны попадать в GatewayError.
        """
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "status_code": 399})

    def test_status_code_200_rejected(self, valid_gateway_error_data: dict) -> None:
        """
        [SRE_MARKER] — status_code 200 (успех) не должен быть в GatewayError.
        Это защита от логической ошибки, когда успешный ответ маскируется под ошибку.
        """
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "status_code": 200})

    def test_status_code_600_rejected(self, valid_gateway_error_data: dict) -> None:
        """status_code > 599 отклоняется (нет таких HTTP-кодов)."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "status_code": 600})

    def test_status_code_0_rejected(self, valid_gateway_error_data: dict) -> None:
        """status_code = 0 отклоняется."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "status_code": 0})

    def test_status_code_negative_rejected(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Отрицательный status_code отклоняется."""
        with pytest.raises(ValidationError):
            GatewayError(**{**valid_gateway_error_data, "status_code": -1})

    def test_status_code_common_client_errors(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Типичные клиентские коды ошибок (401, 403, 404, 429) принимаются."""
        for code in [401, 403, 404, 429]:
            error = GatewayError(**{**valid_gateway_error_data, "status_code": code})
            assert error.status_code == code

    def test_status_code_common_server_errors(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Типичные серверные коды ошибок (500, 502, 503, 504) принимаются."""
        for code in [500, 502, 503, 504]:
            error = GatewayError(**{**valid_gateway_error_data, "status_code": code})
            assert error.status_code == code


# ==========================================================================
# GatewayError — валидация provider_name
# ==========================================================================


class TestGatewayErrorProviderNameValidation:
    """Тесты валидации поля provider_name."""

    def test_provider_name_none_accepted(self, valid_gateway_error_data: dict) -> None:
        """provider_name = None допустимо (по умолчанию)."""
        error = GatewayError(**{**valid_gateway_error_data, "provider_name": None})
        assert error.provider_name is None

    def test_provider_name_string_accepted(
        self, valid_gateway_error_data: dict
    ) -> None:
        """provider_name как строка принимается."""
        error = GatewayError(**{**valid_gateway_error_data, "provider_name": "portkey"})
        assert error.provider_name == "portkey"

    def test_provider_name_omitted_defaults_to_none(
        self, valid_gateway_error_data: dict
    ) -> None:
        """Если provider_name не передан, по умолчанию None."""
        error = GatewayError(**valid_gateway_error_data)
        assert error.provider_name is None


# ==========================================================================
# GatewayError — валидация details
# ==========================================================================


class TestGatewayErrorDetailsValidation:
    """Тесты валидации поля details."""

    def test_details_accepts_dict(self, valid_gateway_error_data: dict) -> None:
        """details принимает словарь."""
        error = GatewayError(
            **{**valid_gateway_error_data, "details": {"key": "value"}}
        )
        assert error.details == {"key": "value"}

    def test_details_accepts_nested_dict(self, valid_gateway_error_data: dict) -> None:
        """details принимает вложенный словарь."""
        nested = {"level1": {"level2": {"level3": "deep"}}}
        error = GatewayError(**{**valid_gateway_error_data, "details": nested})
        assert error.details == nested

    def test_details_accepts_empty_dict(self, valid_gateway_error_data: dict) -> None:
        """details принимает пустой словарь."""
        error = GatewayError(**{**valid_gateway_error_data, "details": {}})
        assert error.details == {}


# ==========================================================================
# GatewayError — стандартные коды ошибок (константы)
# ==========================================================================


class TestGatewayErrorConstants:
    """Тесты наличия стандартных констант кодов ошибок."""

    def test_timeout_constant_exists(self) -> None:
        """Константа TIMEOUT определена."""
        assert hasattr(GatewayError, "TIMEOUT")
        assert GatewayError.TIMEOUT == "TIMEOUT"

    def test_auth_failed_constant_exists(self) -> None:
        """Константа AUTH_FAILED определена."""
        assert hasattr(GatewayError, "AUTH_FAILED")
        assert GatewayError.AUTH_FAILED == "AUTH_FAILED"

    def test_provider_error_constant_exists(self) -> None:
        """Константа PROVIDER_ERROR определена."""
        assert hasattr(GatewayError, "PROVIDER_ERROR")
        assert GatewayError.PROVIDER_ERROR == "PROVIDER_ERROR"

    def test_validation_error_constant_exists(self) -> None:
        """Константа VALIDATION_ERROR определена."""
        assert hasattr(GatewayError, "VALIDATION_ERROR")
        assert GatewayError.VALIDATION_ERROR == "VALIDATION_ERROR"

    def test_rate_limited_constant_exists(self) -> None:
        """Константа RATE_LIMITED определена."""
        assert hasattr(GatewayError, "RATE_LIMITED")
        assert GatewayError.RATE_LIMITED == "RATE_LIMITED"

    def test_unknown_constant_exists(self) -> None:
        """Константа UNKNOWN определена."""
        assert hasattr(GatewayError, "UNKNOWN")
        assert GatewayError.UNKNOWN == "UNKNOWN"


# ==========================================================================
# GatewayError — использование как DTO (не исключение)
# ==========================================================================


class TestGatewayErrorIsDTO:
    """Тесты подтверждающие, что GatewayError — DTO, а не исключение."""

    def test_is_not_exception(self, valid_gateway_error_data: dict) -> None:
        """
        [SRE_MARKER] — GatewayError НЕ является исключением.
        Это DTO для передачи данных между слоями. Если бы он наследовал Exception,
        это нарушило бы контракт единообразной обработки ошибок через проверку типа.
        """
        error = GatewayError(**valid_gateway_error_data)
        assert not isinstance(error, Exception)
        assert not isinstance(error, BaseException)

    def test_is_pydantic_base_model(self, valid_gateway_error_data: dict) -> None:
        """GatewayError наследует от pydantic.BaseModel."""
        from pydantic import BaseModel

        error = GatewayError(**valid_gateway_error_data)
        assert isinstance(error, BaseModel)


# ==========================================================================
# GatewayError — сериализация
# ==========================================================================


class TestGatewayErrorSerialization:
    """Тесты сериализации модели."""

    def test_model_dump_returns_dict(self, full_gateway_error_data: dict) -> None:
        """model_dump() возвращает словарь со всеми полями."""
        error = GatewayError(**full_gateway_error_data)
        data = error.model_dump()
        assert isinstance(data, dict)
        assert "trace_id" in data
        assert "error_code" in data
        assert "message" in data
        assert "status_code" in data
        assert "provider_name" in data
        assert "details" in data

    def test_model_dump_values_match(self, full_gateway_error_data: dict) -> None:
        """model_dump() возвращает корректные значения."""
        error = GatewayError(**full_gateway_error_data)
        data = error.model_dump()
        assert data["trace_id"] == full_gateway_error_data["trace_id"]
        assert data["error_code"] == "PROVIDER_ERROR"
        assert data["message"] == "Внутренняя ошибка на стороне провайдера"
        assert data["status_code"] == 502
        assert data["provider_name"] == "portkey"
        assert data["details"] == {
            "raw_response": "Internal Server Error",
            "retry_count": 3,
        }

    def test_model_dump_json_returns_string(
        self, valid_gateway_error_data: dict
    ) -> None:
        """model_dump_json() возвращает JSON-строку."""
        error = GatewayError(**valid_gateway_error_data)
        json_str = error.model_dump_json()
        assert isinstance(json_str, str)
        assert valid_gateway_error_data["trace_id"] in json_str


# ==========================================================================
# GatewayError — обязательные поля отсутствуют
# ==========================================================================


class TestGatewayErrorMissingRequiredFields:
    """Тесты на отсутствие обязательных полей."""

    def test_missing_all_fields(self) -> None:
        """Без обязательных полей — ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError()

    def test_missing_trace_id(self) -> None:
        """Без trace_id — ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError(error_code="TIMEOUT", message="Timeout")

    def test_missing_error_code(self, valid_trace_id: str) -> None:
        """Без error_code — ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError(trace_id=valid_trace_id, message="Timeout")

    def test_missing_message(self, valid_trace_id: str) -> None:
        """Без message — ValidationError."""
        with pytest.raises(ValidationError):
            GatewayError(trace_id=valid_trace_id, error_code="TIMEOUT")

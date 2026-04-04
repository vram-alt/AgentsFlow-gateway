"""
TDD Red-phase тесты для Pydantic V2 схем модуля Testing Console.

Спецификация: app/api/schemas/tester_spec.md

Все тесты ДОЛЖНЫ падать на Red-фазе, пока схемы не реализованы
(tester.py пуст).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

# ── Импорт тестируемых схем (упадёт на Red-фазе) ────────────────────────
from app.api.schemas.tester import (
    TesterErrorResponse,
    TesterProxyRequest,
    TesterProxyResponse,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. TesterProxyRequest — базовая валидация полей (§1)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyRequestBasic:
    """Базовые тесты полей TesterProxyRequest (§1)."""

    def test_minimal_valid_request(self):
        """Минимальный валидный запрос — только provider_name."""
        req = TesterProxyRequest(provider_name="portkey")
        assert req.provider_name == "portkey"

    def test_default_method_is_post(self):
        """method по умолчанию = 'POST'."""
        req = TesterProxyRequest(provider_name="portkey")
        assert req.method == "POST"

    def test_default_path_is_chat_completions(self):
        """path по умолчанию = '/chat/completions'."""
        req = TesterProxyRequest(provider_name="portkey")
        assert req.path == "/chat/completions"

    def test_default_body_is_none(self):
        """body по умолчанию = None."""
        req = TesterProxyRequest(provider_name="portkey")
        assert req.body is None

    def test_default_headers_is_none(self):
        """headers по умолчанию = None."""
        req = TesterProxyRequest(provider_name="portkey")
        assert req.headers is None

    def test_full_valid_request(self):
        """Полный валидный запрос со всеми полями."""
        req = TesterProxyRequest(
            provider_name="portkey",
            method="PUT",
            path="/v1/models",
            body={"model": "gpt-4"},
            headers={"Accept": "application/json"},
        )
        assert req.provider_name == "portkey"
        assert req.method == "PUT"
        assert req.path == "/v1/models"
        assert req.body == {"model": "gpt-4"}
        assert req.headers == {"Accept": "application/json"}

    def test_provider_name_required(self):
        """provider_name обязательно — без него ValidationError."""
        with pytest.raises(ValidationError):
            TesterProxyRequest()

    def test_provider_name_min_length(self):
        """provider_name не может быть пустой строкой (min_length=1)."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="")


# ═══════════════════════════════════════════════════════════════════════════
# 2. TesterProxyRequest — валидация method (§1)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyRequestMethod:
    """Валидация поля method (§1)."""

    @pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
    def test_valid_methods_uppercase(self, method: str):
        """Допустимые методы в верхнем регистре принимаются."""
        req = TesterProxyRequest(provider_name="portkey", method=method)
        assert req.method == method

    @pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
    def test_valid_methods_lowercase_normalized_to_upper(self, method: str):
        """Методы в нижнем регистре приводятся к верхнему."""
        req = TesterProxyRequest(provider_name="portkey", method=method)
        assert req.method == method.upper()

    @pytest.mark.parametrize("method", ["Get", "Post", "pUt", "DeLeTe"])
    def test_valid_methods_mixed_case_normalized(self, method: str):
        """Методы в смешанном регистре приводятся к верхнему."""
        req = TesterProxyRequest(provider_name="portkey", method=method)
        assert req.method == method.upper()

    @pytest.mark.parametrize("method", ["PATCH", "OPTIONS", "HEAD", "TRACE", "CONNECT"])
    def test_invalid_methods_rejected(self, method: str):
        """Недопустимые HTTP-методы отклоняются."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="portkey", method=method)

    def test_empty_method_rejected(self):
        """Пустая строка method отклоняется."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="portkey", method="")


# ═══════════════════════════════════════════════════════════════════════════
# 3. TesterProxyRequest — валидация path (§1.1) [SRE_MARKER]
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyRequestPathValidation:
    """[SRE_MARKER] Валидация path: SSRF, path traversal, абсолютные URL (§1.1)."""

    def test_valid_path_accepted(self):
        """Обычный путь принимается."""
        req = TesterProxyRequest(provider_name="portkey", path="/v1/chat/completions")
        assert req.path == "/v1/chat/completions"

    def test_path_traversal_rejected(self):
        """[SRE_MARKER] Path traversal через '..' отклоняется."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="portkey", path="/../../etc/passwd")

    def test_path_traversal_double_dot_in_middle(self):
        """[SRE_MARKER] '..' в середине пути отклоняется."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="portkey", path="/v1/../admin/secrets")

    def test_absolute_url_rejected(self):
        """[SRE_MARKER] Абсолютный URL (содержит '://') отклоняется."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="portkey", path="https://evil.com/steal")

    def test_percent_encoded_path_traversal_rejected(self):
        """[SRE_MARKER] Percent-encoded path traversal (%2e%2e) отклоняется после URL-декодирования."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(
                provider_name="portkey", path="/%2e%2e/%2e%2e/etc/passwd"
            )

    def test_percent_encoded_absolute_url_rejected(self):
        """[SRE_MARKER] Percent-encoded '://' (%3A%2F%2F) отклоняется после URL-декодирования."""
        with pytest.raises(ValidationError):
            TesterProxyRequest(
                provider_name="portkey", path="http%3A%2F%2Fevil.com/steal"
            )

    def test_double_encoded_path_traversal_rejected(self):
        """[SRE_MARKER] Двойное кодирование '..' (%252e%252e) — после одного декодирования содержит %2e%2e."""
        # После URL-декодирования: %2e%2e → '..' — должно быть отклонено
        with pytest.raises(ValidationError):
            TesterProxyRequest(provider_name="portkey", path="/%252e%252e/etc/passwd")


# ═══════════════════════════════════════════════════════════════════════════
# 4. TesterProxyRequest — валидация body (§1.2) [SRE_MARKER]
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyRequestBodyValidation:
    """[SRE_MARKER] Ограничение размера body (§1.2)."""

    def test_small_body_accepted(self):
        """Маленькое тело запроса принимается."""
        req = TesterProxyRequest(
            provider_name="portkey",
            body={"model": "gpt-4", "messages": [{"role": "user", "content": "Hi"}]},
        )
        assert req.body is not None

    def test_body_none_accepted(self):
        """body=None допустимо."""
        req = TesterProxyRequest(provider_name="portkey", body=None)
        assert req.body is None

    def test_body_exceeding_1mb_rejected(self):
        """[SRE_MARKER] Тело > 1 МБ отклоняется с ошибкой 'Request body too large (max 1MB)'."""
        # Создаём словарь, сериализация которого > 1 МБ
        large_body = {"data": "x" * (1_048_576 + 1)}
        with pytest.raises(ValidationError, match="Request body too large"):
            TesterProxyRequest(provider_name="portkey", body=large_body)

    def test_body_exactly_1mb_accepted(self):
        """Тело ровно 1 МБ (или чуть меньше) принимается."""
        # Создаём строку, чтобы JSON-сериализация была < 1 МБ
        # {"data": "xxx..."} — overhead ~10 байт
        safe_size = 1_048_576 - 20
        body = {"data": "x" * safe_size}
        serialized = json.dumps(body).encode("utf-8")
        if len(serialized) <= 1_048_576:
            req = TesterProxyRequest(provider_name="portkey", body=body)
            assert req.body is not None


# ═══════════════════════════════════════════════════════════════════════════
# 5. TesterProxyRequest — валидация headers (§1.3) [SRE_MARKER]
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyRequestHeadersValidation:
    """[SRE_MARKER] Ограничение количества и длины headers (§1.3)."""

    def test_valid_headers_accepted(self):
        """Допустимые заголовки принимаются."""
        req = TesterProxyRequest(
            provider_name="portkey",
            headers={"Accept": "application/json", "X-Custom-Id": "123"},
        )
        assert req.headers is not None

    def test_headers_none_accepted(self):
        """headers=None допустимо."""
        req = TesterProxyRequest(provider_name="portkey", headers=None)
        assert req.headers is None

    def test_too_many_headers_rejected(self):
        """[SRE_MARKER] Более 20 заголовков отклоняется."""
        headers = {f"X-Header-{i}": f"value-{i}" for i in range(21)}
        with pytest.raises(ValidationError, match="Too many headers"):
            TesterProxyRequest(provider_name="portkey", headers=headers)

    def test_exactly_20_headers_accepted(self):
        """Ровно 20 заголовков принимается."""
        headers = {f"X-Header-{i}": f"value-{i}" for i in range(20)}
        req = TesterProxyRequest(provider_name="portkey", headers=headers)
        assert len(req.headers) == 20

    def test_header_name_too_long_rejected(self):
        """[SRE_MARKER] Ключ заголовка > 128 символов отклоняется."""
        headers = {"X" * 129: "value"}
        with pytest.raises(ValidationError, match="Header name too long"):
            TesterProxyRequest(provider_name="portkey", headers=headers)

    def test_header_name_exactly_128_accepted(self):
        """Ключ заголовка ровно 128 символов принимается."""
        headers = {"X" * 128: "value"}
        req = TesterProxyRequest(provider_name="portkey", headers=headers)
        assert req.headers is not None

    def test_header_value_too_long_rejected(self):
        """[SRE_MARKER] Значение заголовка > 4096 символов отклоняется."""
        headers = {"Accept": "v" * 4097}
        with pytest.raises(ValidationError, match="Header value too long"):
            TesterProxyRequest(provider_name="portkey", headers=headers)

    def test_header_value_exactly_4096_accepted(self):
        """Значение заголовка ровно 4096 символов принимается."""
        headers = {"Accept": "v" * 4096}
        req = TesterProxyRequest(provider_name="portkey", headers=headers)
        assert req.headers is not None


# ═══════════════════════════════════════════════════════════════════════════
# 6. TesterProxyResponse (§2)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterProxyResponse:
    """Тесты схемы TesterProxyResponse (§2)."""

    def test_valid_response(self):
        """Полный валидный ответ."""
        resp = TesterProxyResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body={"choices": [{"message": {"content": "Hello"}}]},
            latency_ms=123.45,
        )
        assert resp.status_code == 200
        assert resp.headers == {"content-type": "application/json"}
        assert resp.latency_ms == 123.45

    def test_body_can_be_dict(self):
        """body может быть словарём."""
        resp = TesterProxyResponse(
            status_code=200,
            headers={},
            body={"key": "value"},
            latency_ms=10.0,
        )
        assert isinstance(resp.body, dict)

    def test_body_can_be_list(self):
        """body может быть списком."""
        resp = TesterProxyResponse(
            status_code=200,
            headers={},
            body=[1, 2, 3],
            latency_ms=10.0,
        )
        assert isinstance(resp.body, list)

    def test_body_can_be_string(self):
        """body может быть строкой (сырой текст)."""
        resp = TesterProxyResponse(
            status_code=200,
            headers={},
            body="raw text response",
            latency_ms=10.0,
        )
        assert isinstance(resp.body, str)

    def test_all_fields_required(self):
        """Все поля обязательны — без них ValidationError."""
        with pytest.raises(ValidationError):
            TesterProxyResponse()

    def test_missing_latency_ms_rejected(self):
        """Отсутствие latency_ms → ValidationError."""
        with pytest.raises(ValidationError):
            TesterProxyResponse(
                status_code=200,
                headers={},
                body={},
            )


# ═══════════════════════════════════════════════════════════════════════════
# 7. TesterErrorResponse (§3)
# ═══════════════════════════════════════════════════════════════════════════


class TestTesterErrorResponse:
    """Тесты схемы TesterErrorResponse (§3)."""

    def test_valid_error_response(self):
        """Полный валидный ответ об ошибке."""
        err = TesterErrorResponse(
            trace_id="123e4567-e89b-42d3-a456-426614174000",
            error_code="PROVIDER_NOT_FOUND",
            message="Provider 'openai' not found",
        )
        assert err.trace_id == "123e4567-e89b-42d3-a456-426614174000"
        assert err.error_code == "PROVIDER_NOT_FOUND"
        assert err.message == "Provider 'openai' not found"

    def test_all_fields_required(self):
        """Все поля обязательны."""
        with pytest.raises(ValidationError):
            TesterErrorResponse()

    def test_missing_trace_id_rejected(self):
        """Отсутствие trace_id → ValidationError."""
        with pytest.raises(ValidationError):
            TesterErrorResponse(
                error_code="INTERNAL_ERROR",
                message="Something went wrong",
            )

    def test_missing_error_code_rejected(self):
        """Отсутствие error_code → ValidationError."""
        with pytest.raises(ValidationError):
            TesterErrorResponse(
                trace_id="123e4567-e89b-42d3-a456-426614174000",
                message="Something went wrong",
            )

    def test_missing_message_rejected(self):
        """Отсутствие message → ValidationError."""
        with pytest.raises(ValidationError):
            TesterErrorResponse(
                trace_id="123e4567-e89b-42d3-a456-426614174000",
                error_code="INTERNAL_ERROR",
            )

    @pytest.mark.parametrize(
        "error_code",
        [
            "PROVIDER_NOT_FOUND",
            "PROXY_TIMEOUT",
            "PROXY_CONNECTION_ERROR",
            "VALIDATION_ERROR",
            "INTERNAL_ERROR",
            "RESPONSE_TOO_LARGE",
        ],
    )
    def test_all_error_codes_accepted(self, error_code: str):
        """Все коды ошибок из спецификации принимаются."""
        err = TesterErrorResponse(
            trace_id="123e4567-e89b-42d3-a456-426614174000",
            error_code=error_code,
            message="Test error",
        )
        assert err.error_code == error_code

"""
TDD Red-phase tests for POST /api/webhook router.

Based on: app/api/routes/webhook_spec.md
These tests MUST fail until the router is implemented.

Covers:
  - Successful webhook receipt (HTTP 200)
  - Auth via X-Webhook-Secret header (HTTP 401)
  - Payload validation (HTTP 422)
  - Payload size limit (HTTP 413)
  - JSON nesting depth limit (HTTP 422)
  - [SRE_MARKER] Service error status still returns HTTP 200
  - [SRE_MARKER] Internal exception → HTTP 500
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# --- Imports that will fail until modules are wired ---
from app.main import app
from app.services.webhook_service import WebhookService
from app.api.dependencies.di import get_webhook_service


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SECRET = "super-secret-webhook-token-1234"
WEBHOOK_URL = "/api/webhook"

VALID_PAYLOAD = {
    "trace_id": "123e4567-e89b-42d3-a456-426614174000",
    "event": "guardrail_triggered",
    "rule": "content_filter",
    "severity": "high",
    "blocked": True,
}

SERVICE_ACCEPTED_RESPONSE = {
    "status": "accepted",
    "trace_id": "123e4567-e89b-42d3-a456-426614174000",
    "linked_to_prompt": False,
}

SERVICE_ERROR_RESPONSE = {
    "status": "error",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_nested_dict(depth: int) -> dict:
    """Build a dict nested to the given depth level."""
    result: dict = {"level": depth}
    current = result
    for i in range(depth - 1):
        child: dict = {"level": depth - i - 1}
        current["nested"] = child
        current = child
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_webhook_service() -> AsyncMock:
    """Create an AsyncMock of WebhookService."""
    svc = AsyncMock(spec=WebhookService)
    svc.process_guardrail_incident.return_value = SERVICE_ACCEPTED_RESPONSE
    return svc


@pytest.fixture()
def client(mock_webhook_service: AsyncMock) -> TestClient:
    """
    Build a TestClient with WebhookService overridden via dependency_overrides.
    Also patches WEBHOOK_SECRET in settings so auth checks pass.
    """
    app.dependency_overrides[get_webhook_service] = lambda: mock_webhook_service

    with patch("app.api.routes.webhook.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.webhook_secret = VALID_SECRET
        yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_secret_patch(mock_webhook_service: AsyncMock) -> TestClient:
    """
    TestClient WITHOUT patching settings — for testing missing/wrong secret.
    Uses a known secret value via patch.
    """
    app.dependency_overrides[get_webhook_service] = lambda: mock_webhook_service

    with patch("app.api.routes.webhook.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.webhook_secret = VALID_SECRET
        yield TestClient(app)

    app.dependency_overrides.clear()


# ===========================================================================
# 1. Успешный приём webhook — HTTP 200
# ===========================================================================


class TestWebhookSuccess:
    """POST /api/webhook → 200 OK при валидном запросе."""

    def test_returns_200_with_valid_payload(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Валидный payload + правильный X-Webhook-Secret → HTTP 200."""
        response = client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 200

    def test_response_body_contains_service_result(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Тело ответа содержит результат от WebhookService."""
        response = client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        body = response.json()
        assert body["status"] == "accepted"
        assert body["trace_id"] == "123e4567-e89b-42d3-a456-426614174000"

    def test_service_called_with_payload(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """WebhookService.process_guardrail_incident вызывается с переданным payload."""
        client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        mock_webhook_service.process_guardrail_incident.assert_called_once_with(
            VALID_PAYLOAD
        )

    def test_returns_200_with_minimal_payload(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Минимальный валидный JSON-объект (свободная структура) → HTTP 200."""
        minimal = {"event": "test"}
        mock_webhook_service.process_guardrail_incident.return_value = {
            "status": "accepted",
            "trace_id": "abc",
            "linked_to_prompt": False,
        }

        response = client.post(
            WEBHOOK_URL,
            json=minimal,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 200


# ===========================================================================
# 2. Аутентификация — X-Webhook-Secret (HTTP 401)
# ===========================================================================


class TestWebhookAuth:
    """POST /api/webhook → 401 Unauthorized при невалидном/отсутствующем токене."""

    def test_missing_secret_header_returns_401(
        self, client_no_secret_patch: TestClient
    ):
        """Отсутствие заголовка X-Webhook-Secret → HTTP 401."""
        response = client_no_secret_patch.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
        )

        assert response.status_code == 401

    def test_wrong_secret_returns_401(self, client_no_secret_patch: TestClient):
        """Неправильный X-Webhook-Secret → HTTP 401."""
        response = client_no_secret_patch.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": "wrong-secret-value"},
        )

        assert response.status_code == 401

    def test_empty_secret_returns_401(self, client_no_secret_patch: TestClient):
        """Пустой X-Webhook-Secret → HTTP 401."""
        response = client_no_secret_patch.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": ""},
        )

        assert response.status_code == 401

    def test_correct_secret_does_not_return_401(self, client: TestClient):
        """Правильный X-Webhook-Secret → НЕ 401."""
        response = client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code != 401


# ===========================================================================
# 3. Валидация payload — HTTP 422
# ===========================================================================


class TestWebhookValidation:
    """POST /api/webhook → 422 при невалидном JSON."""

    def test_invalid_json_returns_422(self, client: TestClient):
        """Невалидный JSON → HTTP 422."""
        response = client.post(
            WEBHOOK_URL,
            content=b"not-a-json{{{",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": VALID_SECRET,
            },
        )

        assert response.status_code == 422

    def test_json_nesting_depth_exceeds_limit_returns_422(self, client: TestClient):
        """JSON с вложенностью > 10 уровней → HTTP 422 (защита от DoS)."""
        deep_payload = _build_nested_dict(15)

        response = client.post(
            WEBHOOK_URL,
            json=deep_payload,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 422

    def test_json_nesting_at_limit_returns_200(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """JSON с вложенностью ровно 10 уровней → HTTP 200 (в пределах лимита)."""
        payload_at_limit = _build_nested_dict(10)

        response = client.post(
            WEBHOOK_URL,
            json=payload_at_limit,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 200

    def test_json_nesting_11_levels_returns_422(self, client: TestClient):
        """JSON с вложенностью 11 уровней → HTTP 422 (превышение на 1)."""
        payload_over_limit = _build_nested_dict(11)

        response = client.post(
            WEBHOOK_URL,
            json=payload_over_limit,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 422


# ===========================================================================
# 4. Ограничение размера тела запроса — HTTP 413
# ===========================================================================


class TestWebhookPayloadSize:
    """POST /api/webhook → 413 Payload Too Large при превышении 1MB."""

    def test_payload_over_1mb_returns_413(self, client: TestClient):
        """Тело запроса > 1MB → HTTP 413 Payload Too Large."""
        # Создаём JSON-строку чуть больше 1MB
        oversized_value = "x" * (1024 * 1024 + 100)
        oversized_payload = {"data": oversized_value}

        response = client.post(
            WEBHOOK_URL,
            json=oversized_payload,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 413

    def test_payload_under_1mb_returns_200(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Тело запроса < 1MB → HTTP 200 (в пределах лимита)."""
        small_payload = {"data": "x" * 1000}

        response = client.post(
            WEBHOOK_URL,
            json=small_payload,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 200

    def test_content_length_header_over_1mb_returns_413(self, client: TestClient):
        """Content-Length > 1MB → HTTP 413 (проверка по заголовку)."""
        small_body = json.dumps({"data": "small"}).encode()

        response = client.post(
            WEBHOOK_URL,
            content=small_body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(2 * 1024 * 1024),  # 2MB
                "X-Webhook-Secret": VALID_SECRET,
            },
        )

        assert response.status_code == 413


# ===========================================================================
# 5. [SRE_MARKER] Сервис возвращает ошибку — роутер всё равно HTTP 200
# ===========================================================================


class TestSREServiceErrorStillHttp200:
    """
    [SRE_MARKER] Если WebhookService возвращает {"status": "error"} (например,
    из-за падения БД), роутер всё равно ДОЛЖЕН вернуть HTTP 200.
    Webhook — асинхронный фоновый процесс; провайдер не должен получать 5xx,
    иначе он будет ретраить и создавать каскадную нагрузку.
    """

    def test_service_error_status_still_returns_http_200(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Сервис вернул {"status": "error"} → HTTP 200 (не 500!)."""
        mock_webhook_service.process_guardrail_incident.return_value = (
            SERVICE_ERROR_RESPONSE
        )

        response = client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"

    def test_service_rejected_status_still_returns_http_200(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Сервис вернул {"status": "rejected"} → HTTP 200."""
        mock_webhook_service.process_guardrail_incident.return_value = {
            "status": "rejected",
            "reason": "empty payload",
        }

        response = client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"


# ===========================================================================
# 6. [SRE_MARKER] Необработанное исключение в сервисе → HTTP 500
# ===========================================================================


class TestSREUnhandledException:
    """
    [SRE_MARKER] Если WebhookService бросает необработанное исключение,
    роутер должен вернуть HTTP 500 Internal Server Error.
    """

    def test_service_exception_returns_500(
        self, client: TestClient, mock_webhook_service: AsyncMock
    ):
        """Необработанное исключение в сервисе → HTTP 500."""
        mock_webhook_service.process_guardrail_incident.side_effect = RuntimeError(
            "Unexpected crash"
        )

        response = client.post(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 500


# ===========================================================================
# 7. Проверка маршрутизации (метод, путь, теги)
# ===========================================================================


class TestWebhookRouting:
    """Проверка корректности маршрутизации."""

    def test_get_method_not_allowed(self, client: TestClient):
        """GET /api/webhook → 405 Method Not Allowed."""
        response = client.get(
            WEBHOOK_URL,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 405

    def test_put_method_not_allowed(self, client: TestClient):
        """PUT /api/webhook → 405 Method Not Allowed."""
        response = client.put(
            WEBHOOK_URL,
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 405

    def test_delete_method_not_allowed(self, client: TestClient):
        """DELETE /api/webhook → 405 Method Not Allowed."""
        response = client.delete(
            WEBHOOK_URL,
            headers={"X-Webhook-Secret": VALID_SECRET},
        )

        assert response.status_code == 405

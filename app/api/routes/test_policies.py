"""
Модульные тесты для роутера политик безопасности (policies.py).

Спецификация: app/api/routes/policies_spec.md
Фаза: TDD Red — тесты должны падать до реализации роутера.

Тестируемые эндпоинты:
  - GET    /api/policies/            — список всех активных политик
  - POST   /api/policies/            — создание новой политики
  - PUT    /api/policies/{policy_id} — обновление политики
  - DELETE /api/policies/{policy_id} — soft delete политики
  - POST   /api/policies/sync        — синхронизация из облака
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Импорты из проекта (ожидаемые по архитектуре) ---
from app.api.routes.policies import router as policies_router
from app.services.policy_service import PolicyService
from app.api.dependencies.di import get_policy_service
from app.api.middleware.auth import get_current_user
from app.domain.dto.gateway_error import GatewayError


# ─────────────────────────────────────────────────────────
# Хелперы
# ─────────────────────────────────────────────────────────

FAKE_TRACE_ID = str(uuid.uuid4())


def _make_gateway_error(status_code: int, error_code: str, message: str) -> MagicMock:
    """Создать мок GatewayError с заданным статусом."""
    err = MagicMock(spec=GatewayError)
    err.status_code = status_code
    err.trace_id = FAKE_TRACE_ID
    err.error_code = error_code
    err.message = message
    err.details = {}
    return err


def _make_fake_policy(
    policy_id: int = 1,
    name: str = "test-policy",
    body: dict | None = None,
    remote_id: str = "remote-abc",
    provider_id: int = 1,
) -> dict:
    """Фейковая политика как словарь (имитация сериализованной сущности)."""
    return {
        "id": policy_id,
        "name": name,
        "body": body or {"type": "guardrail", "rules": []},
        "remote_id": remote_id,
        "provider_id": provider_id,
        "is_active": True,
    }


# ─────────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────────


@pytest.fixture()
def mock_policy_service() -> MagicMock:
    """Мок PolicyService — все методы возвращают AsyncMock."""
    service = MagicMock(spec=PolicyService)
    service.list_policies = AsyncMock(return_value=[])
    service.create_policy = AsyncMock(return_value=_make_fake_policy())
    service.update_policy = AsyncMock(return_value=_make_fake_policy())
    service.delete_policy = AsyncMock(return_value=True)
    service.sync_policies_from_provider = AsyncMock(
        return_value={
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "total_remote": 0,
        }
    )
    return service


@pytest.fixture()
def client(mock_policy_service: MagicMock) -> TestClient:
    """
    TestClient с подменённым PolicyService через dependency_overrides.
    HTTP Basic Auth отключён для изоляции тестов роутинга.
    """
    app = FastAPI()
    app.include_router(policies_router)

    app.dependency_overrides[get_policy_service] = lambda: mock_policy_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    return TestClient(app)


# ═════════════════════════════════════════════════════════
# 3. GET /api/policies/ — список всех активных политик
# ═════════════════════════════════════════════════════════


class TestListPolicies:
    """Тесты для GET /api/policies/ — список политик."""

    def test_list_policies_returns_200(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Успешный запрос списка — HTTP 200."""
        mock_policy_service.list_policies.return_value = []

        response = client.get("/api/policies/")

        assert response.status_code == 200
        mock_policy_service.list_policies.assert_called_once()

    def test_list_policies_returns_list_body(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Ответ содержит JSON-список политик."""
        fake_policies = [
            _make_fake_policy(policy_id=1, name="policy-a"),
            _make_fake_policy(policy_id=2, name="policy-b"),
        ]
        mock_policy_service.list_policies.return_value = fake_policies

        response = client.get("/api/policies/")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2

    def test_list_policies_empty_returns_200_with_empty_list(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Пустой список политик — HTTP 200 с пустым массивом."""
        mock_policy_service.list_policies.return_value = []

        response = client.get("/api/policies/")

        assert response.status_code == 200
        assert response.json() == []


# ═════════════════════════════════════════════════════════
# 4. POST /api/policies/ — создание новой политики
# ═════════════════════════════════════════════════════════


class TestCreatePolicy:
    """Тесты для POST /api/policies/ — создание политики."""

    def test_create_policy_returns_201(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Успешное создание — HTTP 201."""
        mock_policy_service.create_policy.return_value = _make_fake_policy()

        payload = {
            "name": "new-policy",
            "body": {"type": "guardrail", "rules": [{"check": "pii"}]},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 201
        mock_policy_service.create_policy.assert_called_once()

    def test_create_policy_with_provider_name(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Создание с явным provider_name — HTTP 201."""
        mock_policy_service.create_policy.return_value = _make_fake_policy()

        payload = {
            "name": "new-policy",
            "body": {"type": "guardrail"},
            "provider_name": "openai",
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 201

    def test_create_policy_default_provider_name_is_portkey(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """provider_name по умолчанию = 'portkey'."""
        mock_policy_service.create_policy.return_value = _make_fake_policy()

        payload = {
            "name": "new-policy",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 201
        call_args = mock_policy_service.create_policy.call_args
        assert call_args is not None
        # Ожидаем вызов с provider_name="portkey" (keyword или positional)
        all_values = list(call_args.args) + list(call_args.kwargs.values())
        assert "portkey" in all_values

    def test_create_policy_returns_body_with_policy_data(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Ответ содержит данные созданной политики."""
        fake = _make_fake_policy(policy_id=42, name="created-policy")
        mock_policy_service.create_policy.return_value = fake

        payload = {
            "name": "created-policy",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert isinstance(body, dict)

    # ── Валидация (HTTP 422) ──

    def test_create_policy_missing_name_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'name' — HTTP 422."""
        payload = {
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 422

    def test_create_policy_missing_body_returns_422(self, client: TestClient):
        """Отсутствие обязательного поля 'body' — HTTP 422."""
        payload = {
            "name": "test-policy",
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 422

    def test_create_policy_empty_json_returns_422(self, client: TestClient):
        """Пустое тело запроса — HTTP 422."""
        response = client.post("/api/policies/", json={})

        assert response.status_code == 422

    def test_create_policy_invalid_json_returns_422(self, client: TestClient):
        """Невалидный JSON — HTTP 422."""
        response = client.post(
            "/api/policies/",
            content=b"not-a-json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_create_policy_body_not_dict_returns_422(self, client: TestClient):
        """body должен быть словарём, строка — HTTP 422."""
        payload = {
            "name": "test-policy",
            "body": "not-a-dict",
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 422

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_create_policy_gateway_error_maps_to_http_status(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError от сервиса — HTTP с соответствующим status_code."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Cloud provider failed")
        mock_policy_service.create_policy.return_value = error

        payload = {
            "name": "new-policy",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 502

    def test_create_policy_auth_failed_returns_401(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError AUTH_FAILED — HTTP 401."""
        error = _make_gateway_error(401, "AUTH_FAILED", "Провайдер не найден")
        mock_policy_service.create_policy.return_value = error

        payload = {
            "name": "new-policy",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 401

    def test_create_policy_unknown_error_returns_500(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError UNKNOWN — HTTP 500."""
        error = _make_gateway_error(500, "UNKNOWN", "Ошибка при сохранении в БД")
        mock_policy_service.create_policy.return_value = error

        payload = {
            "name": "new-policy",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 500


# ═════════════════════════════════════════════════════════
# 5. PUT /api/policies/{policy_id} — обновление политики
# ═════════════════════════════════════════════════════════


class TestUpdatePolicy:
    """Тесты для PUT /api/policies/{policy_id} — обновление политики."""

    def test_update_policy_returns_200(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Успешное обновление — HTTP 200."""
        mock_policy_service.update_policy.return_value = _make_fake_policy(
            name="updated-name"
        )

        payload = {"name": "updated-name"}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 200
        mock_policy_service.update_policy.assert_called_once()

    def test_update_policy_with_name_only(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Обновление только name — HTTP 200."""
        mock_policy_service.update_policy.return_value = _make_fake_policy(
            name="new-name"
        )

        payload = {"name": "new-name"}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 200

    def test_update_policy_with_body_only(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Обновление только body — HTTP 200."""
        new_body = {"type": "guardrail", "rules": [{"check": "toxicity"}]}
        mock_policy_service.update_policy.return_value = _make_fake_policy(
            body=new_body
        )

        payload = {"body": new_body}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 200

    def test_update_policy_with_both_fields(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Обновление name и body одновременно — HTTP 200."""
        new_body = {"type": "guardrail", "rules": []}
        mock_policy_service.update_policy.return_value = _make_fake_policy(
            name="both-updated", body=new_body
        )

        payload = {"name": "both-updated", "body": new_body}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 200

    def test_update_policy_empty_body_accepted(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Пустое тело запроса (оба поля null) — допустимо, HTTP 200."""
        mock_policy_service.update_policy.return_value = _make_fake_policy()

        payload: dict = {}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 200

    def test_update_policy_passes_policy_id_to_service(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """policy_id из URL корректно передаётся в сервис."""
        mock_policy_service.update_policy.return_value = _make_fake_policy()

        payload = {"name": "test"}
        client.put("/api/policies/42", json=payload)

        call_args = mock_policy_service.update_policy.call_args
        assert call_args is not None
        # policy_id=42 должен быть передан (позиционно или keyword)
        if call_args.args:
            assert call_args.args[0] == 42
        else:
            assert call_args.kwargs.get("policy_id") == 42

    # ── Ошибка: политика не найдена (HTTP 404) ──

    def test_update_policy_not_found_returns_404(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Политика не найдена — HTTP 404."""
        error = _make_gateway_error(404, "VALIDATION_ERROR", "Политика не найдена")
        mock_policy_service.update_policy.return_value = error

        payload = {"name": "updated"}
        response = client.put("/api/policies/999", json=payload)

        assert response.status_code == 404

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_update_policy_gateway_error_502(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError от облака — HTTP 502."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Cloud sync failed")
        mock_policy_service.update_policy.return_value = error

        payload = {"body": {"type": "guardrail"}}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 502

    # ── Валидация path-параметра ──

    def test_update_policy_invalid_id_returns_422(self, client: TestClient):
        """Нечисловой policy_id — HTTP 422."""
        payload = {"name": "test"}
        response = client.put("/api/policies/abc", json=payload)

        assert response.status_code == 422


# ═════════════════════════════════════════════════════════
# 6. DELETE /api/policies/{policy_id} — soft delete
# ═════════════════════════════════════════════════════════


class TestDeletePolicy:
    """Тесты для DELETE /api/policies/{policy_id} — удаление политики."""

    def test_delete_policy_returns_200(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Успешное удаление — HTTP 200."""
        mock_policy_service.delete_policy.return_value = True

        response = client.delete("/api/policies/1")

        assert response.status_code == 200
        mock_policy_service.delete_policy.assert_called_once()

    def test_delete_policy_response_contains_status_deleted(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Ответ содержит {"status": "deleted"}."""
        mock_policy_service.delete_policy.return_value = True

        response = client.delete("/api/policies/1")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "deleted"

    def test_delete_policy_passes_policy_id_to_service(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """policy_id из URL корректно передаётся в сервис."""
        mock_policy_service.delete_policy.return_value = True

        client.delete("/api/policies/77")

        call_args = mock_policy_service.delete_policy.call_args
        assert call_args is not None
        if call_args.args:
            assert call_args.args[0] == 77
        else:
            assert call_args.kwargs.get("policy_id") == 77

    # ── Ошибка: политика не найдена (HTTP 404) ──

    def test_delete_policy_not_found_returns_404(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Политика не найдена — HTTP 404."""
        error = _make_gateway_error(404, "VALIDATION_ERROR", "Политика не найдена")
        mock_policy_service.delete_policy.return_value = error

        response = client.delete("/api/policies/999")

        assert response.status_code == 404

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_delete_policy_gateway_error_502(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError от облака при удалении — HTTP 502."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Cloud delete failed")
        mock_policy_service.delete_policy.return_value = error

        response = client.delete("/api/policies/1")

        assert response.status_code == 502

    # ── Валидация path-параметра ──

    def test_delete_policy_invalid_id_returns_422(self, client: TestClient):
        """Нечисловой policy_id — HTTP 422."""
        response = client.delete("/api/policies/abc")

        assert response.status_code == 422


# ═════════════════════════════════════════════════════════
# 7. POST /api/policies/sync — синхронизация из облака
# ═════════════════════════════════════════════════════════


class TestSyncPolicies:
    """Тесты для POST /api/policies/sync — синхронизация политик."""

    def test_sync_policies_returns_200(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Успешная синхронизация — HTTP 200."""
        mock_policy_service.sync_policies_from_provider.return_value = {
            "created": 2,
            "updated": 1,
            "unchanged": 5,
            "total_remote": 8,
        }

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 200
        mock_policy_service.sync_policies_from_provider.assert_called_once()

    def test_sync_policies_returns_report_body(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Ответ содержит отчёт о синхронизации."""
        report = {
            "created": 3,
            "updated": 0,
            "unchanged": 7,
            "total_remote": 10,
        }
        mock_policy_service.sync_policies_from_provider.return_value = report

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 3
        assert body["updated"] == 0
        assert body["unchanged"] == 7
        assert body["total_remote"] == 10

    def test_sync_policies_default_provider_name_is_portkey(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """provider_name по умолчанию = 'portkey'."""
        mock_policy_service.sync_policies_from_provider.return_value = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "total_remote": 0,
        }

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 200
        call_args = mock_policy_service.sync_policies_from_provider.call_args
        assert call_args is not None
        # Проверяем, что provider_name == "portkey"
        all_values = list(call_args.args) + list(call_args.kwargs.values())
        assert "portkey" in all_values

    def test_sync_policies_with_custom_provider_name(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Синхронизация с явным provider_name."""
        mock_policy_service.sync_policies_from_provider.return_value = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "total_remote": 0,
        }

        response = client.post("/api/policies/sync", json={"provider_name": "openai"})

        assert response.status_code == 200
        call_args = mock_policy_service.sync_policies_from_provider.call_args
        assert call_args is not None

    def test_sync_policies_without_body_accepted(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """Запрос без тела (или пустое тело) — допустимо, используется дефолт."""
        mock_policy_service.sync_policies_from_provider.return_value = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "total_remote": 0,
        }

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 200

    # ── Маппинг GatewayError → HTTP-статусы ──

    def test_sync_policies_gateway_error_maps_to_http_status(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError от сервиса — HTTP с соответствующим status_code."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Cloud list failed")
        mock_policy_service.sync_policies_from_provider.return_value = error

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 502

    def test_sync_policies_auth_failed_returns_401(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """GatewayError AUTH_FAILED — HTTP 401."""
        error = _make_gateway_error(401, "AUTH_FAILED", "Провайдер не найден")
        mock_policy_service.sync_policies_from_provider.return_value = error

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 401


# ═════════════════════════════════════════════════════════
# 8. Обработка ошибок — общие сценарии [SRE_MARKER]
# ═════════════════════════════════════════════════════════


class TestPoliciesErrorHandling:
    """Тесты обработки ошибок для всех эндпоинтов политик."""

    def test_list_policies_service_raises_exception_returns_500(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при list — HTTP 500.
        Роутер не должен пробрасывать необработанные исключения наружу.
        """
        mock_policy_service.list_policies.side_effect = RuntimeError(
            "DB connection lost"
        )

        response = client.get("/api/policies/")

        assert response.status_code == 500

    def test_create_policy_service_raises_exception_returns_500(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при create — HTTP 500.
        """
        mock_policy_service.create_policy.side_effect = RuntimeError("Unexpected error")

        payload = {
            "name": "test",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 500

    def test_update_policy_service_raises_exception_returns_500(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при update — HTTP 500.
        """
        mock_policy_service.update_policy.side_effect = RuntimeError("Unexpected error")

        payload = {"name": "test"}
        response = client.put("/api/policies/1", json=payload)

        assert response.status_code == 500

    def test_delete_policy_service_raises_exception_returns_500(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при delete — HTTP 500.
        """
        mock_policy_service.delete_policy.side_effect = RuntimeError("Unexpected error")

        response = client.delete("/api/policies/1")

        assert response.status_code == 500

    def test_sync_policies_service_raises_exception_returns_500(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] Внутренняя ошибка сервиса при sync — HTTP 500.
        """
        mock_policy_service.sync_policies_from_provider.side_effect = RuntimeError(
            "Unexpected error"
        )

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 500


# ═════════════════════════════════════════════════════════
# 9. [SRE_MARKER] Маршрутизация: /sync НЕ перехватывается {policy_id}
# ═════════════════════════════════════════════════════════


class TestRouteOrdering:
    """
    Проверяем, что /api/policies/sync обрабатывается отдельным хендлером,
    а не попадает в PUT/DELETE /api/policies/{policy_id} как policy_id='sync'.
    """

    def test_sync_route_not_captured_by_policy_id_put(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] POST /api/policies/sync должен вызывать sync_policies_from_provider(),
        а НЕ update_policy() или delete_policy().
        """
        mock_policy_service.sync_policies_from_provider.return_value = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "total_remote": 0,
        }

        response = client.post("/api/policies/sync", json={})

        assert response.status_code == 200
        mock_policy_service.sync_policies_from_provider.assert_called_once()
        mock_policy_service.update_policy.assert_not_called()
        mock_policy_service.delete_policy.assert_not_called()

    def test_sync_route_returns_correct_method(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """
        [SRE] GET/PUT/DELETE на /api/policies/sync не должны совпадать
        с POST /api/policies/sync.
        """
        mock_policy_service.sync_policies_from_provider.return_value = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "total_remote": 0,
        }

        # PUT на /sync не должен быть валидным роутом sync
        response_put = client.put("/api/policies/sync", json={})
        # Ожидаем 405 Method Not Allowed или 422 (если sync интерпретируется как policy_id)
        assert response_put.status_code in (405, 422)


# ═════════════════════════════════════════════════════════
# 10. [SRE_MARKER] Структура ответа ошибки
# ═════════════════════════════════════════════════════════


class TestErrorResponseStructure:
    """Проверка полноты ErrorResponse при GatewayError."""

    def test_error_response_contains_required_fields(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """ErrorResponse должен содержать trace_id, error_code, message."""
        error = _make_gateway_error(502, "PROVIDER_ERROR", "Cloud failed")
        error.details = {"extra": "info"}
        mock_policy_service.create_policy.return_value = error

        payload = {
            "name": "test",
            "body": {"type": "guardrail"},
        }
        response = client.post("/api/policies/", json=payload)

        assert response.status_code == 502
        body = response.json()
        assert "trace_id" in body
        assert "error_code" in body
        assert "message" in body

    def test_error_response_trace_id_is_present(
        self, client: TestClient, mock_policy_service: MagicMock
    ):
        """[SRE] trace_id обязателен в ответе с ошибкой для distributed tracing."""
        error = _make_gateway_error(500, "UNKNOWN", "Fail")
        mock_policy_service.delete_policy.return_value = error

        response = client.delete("/api/policies/1")

        body = response.json()
        assert "trace_id" in body
        assert body["trace_id"] is not None

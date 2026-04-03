"""
Модульные тесты для роутера журнала событий (logs.py).

Спецификация: app/api/routes/logs_spec.md
Фаза: TDD Red — тесты должны падать до реализации роутера.

Тестируемые эндпоинты:
  - GET /api/logs/         — постраничный список событий
  - GET /api/logs/stats    — статистика событий
  - GET /api/logs/{trace_id} — события по trace_id
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Импорты из проекта (ожидаемые по архитектуре) ---
from app.api.routes.logs import router as logs_router
from app.services.log_service import LogService
from app.api.dependencies.di import get_log_service


# ─────────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────────


@pytest.fixture()
def mock_log_service() -> MagicMock:
    """Мок LogService — все методы возвращают AsyncMock."""
    service = MagicMock(spec=LogService)
    service.get_logs = AsyncMock(return_value=[])
    service.get_logs_by_trace_id = AsyncMock(return_value=[])
    service.get_log_stats = AsyncMock(return_value={})
    return service


@pytest.fixture()
def client(mock_log_service: MagicMock) -> TestClient:
    """
    TestClient с подменённым LogService через dependency_overrides.
    HTTP Basic Auth отключён для изоляции тестов роутинга.
    """
    from app.api.middleware.auth import get_current_user

    app = FastAPI()
    app.include_router(logs_router)

    app.dependency_overrides[get_log_service] = lambda: mock_log_service
    app.dependency_overrides[get_current_user] = lambda: "test-user"

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Заголовки HTTP Basic Auth для авторизованных запросов."""
    import base64

    credentials = base64.b64encode(b"admin:admin").decode("utf-8")
    return {"Authorization": f"Basic {credentials}"}


# ═════════════════════════════════════════════════════════
# 3. GET /api/logs/ — постраничный список событий
# ═════════════════════════════════════════════════════════


class TestGetLogsList:
    """Тесты для GET /api/logs/ — постраничный список событий."""

    def test_get_logs_default_params_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запрос без параметров — HTTP 200, дефолтные limit=100, offset=0."""
        mock_log_service.get_logs.return_value = []

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

    def test_get_logs_with_custom_limit_and_offset(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запрос с limit=50, offset=10 — HTTP 200, параметры пробрасываются в сервис."""
        mock_log_service.get_logs.return_value = []

        response = client.get(
            "/api/logs/", params={"limit": 50, "offset": 10}, headers=auth_headers
        )

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

    def test_get_logs_with_event_type_filter(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запрос с event_type=chat_request — HTTP 200, фильтр передаётся в сервис."""
        mock_log_service.get_logs.return_value = []

        response = client.get(
            "/api/logs/",
            params={"event_type": "chat_request"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        mock_log_service.get_logs.assert_called_once()

    def test_get_logs_returns_list_body(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Ответ содержит JSON-список."""
        fake_log = {
            "id": 1,
            "trace_id": "abc-123",
            "event_type": "chat_request",
            "payload": {},
        }
        mock_log_service.get_logs.return_value = [fake_log]

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1

    # ── [SRE_MARKER] DoS-защита: валидация limit ──

    def test_get_logs_limit_exceeds_max_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] limit > 1000 — HTTP 422.
        Защита от DoS: предотвращение полного сканирования таблицы.
        """
        response = client.get(
            "/api/logs/", params={"limit": 1001}, headers=auth_headers
        )

        assert response.status_code == 422

    def test_get_logs_limit_zero_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] limit=0 — HTTP 422.
        Минимальное значение limit = 1.
        """
        response = client.get("/api/logs/", params={"limit": 0}, headers=auth_headers)

        assert response.status_code == 422

    def test_get_logs_limit_negative_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] limit=-1 — HTTP 422.
        Отрицательные значения запрещены.
        """
        response = client.get("/api/logs/", params={"limit": -1}, headers=auth_headers)

        assert response.status_code == 422

    # ── [SRE_MARKER] DoS-защита: валидация offset ──

    def test_get_logs_negative_offset_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """
        [SRE] offset=-1 — HTTP 422.
        Отрицательный offset запрещён.
        """
        response = client.get("/api/logs/", params={"offset": -1}, headers=auth_headers)

        assert response.status_code == 422

    def test_get_logs_non_integer_limit_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """limit=abc — HTTP 422. Нечисловое значение."""
        response = client.get(
            "/api/logs/", params={"limit": "abc"}, headers=auth_headers
        )

        assert response.status_code == 422

    def test_get_logs_non_integer_offset_returns_422(
        self, client: TestClient, auth_headers: dict
    ):
        """offset=xyz — HTTP 422. Нечисловое значение."""
        response = client.get(
            "/api/logs/", params={"offset": "xyz"}, headers=auth_headers
        )

        assert response.status_code == 422


# ═════════════════════════════════════════════════════════
# 4. GET /api/logs/{trace_id} — события по trace_id
# ═════════════════════════════════════════════════════════


class TestGetLogsByTraceId:
    """Тесты для GET /api/logs/{trace_id}."""

    def test_get_logs_by_trace_id_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Существующий trace_id — HTTP 200 со списком событий."""
        fake_events = [
            {"id": 1, "trace_id": "abc-123", "event_type": "chat_request"},
            {"id": 2, "trace_id": "abc-123", "event_type": "chat_response"},
        ]
        mock_log_service.get_logs_by_trace_id.return_value = fake_events

        response = client.get("/api/logs/abc-123", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        mock_log_service.get_logs_by_trace_id.assert_called_once_with("abc-123")

    def test_get_logs_by_trace_id_empty_result_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """trace_id без событий — HTTP 200 с пустым списком."""
        mock_log_service.get_logs_by_trace_id.return_value = []

        response = client.get("/api/logs/nonexistent-trace", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body == []
        mock_log_service.get_logs_by_trace_id.assert_called_once_with(
            "nonexistent-trace"
        )

    def test_get_logs_by_trace_id_calls_service_with_correct_id(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Проверяем, что trace_id из URL корректно передаётся в сервис."""
        mock_log_service.get_logs_by_trace_id.return_value = []

        client.get("/api/logs/my-unique-trace-42", headers=auth_headers)

        mock_log_service.get_logs_by_trace_id.assert_called_once_with(
            "my-unique-trace-42"
        )


# ═════════════════════════════════════════════════════════
# 5. GET /api/logs/stats — статистика событий
# ═════════════════════════════════════════════════════════


class TestGetLogStats:
    """Тесты для GET /api/logs/stats."""

    def test_get_log_stats_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Успешный запрос статистики — HTTP 200."""
        mock_log_service.get_log_stats.return_value = {
            "total": 150,
            "by_event_type": {"chat_request": 100, "chat_response": 50},
        }

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_log_stats.assert_called_once()

    def test_get_log_stats_returns_dict_body(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Ответ содержит JSON-словарь со статистикой."""
        stats_data = {
            "total": 42,
            "by_event_type": {"error": 5, "chat_request": 37},
        }
        mock_log_service.get_log_stats.return_value = stats_data

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, dict)
        assert body["total"] == 42

    def test_get_log_stats_empty_returns_200(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Пустая статистика — HTTP 200 с пустым словарём."""
        mock_log_service.get_log_stats.return_value = {}

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body == {}


# ═════════════════════════════════════════════════════════
# 6. Обработка ошибок — общие сценарии
# ═════════════════════════════════════════════════════════


class TestLogsErrorHandling:
    """Тесты обработки ошибок для всех эндпоинтов логов."""

    def test_get_logs_service_raises_exception_returns_500(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        [SRE] Внутренняя ошибка сервиса — HTTP 500.
        Роутер не должен пробрасывать необработанные исключения наружу.
        """
        mock_log_service.get_logs.side_effect = RuntimeError("DB connection lost")

        response = client.get("/api/logs/", headers=auth_headers)

        assert response.status_code == 500

    def test_get_logs_by_trace_id_service_raises_exception_returns_500(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        [SRE] Ошибка при поиске по trace_id — HTTP 500.
        """
        mock_log_service.get_logs_by_trace_id.side_effect = RuntimeError(
            "Unexpected error"
        )

        response = client.get("/api/logs/some-trace", headers=auth_headers)

        assert response.status_code == 500

    def test_get_log_stats_service_raises_exception_returns_500(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        [SRE] Ошибка при получении статистики — HTTP 500.
        """
        mock_log_service.get_log_stats.side_effect = RuntimeError("Stats unavailable")

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 500


# ═════════════════════════════════════════════════════════
# Маршрутизация: /stats НЕ перехватывается {trace_id}
# ═════════════════════════════════════════════════════════


class TestRouteOrdering:
    """
    Проверяем, что /api/logs/stats обрабатывается отдельным хендлером,
    а не попадает в GET /api/logs/{trace_id} как trace_id='stats'.
    """

    def test_stats_route_not_captured_by_trace_id(
        self, client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """
        GET /api/logs/stats должен вызывать get_log_stats(),
        а НЕ get_logs_by_trace_id('stats').
        """
        mock_log_service.get_log_stats.return_value = {"total": 0}
        mock_log_service.get_logs_by_trace_id.return_value = []

        response = client.get("/api/logs/stats", headers=auth_headers)

        assert response.status_code == 200
        mock_log_service.get_log_stats.assert_called_once()
        mock_log_service.get_logs_by_trace_id.assert_not_called()

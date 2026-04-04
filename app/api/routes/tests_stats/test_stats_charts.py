"""
Тесты для GET /api/stats/charts — данные для графиков.

Извлечены из app/api/routes/test_stats.py при рефакторинге.
Спецификация: app/api/routes/stats_spec.md
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════════════
# 3. GET /api/stats/charts — успешный ответ (spec 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetStatsChartsSuccess:
    """GET /api/stats/charts -> 200 OK с данными для графиков."""

    def test_returns_200(self, client: TestClient):
        """Эндпоинт возвращает HTTP 200."""
        response = client.get("/api/stats/charts")
        assert response.status_code == 200

    def test_response_is_list(self, client: TestClient, mock_log_service: AsyncMock):
        """Ответ — JSON-массив."""
        response = client.get("/api/stats/charts")
        body = response.json()
        assert isinstance(body, list)

    def test_response_items_have_hour_and_count(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """Каждый элемент содержит 'hour' и 'count'."""
        response = client.get("/api/stats/charts")
        body = response.json()
        for item in body:
            assert "hour" in item
            assert "count" in item

    def test_response_count_is_integer(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """count — целое число."""
        response = client.get("/api/stats/charts")
        body = response.json()
        for item in body:
            assert isinstance(item["count"], int)

    def test_response_hour_is_string(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """hour — строка."""
        response = client.get("/api/stats/charts")
        body = response.json()
        for item in body:
            assert isinstance(item["hour"], str)

    def test_default_hours_is_24(self, client: TestClient, mock_log_service: AsyncMock):
        """По умолчанию hours=24 (spec 3.2)."""
        client.get("/api/stats/charts")
        mock_log_service.get_chart_data.assert_called()
        call_kwargs = mock_log_service.get_chart_data.call_args
        args, kwargs = call_kwargs
        hours_value = kwargs.get("hours") or (args[0] if args else None)
        assert hours_value == 24

    def test_custom_hours_parameter(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """Пользовательский параметр hours передаётся в сервис."""
        client.get("/api/stats/charts?hours=48")
        mock_log_service.get_chart_data.assert_called()
        call_kwargs = mock_log_service.get_chart_data.call_args
        args, kwargs = call_kwargs
        hours_value = kwargs.get("hours") or (args[0] if args else None)
        assert hours_value == 48

    def test_response_sorted_by_hour_ascending(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """Данные отсортированы по hour в порядке возрастания (spec 3.4)."""
        response = client.get("/api/stats/charts")
        body = response.json()
        hours = [item["hour"] for item in body]
        assert hours == sorted(hours)


# ═══════════════════════════════════════════════════════════════════════════
# 4. GET /api/stats/charts — валидация параметра hours (spec 3.2)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetStatsChartsValidation:
    """GET /api/stats/charts — валидация параметра hours."""

    def test_hours_below_1_returns_422(self, client: TestClient):
        """hours=0 -> HTTP 422 (ge=1)."""
        response = client.get("/api/stats/charts?hours=0")
        assert response.status_code == 422

    def test_hours_negative_returns_422(self, client: TestClient):
        """hours=-5 -> HTTP 422."""
        response = client.get("/api/stats/charts?hours=-5")
        assert response.status_code == 422

    def test_hours_above_168_returns_422(self, client: TestClient):
        """hours=169 -> HTTP 422 (le=168)."""
        response = client.get("/api/stats/charts?hours=169")
        assert response.status_code == 422

    def test_hours_1_accepted(self, client: TestClient, mock_log_service: AsyncMock):
        """hours=1 принимается (граничное значение)."""
        response = client.get("/api/stats/charts?hours=1")
        assert response.status_code == 200

    def test_hours_168_accepted(self, client: TestClient, mock_log_service: AsyncMock):
        """hours=168 принимается (граничное значение)."""
        response = client.get("/api/stats/charts?hours=168")
        assert response.status_code == 200

    def test_hours_non_integer_returns_422(self, client: TestClient):
        """hours=abc -> HTTP 422."""
        response = client.get("/api/stats/charts?hours=abc")
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 5. GET /api/stats/charts — обработка ошибок (spec 3.6)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetStatsChartsErrors:
    """GET /api/stats/charts -> 500 при ошибке сервиса."""

    def test_service_exception_returns_500(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """Исключение сервиса -> HTTP 500."""
        mock_log_service.get_chart_data.side_effect = Exception("DB timeout")

        response = client.get("/api/stats/charts")
        assert response.status_code == 500

    def test_error_response_contains_detail(
        self, client: TestClient, mock_log_service: AsyncMock
    ):
        """Ответ об ошибке содержит 'detail' = 'Internal server error'."""
        mock_log_service.get_chart_data.side_effect = Exception("DB timeout")

        response = client.get("/api/stats/charts")
        body = response.json()
        assert (
            body.get("detail") == "Internal server error"
            or body.get("message") == "Internal server error"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. [SRE_MARKER] Защита от DoS — параметр hours (spec 4)
# ═══════════════════════════════════════════════════════════════════════════


class TestStatsSecurityHoursLimit:
    """[SRE_MARKER] Параметр hours ограничен [1, 168] для предотвращения DoS."""

    def test_hours_1000_rejected(self, client: TestClient):
        """[SRE_MARKER] hours=1000 отклоняется (> 168)."""
        response = client.get("/api/stats/charts?hours=1000")
        assert response.status_code == 422

    def test_hours_999999_rejected(self, client: TestClient):
        """[SRE_MARKER] hours=999999 отклоняется (чрезмерно широкий запрос)."""
        response = client.get("/api/stats/charts?hours=999999")
        assert response.status_code == 422

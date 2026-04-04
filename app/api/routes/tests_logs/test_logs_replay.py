"""
Тесты для POST /api/logs/{id}/replay — повтор запросов.

Извлечены из app/api/routes/test_logs.py при рефакторинге.
Спецификация: app/api/routes/logs_spec.md (upgrade §3)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.logs import router as logs_router
from app.api.dependencies.di import get_log_service


# ═════════════════════════════════════════════════════════
# [UPGRADE] 9. POST /api/logs/{id}/replay (logs_upgrade_spec §3)
# ═════════════════════════════════════════════════════════


class TestPostLogsReplay:
    """Тесты для нового эндпоинта POST /api/logs/{id}/replay (upgrade spec §3)."""

    @pytest.fixture()
    def replay_client(self, mock_log_service: MagicMock) -> TestClient:
        """TestClient с подменёнными LogService и ChatService для replay."""
        from app.api.middleware.auth import get_current_user
        from app.api.dependencies.di import get_chat_service

        mock_chat_service = MagicMock()
        mock_chat_service.send_chat_message = AsyncMock(
            return_value=MagicMock(
                trace_id="new-trace-id",
                content="Replayed response",
                model="gpt-4",
                usage={"total_tokens": 42},
                guardrail_blocked=False,
            )
        )

        app = FastAPI()
        app.include_router(logs_router)

        app.dependency_overrides[get_log_service] = lambda: mock_log_service
        app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
        app.dependency_overrides[get_current_user] = lambda: "test-user"

        return TestClient(app, raise_server_exceptions=False)

    def test_replay_not_found_returns_404(
        self, replay_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Запись лога не найдена -> HTTP 404.

        logs_upgrade_spec.md §3.7.
        """
        mock_log_service.get_log_by_id = AsyncMock(return_value=None)

        response = replay_client.post("/api/logs/999/replay", headers=auth_headers)

        assert response.status_code == 404

    def test_replay_non_chat_request_returns_400(
        self, replay_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """Тип события не chat_request -> HTTP 400.

        logs_upgrade_spec.md §3.5 п.4.
        """
        fake_log = MagicMock(
            id=1,
            event_type="system_error",
            payload='{"error": "test"}',
        )
        mock_log_service.get_log_by_id = AsyncMock(return_value=fake_log)

        response = replay_client.post("/api/logs/1/replay", headers=auth_headers)

        assert response.status_code == 400
        body = response.json()
        assert (
            "chat_request" in body.get("detail", "").lower()
            or "only chat_request" in body.get("detail", "").lower()
        )

    def test_replay_rate_limit_exceeded_returns_429(
        self, replay_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """[SRE_MARKER] Rate limit: >10 replay/min -> HTTP 429.

        logs_upgrade_spec.md §3.4: максимум 10 replay-запросов в минуту.
        """
        fake_log = MagicMock(
            id=1,
            event_type="chat_request",
            payload='{"prompt": {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}}',
        )
        mock_log_service.get_log_by_id = AsyncMock(return_value=fake_log)

        # Отправляем 11 запросов подряд
        for i in range(11):
            response = replay_client.post("/api/logs/1/replay", headers=auth_headers)

        # 11-й запрос должен вернуть 429
        assert response.status_code == 429

    def test_replay_corrupted_payload_returns_400(
        self, replay_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """[SRE_MARKER] Повреждённый payload -> HTTP 400.

        logs_upgrade_spec.md §3.5 п.6: валидация через Pydantic-схему.
        """
        fake_log = MagicMock(
            id=1,
            event_type="chat_request",
            payload='{"corrupted": true}',  # Нет prompt.model, prompt.messages
        )
        mock_log_service.get_log_by_id = AsyncMock(return_value=fake_log)

        response = replay_client.post("/api/logs/1/replay", headers=auth_headers)

        assert response.status_code == 400

    def test_replay_creates_new_trace_id(
        self, replay_client: TestClient, mock_log_service: MagicMock, auth_headers: dict
    ):
        """[SRE_MARKER] Replay создаёт НОВЫЙ trace_id (не переиспользует оригинальный).

        logs_upgrade_spec.md §4: безопасность.
        """
        fake_log = MagicMock(
            id=1,
            trace_id="original-trace-id",
            event_type="chat_request",
            payload='{"prompt": {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "temperature": null, "max_tokens": null, "guardrail_ids": []}, "response": {}}',
        )
        mock_log_service.get_log_by_id = AsyncMock(return_value=fake_log)

        response = replay_client.post("/api/logs/1/replay", headers=auth_headers)

        if response.status_code == 200:
            body = response.json()
            assert body.get("trace_id") != "original-trace-id", (
                "Replay должен создать НОВЫЙ trace_id"
            )

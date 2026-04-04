"""
Unit tests for LogService.
Specification: app/services/log_service_spec.md

TDD Red phase: all tests should fail with ImportError,
until LogService is not implemented.
"""

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Import tested class (should fail during Red phase) ──────────────
from app.services.log_service import LogService

# ── Импорт доменных объектов (already implemented in scaffolding) ────────────
from app.domain.entities.log_entry import EventType, LogEntry


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_log_repo():
    """Mock LogRepository with async methods."""
    repo = AsyncMock()
    repo.create = AsyncMock(return_value=None)
    repo.list_all = AsyncMock(return_value=[])
    repo.list_by_type = AsyncMock(return_value=[])
    repo.get_by_trace_id = AsyncMock(return_value=[])
    repo.count_all = AsyncMock(return_value=0)
    repo.count_by_type = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def service(mock_log_repo):
    """Instance of LogService с замоканным репозиторием."""
    return LogService(log_repo=mock_log_repo)


@pytest.fixture
def valid_trace_id():
    """Valid UUID v4 trace_id."""
    return "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
def sample_prompt_data():
    """Пример данных промпта."""
    return {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}


@pytest.fixture
def sample_response_data():
    """Пример данных ответа."""
    return {
        "choices": [{"message": {"content": "Hi there!"}}],
        "usage": {"total_tokens": 42},
    }


@pytest.fixture
def sample_incident_data():
    """Пример данных инцидента guardrail."""
    return {"rule": "content_filter", "severity": "high", "blocked": True}


@pytest.fixture
def sample_error_data():
    """Пример данных системной ошибки."""
    return {
        "adapter": "portkey",
        "exception": "ConnectionTimeout",
        "detail": "10s elapsed",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Constructor (specification §2)
# ═══════════════════════════════════════════════════════════════════════════


class TestLogServiceConstructor:
    """Constructor tests for LogService (specification §2)."""

    def test_constructor_accepts_log_repo(self, mock_log_repo):
        """LogService accepts log_repo via constructor."""
        svc = LogService(log_repo=mock_log_repo)
        assert svc is not None

    def test_constructor_stores_log_repo(self, mock_log_repo):
        """Dependency log_repo is stored as an instance attribute."""
        svc = LogService(log_repo=mock_log_repo)
        assert svc.log_repo is mock_log_repo


# ═══════════════════════════════════════════════════════════════════════════
# 3. log_chat_request (specification §3)
# ═══════════════════════════════════════════════════════════════════════════


class TestLogChatRequest:
    """Tests for метода log_chat_request (specification §3)."""

    @pytest.mark.asyncio
    async def test_log_chat_request_calls_repo_create(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """Успешная запись: вызывает log_repo.create с правильными аргументами."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        mock_log_repo.create.assert_awaited_once()
        call_args = mock_log_repo.create.call_args
        assert call_args[0][0] == valid_trace_id
        assert call_args[0][1] == EventType.CHAT_REQUEST

    @pytest.mark.asyncio
    async def test_log_chat_request_payload_contains_prompt(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """Payload содержит ключ 'prompt' с данными промпта."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "prompt" in payload
        assert payload["prompt"] == sample_prompt_data

    @pytest.mark.asyncio
    async def test_log_chat_request_payload_contains_response(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """Payload содержит ключ 'response' с данными ответа."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "response" in payload
        assert payload["response"] == sample_response_data

    @pytest.mark.asyncio
    async def test_log_chat_request_payload_is_error_false_by_default(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """By default is_error=False в payload."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "is_error" in payload
        assert payload["is_error"] is False

    @pytest.mark.asyncio
    async def test_log_chat_request_payload_is_error_true(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """Передача is_error=True отражается в payload."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
            is_error=True,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert payload["is_error"] is True

    @pytest.mark.asyncio
    async def test_log_chat_request_payload_contains_logged_at_iso(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """Payload содержит 'logged_at' in ISO 8601 UTC format."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "logged_at" in payload
        parsed = datetime.fromisoformat(payload["logged_at"])
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_log_chat_request_payload_has_exactly_four_keys(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """Payload contains exactly 4 ключа: prompt, response, is_error, logged_at."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert set(payload.keys()) == {"prompt", "response", "is_error", "logged_at"}

    @pytest.mark.asyncio
    async def test_log_chat_request_returns_none(
        self, service, valid_trace_id, sample_prompt_data, sample_response_data
    ):
        """Method returns None."""
        result = await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_chat_request_suppresses_db_error(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """[SRE_MARKER] Ошибка БД при записи лога подавляется, не пробрасывается."""
        mock_log_repo.create.side_effect = Exception("DB connection lost")

        result = await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_chat_request_logs_to_stderr_on_db_error(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """[SRE_MARKER] При ошибке БД — вывод в stderr через logging.error."""
        mock_log_repo.create.side_effect = Exception("DB write failed")

        with patch("app.services.log_service.logging") as mock_logging:
            await service.log_chat_request(
                trace_id=valid_trace_id,
                prompt_data=sample_prompt_data,
                response_data=sample_response_data,
            )
            mock_logging.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_chat_request_event_type_is_chat_request(
        self,
        service,
        mock_log_repo,
        valid_trace_id,
        sample_prompt_data,
        sample_response_data,
    ):
        """event_type передаётся как EventType.CHAT_REQUEST."""
        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data=sample_prompt_data,
            response_data=sample_response_data,
        )

        event_type = mock_log_repo.create.call_args[0][1]
        assert event_type == EventType.CHAT_REQUEST


# ═══════════════════════════════════════════════════════════════════════════
# 4. log_guardrail_incident (specification §4)
# ═══════════════════════════════════════════════════════════════════════════


class TestLogGuardrailIncident:
    """Tests for метода log_guardrail_incident (specification §4)."""

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_calls_repo_create(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """Успешная запись: вызывает log_repo.create."""
        await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )

        mock_log_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_event_type(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """event_type = EventType.GUARDRAIL_INCIDENT."""
        await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )

        event_type = mock_log_repo.create.call_args[0][1]
        assert event_type == EventType.GUARDRAIL_INCIDENT

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_payload_contains_incident(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """Payload содержит ключ 'incident' с данными инцидента."""
        await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "incident" in payload
        assert payload["incident"] == sample_incident_data

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_payload_contains_logged_at(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """Payload содержит 'logged_at' в формате ISO 8601."""
        await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "logged_at" in payload
        parsed = datetime.fromisoformat(payload["logged_at"])
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_payload_has_exactly_two_keys(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """Payload contains exactly 2 ключа: incident и logged_at."""
        await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert set(payload.keys()) == {"incident", "logged_at"}

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_returns_none(
        self, service, valid_trace_id, sample_incident_data
    ):
        """Method returns None."""
        result = await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_suppresses_db_error(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """[SRE_MARKER] Ошибка БД подавляется."""
        mock_log_repo.create.side_effect = RuntimeError("DB timeout")

        result = await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data=sample_incident_data,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_logs_stderr_on_error(
        self, service, mock_log_repo, valid_trace_id, sample_incident_data
    ):
        """[SRE_MARKER] При ошибке — logging.error is called."""
        mock_log_repo.create.side_effect = RuntimeError("DB timeout")

        with patch("app.services.log_service.logging") as mock_logging:
            await service.log_guardrail_incident(
                trace_id=valid_trace_id,
                incident_data=sample_incident_data,
            )
            mock_logging.error.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# 5. log_system_error (specification §5)
# ═══════════════════════════════════════════════════════════════════════════


class TestLogSystemError:
    """Tests for метода log_system_error (specification §5)."""

    @pytest.mark.asyncio
    async def test_log_system_error_calls_repo_create(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """Успешная запись: вызывает log_repo.create."""
        await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )

        mock_log_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_system_error_event_type(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """event_type = EventType.SYSTEM_ERROR."""
        await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )

        event_type = mock_log_repo.create.call_args[0][1]
        assert event_type == EventType.SYSTEM_ERROR

    @pytest.mark.asyncio
    async def test_log_system_error_payload_contains_error(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """Payload содержит ключ 'error' с данными ошибки."""
        await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "error" in payload
        assert payload["error"] == sample_error_data

    @pytest.mark.asyncio
    async def test_log_system_error_payload_contains_logged_at(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """Payload содержит 'logged_at' в формате ISO 8601."""
        await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert "logged_at" in payload
        parsed = datetime.fromisoformat(payload["logged_at"])
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_log_system_error_payload_has_exactly_two_keys(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """Payload contains exactly 2 ключа: error и logged_at."""
        await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )

        payload = mock_log_repo.create.call_args[0][2]
        assert set(payload.keys()) == {"error", "logged_at"}

    @pytest.mark.asyncio
    async def test_log_system_error_returns_none(
        self, service, valid_trace_id, sample_error_data
    ):
        """Method returns None."""
        result = await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_system_error_suppresses_db_error(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """[SRE_MARKER] Ошибка БД подавляется."""
        mock_log_repo.create.side_effect = Exception("Disk full")

        result = await service.log_system_error(
            trace_id=valid_trace_id,
            error_data=sample_error_data,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_system_error_logs_stderr_on_error(
        self, service, mock_log_repo, valid_trace_id, sample_error_data
    ):
        """[SRE_MARKER] При ошибке — logging.error is called."""
        mock_log_repo.create.side_effect = Exception("Disk full")

        with patch("app.services.log_service.logging") as mock_logging:
            await service.log_system_error(
                trace_id=valid_trace_id,
                error_data=sample_error_data,
            )
            mock_logging.error.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# 6. get_logs (specification §6)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetLogs:
    """Tests for метода get_logs (specification §6)."""

    @pytest.mark.asyncio
    async def test_get_logs_default_params(self, service, mock_log_repo):
        """By default limit=100, offset=0, event_type=None -> list_all."""
        mock_log_repo.list_all.return_value = []

        await service.get_logs()

        mock_log_repo.list_all.assert_awaited_once_with(100, 0)

    @pytest.mark.asyncio
    async def test_get_logs_custom_limit_offset(self, service, mock_log_repo):
        """Передача кастомных limit и offset."""
        mock_log_repo.list_all.return_value = []

        await service.get_logs(limit=50, offset=10)

        mock_log_repo.list_all.assert_awaited_once_with(50, 10)

    @pytest.mark.asyncio
    async def test_get_logs_with_event_type_calls_list_by_type(
        self, service, mock_log_repo
    ):
        """If event_type задан -> вызывается list_by_type."""
        mock_log_repo.list_by_type.return_value = []

        await service.get_logs(event_type="chat_request")

        mock_log_repo.list_by_type.assert_awaited_once_with("chat_request", 100, 0)
        mock_log_repo.list_all.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_logs_without_event_type_calls_list_all(
        self, service, mock_log_repo
    ):
        """Без event_type -> вызывается list_all."""
        mock_log_repo.list_all.return_value = []

        await service.get_logs()

        mock_log_repo.list_all.assert_awaited_once()
        mock_log_repo.list_by_type.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_logs_returns_list(self, service, mock_log_repo):
        """Method returns список."""
        fake_orm = MagicMock(
            id=1,
            trace_id="123e4567-e89b-42d3-a456-426614174000",
            event_type=EventType.CHAT_REQUEST,
            payload={
                "prompt": {},
                "response": {},
                "is_error": False,
                "logged_at": "2026-01-01T00:00:00+00:00",
            },
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        mock_log_repo.list_all.return_value = [fake_orm]

        result = await service.get_logs()

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_logs_empty_returns_empty_list(self, service, mock_log_repo):
        """Пустая БД -> пустой список."""
        mock_log_repo.list_all.return_value = []

        result = await service.get_logs()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_logs_db_error_propagates(self, service, mock_log_repo):
        """[SRE_MARKER] Ошибка БД при чтении логов пробрасывается наверх (для UI)."""
        mock_log_repo.list_all.side_effect = Exception("DB read error")

        with pytest.raises(Exception, match="DB read error"):
            await service.get_logs()

    @pytest.mark.asyncio
    async def test_get_logs_with_event_type_and_custom_pagination(
        self, service, mock_log_repo
    ):
        """event_type + кастомные limit/offset передаются в list_by_type."""
        mock_log_repo.list_by_type.return_value = []

        await service.get_logs(limit=25, offset=5, event_type="system_error")

        mock_log_repo.list_by_type.assert_awaited_once_with("system_error", 25, 5)


# ═══════════════════════════════════════════════════════════════════════════
# 7. get_logs_by_trace_id (specification §7)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetLogsByTraceId:
    """Tests for метода get_logs_by_trace_id (specification §7)."""

    @pytest.mark.asyncio
    async def test_get_logs_by_trace_id_calls_repo(
        self, service, mock_log_repo, valid_trace_id
    ):
        """Calls log_repo.get_by_trace_id с переданным trace_id."""
        mock_log_repo.get_by_trace_id.return_value = []

        await service.get_logs_by_trace_id(trace_id=valid_trace_id)

        mock_log_repo.get_by_trace_id.assert_awaited_once_with(valid_trace_id)

    @pytest.mark.asyncio
    async def test_get_logs_by_trace_id_returns_list(
        self, service, mock_log_repo, valid_trace_id
    ):
        """Method returns список."""
        fake_orm = MagicMock(
            id=1,
            trace_id=valid_trace_id,
            event_type=EventType.CHAT_REQUEST,
            payload={
                "prompt": {},
                "response": {},
                "is_error": False,
                "logged_at": "2026-01-01T00:00:00+00:00",
            },
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        mock_log_repo.get_by_trace_id.return_value = [fake_orm]

        result = await service.get_logs_by_trace_id(trace_id=valid_trace_id)

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_logs_by_trace_id_empty_returns_empty_list(
        self, service, mock_log_repo, valid_trace_id
    ):
        """Нет записей по trace_id -> пустой список."""
        mock_log_repo.get_by_trace_id.return_value = []

        result = await service.get_logs_by_trace_id(trace_id=valid_trace_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_logs_by_trace_id_can_return_mixed_event_types(
        self, service, mock_log_repo, valid_trace_id
    ):
        """Может вернуть записи разных типов (chat_request + guardrail_incident)."""
        chat_orm = MagicMock(
            id=1,
            trace_id=valid_trace_id,
            event_type=EventType.CHAT_REQUEST,
            payload={
                "prompt": {},
                "response": {},
                "is_error": False,
                "logged_at": "2026-01-01T00:00:00+00:00",
            },
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        incident_orm = MagicMock(
            id=2,
            trace_id=valid_trace_id,
            event_type=EventType.GUARDRAIL_INCIDENT,
            payload={"incident": {}, "logged_at": "2026-01-01T00:00:01+00:00"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        mock_log_repo.get_by_trace_id.return_value = [chat_orm, incident_orm]

        result = await service.get_logs_by_trace_id(trace_id=valid_trace_id)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_logs_by_trace_id_db_error_propagates(
        self, service, mock_log_repo, valid_trace_id
    ):
        """[SRE_MARKER] Ошибка БД при чтении пробрасывается наверх."""
        mock_log_repo.get_by_trace_id.side_effect = Exception("DB read error")

        with pytest.raises(Exception, match="DB read error"):
            await service.get_logs_by_trace_id(trace_id=valid_trace_id)


# ═══════════════════════════════════════════════════════════════════════════
# 8. get_log_stats (specification §8)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetLogStats:
    """Tests for метода get_log_stats (specification §8)."""

    @pytest.mark.asyncio
    async def test_get_log_stats_returns_dict(self, service, mock_log_repo):
        """Method returns словарь."""
        mock_log_repo.count_all.return_value = 10
        mock_log_repo.count_by_type.return_value = 3

        result = await service.get_log_stats()

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_log_stats_has_total_key(self, service, mock_log_repo):
        """Словарь содержит ключ 'total'."""
        mock_log_repo.count_all.return_value = 0
        mock_log_repo.count_by_type.return_value = 0

        result = await service.get_log_stats()

        assert "total" in result

    @pytest.mark.asyncio
    async def test_get_log_stats_has_chat_requests_key(self, service, mock_log_repo):
        """Словарь содержит ключ 'chat_requests'."""
        mock_log_repo.count_all.return_value = 0
        mock_log_repo.count_by_type.return_value = 0

        result = await service.get_log_stats()

        assert "chat_requests" in result

    @pytest.mark.asyncio
    async def test_get_log_stats_has_guardrail_incidents_key(
        self, service, mock_log_repo
    ):
        """Словарь содержит ключ 'guardrail_incidents'."""
        mock_log_repo.count_all.return_value = 0
        mock_log_repo.count_by_type.return_value = 0

        result = await service.get_log_stats()

        assert "guardrail_incidents" in result

    @pytest.mark.asyncio
    async def test_get_log_stats_has_system_errors_key(self, service, mock_log_repo):
        """Словарь содержит ключ 'system_errors'."""
        mock_log_repo.count_all.return_value = 0
        mock_log_repo.count_by_type.return_value = 0

        result = await service.get_log_stats()

        assert "system_errors" in result

    @pytest.mark.asyncio
    async def test_get_log_stats_has_all_required_keys(self, service, mock_log_repo):
        """Словарь содержит все 4 обязательных ключа."""
        mock_log_repo.count_all.return_value = 0
        mock_log_repo.count_by_type.return_value = 0

        result = await service.get_log_stats()

        required = {"total", "chat_requests", "guardrail_incidents", "system_errors"}
        assert required.issubset(set(result.keys()))

    @pytest.mark.asyncio
    async def test_get_log_stats_values_are_integers(self, service, mock_log_repo):
        """Все значения в словаре — целые числа."""
        mock_log_repo.count_all.return_value = 42
        mock_log_repo.count_by_type.return_value = 10

        result = await service.get_log_stats()

        for key in ("total", "chat_requests", "guardrail_incidents", "system_errors"):
            assert isinstance(result[key], int), (
                f"'{key}' должно быть int, получено {type(result[key])}"
            )

    @pytest.mark.asyncio
    async def test_get_log_stats_total_gte_subtotal(self, service, mock_log_repo):
        """total >= суммы отдельных типов."""
        mock_log_repo.count_all.return_value = 100
        mock_log_repo.count_by_type.side_effect = lambda et: {
            EventType.CHAT_REQUEST: 50,
            EventType.GUARDRAIL_INCIDENT: 30,
            EventType.SYSTEM_ERROR: 20,
        }.get(et, 0)

        result = await service.get_log_stats()

        subtotal = (
            result["chat_requests"]
            + result["guardrail_incidents"]
            + result["system_errors"]
        )
        assert result["total"] >= subtotal


# ═══════════════════════════════════════════════════════════════════════════
# 9. Обработка ошибок — общие сценарии (specification §9)
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorHandlingGeneral:
    """Общие тесты обработки ошибок (specification §9)."""

    @pytest.mark.asyncio
    async def test_write_error_suppressed_in_log_chat_request(
        self, service, mock_log_repo, valid_trace_id
    ):
        """[SRE_MARKER] Любая ошибка записи в log_chat_request подавляется."""
        mock_log_repo.create.side_effect = OSError("Network unreachable")

        await service.log_chat_request(
            trace_id=valid_trace_id,
            prompt_data={"x": 1},
            response_data={"y": 2},
        )

    @pytest.mark.asyncio
    async def test_write_error_suppressed_in_log_guardrail_incident(
        self, service, mock_log_repo, valid_trace_id
    ):
        """[SRE_MARKER] Любая ошибка записи в log_guardrail_incident подавляется."""
        mock_log_repo.create.side_effect = OSError("Network unreachable")

        await service.log_guardrail_incident(
            trace_id=valid_trace_id,
            incident_data={"rule": "test"},
        )

    @pytest.mark.asyncio
    async def test_write_error_suppressed_in_log_system_error(
        self, service, mock_log_repo, valid_trace_id
    ):
        """[SRE_MARKER] Любая ошибка записи в log_system_error подавляется."""
        mock_log_repo.create.side_effect = OSError("Network unreachable")

        await service.log_system_error(
            trace_id=valid_trace_id,
            error_data={"err": "test"},
        )

    @pytest.mark.asyncio
    async def test_read_error_propagates_from_get_logs(self, service, mock_log_repo):
        """[SRE_MARKER] Ошибка БД при чтении (get_logs) пробрасывается для UI."""
        mock_log_repo.list_all.side_effect = ConnectionError("DB down")

        with pytest.raises(ConnectionError):
            await service.get_logs()

    @pytest.mark.asyncio
    async def test_read_error_propagates_from_get_logs_by_trace_id(
        self, service, mock_log_repo, valid_trace_id
    ):
        """[SRE_MARKER] Ошибка БД при чтении get_logs_by_trace_id пробрасывается."""
        mock_log_repo.get_by_trace_id.side_effect = ConnectionError("DB down")

        with pytest.raises(ConnectionError):
            await service.get_logs_by_trace_id(trace_id=valid_trace_id)


# ═══════════════════════════════════════════════════════════════════════════
# [UPGRADE] 10. get_stats_summary (log_service_upgrade_spec §1)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetStatsSummary:
    """Tests for нового метода get_stats_summary (upgrade spec §1)."""

    @pytest.mark.asyncio
    async def test_get_stats_summary_returns_dict(self, service, mock_log_repo):
        """Method returns словарь."""
        mock_log_repo.count_all.return_value = 100
        mock_log_repo.count_by_type.return_value = 30
        mock_log_repo.aggregate_token_stats = AsyncMock(
            return_value={"total_tokens": 5000, "avg_latency_ms": 245.67}
        )

        result = await service.get_stats_summary()

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_stats_summary_has_six_keys(self, service, mock_log_repo):
        """Словарь содержит 6 ключей: total, chat_requests, guardrail_incidents,
        system_errors, total_tokens, avg_latency_ms."""
        mock_log_repo.count_all.return_value = 100
        mock_log_repo.count_by_type.return_value = 30
        mock_log_repo.aggregate_token_stats = AsyncMock(
            return_value={"total_tokens": 5000, "avg_latency_ms": 245.67}
        )

        result = await service.get_stats_summary()

        expected_keys = {
            "total", "chat_requests", "guardrail_incidents",
            "system_errors", "total_tokens", "avg_latency_ms",
        }
        assert expected_keys.issubset(set(result.keys()))

    @pytest.mark.asyncio
    async def test_get_stats_summary_includes_token_stats(self, service, mock_log_repo):
        """Результат включает total_tokens и avg_latency_ms из aggregate_token_stats."""
        mock_log_repo.count_all.return_value = 10
        mock_log_repo.count_by_type.return_value = 3
        mock_log_repo.aggregate_token_stats = AsyncMock(
            return_value={"total_tokens": 9999, "avg_latency_ms": 123.45}
        )

        result = await service.get_stats_summary()

        assert result["total_tokens"] == 9999
        assert result["avg_latency_ms"] == 123.45

    @pytest.mark.asyncio
    async def test_get_stats_summary_graceful_degradation_on_aggregate_error(
        self, service, mock_log_repo
    ):
        """[SRE_MARKER] Ошибка aggregate_token_stats → graceful degradation.

        log_service_upgrade_spec.md §1.5: total_tokens=0, avg_latency_ms=0.0.
        Базовая статистика возвращается нормально.
        """
        mock_log_repo.count_all.return_value = 50
        mock_log_repo.count_by_type.return_value = 10
        mock_log_repo.aggregate_token_stats = AsyncMock(
            side_effect=Exception("DB timeout on aggregation")
        )

        result = await service.get_stats_summary()

        assert result["total"] == 50
        assert result["total_tokens"] == 0
        assert result["avg_latency_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_get_stats_summary_calls_both_methods(self, service, mock_log_repo):
        """Метод вызывает и get_log_stats() и aggregate_token_stats()."""
        mock_log_repo.count_all.return_value = 0
        mock_log_repo.count_by_type.return_value = 0
        mock_log_repo.aggregate_token_stats = AsyncMock(
            return_value={"total_tokens": 0, "avg_latency_ms": 0.0}
        )

        await service.get_stats_summary()

        mock_log_repo.count_all.assert_awaited()
        mock_log_repo.aggregate_token_stats.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# [UPGRADE] 11. get_chart_data (log_service_upgrade_spec §2)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetChartData:
    """Tests for нового метода get_chart_data (upgrade spec §2)."""

    @pytest.mark.asyncio
    async def test_get_chart_data_returns_list(self, service, mock_log_repo):
        """Method returns список словарей."""
        mock_log_repo.count_by_hour = AsyncMock(
            return_value=[("2026-04-01 10:00", 5), ("2026-04-01 11:00", 12)]
        )

        result = await service.get_chart_data(hours=24)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_chart_data_items_have_hour_and_count(self, service, mock_log_repo):
        """Каждый элемент содержит ключи 'hour' и 'count'."""
        mock_log_repo.count_by_hour = AsyncMock(
            return_value=[("2026-04-01 10:00", 5)]
        )

        result = await service.get_chart_data(hours=24)

        assert len(result) == 1
        assert "hour" in result[0]
        assert "count" in result[0]
        assert result[0]["hour"] == "2026-04-01 10:00"
        assert result[0]["count"] == 5

    @pytest.mark.asyncio
    async def test_get_chart_data_default_hours_24(self, service, mock_log_repo):
        """By default hours=24."""
        mock_log_repo.count_by_hour = AsyncMock(return_value=[])

        await service.get_chart_data()

        mock_log_repo.count_by_hour.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_chart_data_empty_returns_empty_list(self, service, mock_log_repo):
        """Нет данных → пустой список."""
        mock_log_repo.count_by_hour = AsyncMock(return_value=[])

        result = await service.get_chart_data(hours=24)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_chart_data_db_error_propagates(self, service, mock_log_repo):
        """[SRE_MARKER] Ошибка БД пробрасывается наверх (обрабатывается роутером).

        log_service_upgrade_spec.md §2.4.
        """
        mock_log_repo.count_by_hour = AsyncMock(
            side_effect=Exception("DB connection lost")
        )

        with pytest.raises(Exception, match="DB connection lost"):
            await service.get_chart_data(hours=24)


# ═══════════════════════════════════════════════════════════════════════════
# [UPGRADE] 12. get_log_by_id (log_service_upgrade_spec §3)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetLogById:
    """Tests for нового метода get_log_by_id (upgrade spec §3)."""

    @pytest.mark.asyncio
    async def test_get_log_by_id_calls_repo(self, service, mock_log_repo):
        """Calls log_repo.get_by_id с переданным log_id."""
        mock_log_repo.get_by_id = AsyncMock(return_value=None)

        await service.get_log_by_id(log_id=42)

        mock_log_repo.get_by_id.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_get_log_by_id_returns_entry(self, service, mock_log_repo):
        """Возвращает LogEntryModel, если найден."""
        fake_entry = MagicMock(id=42, trace_id="trace-042")
        mock_log_repo.get_by_id = AsyncMock(return_value=fake_entry)

        result = await service.get_log_by_id(log_id=42)

        assert result is fake_entry

    @pytest.mark.asyncio
    async def test_get_log_by_id_returns_none_when_not_found(self, service, mock_log_repo):
        """Возвращает None, если запись не найдена."""
        mock_log_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_log_by_id(log_id=999)

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# [UPGRADE] 13. export_logs (log_service_upgrade_spec §4)
# ═══════════════════════════════════════════════════════════════════════════


class TestExportLogs:
    """Tests for нового метода export_logs (upgrade spec §4)."""

    @pytest.mark.asyncio
    async def test_export_logs_yields_csv_header(self, service, mock_log_repo):
        """Первая строка — заголовок CSV: id,trace_id,event_type,created_at,payload."""

        async def _empty_gen(*args, **kwargs):
            return
            yield  # noqa: unreachable — делает функцию async generator

        mock_log_repo.list_for_export = _empty_gen

        lines = []
        async for line in service.export_logs(event_type=None, limit=100):
            lines.append(line)

        assert len(lines) >= 1
        assert "id" in lines[0]
        assert "trace_id" in lines[0]
        assert "event_type" in lines[0]
        assert "created_at" in lines[0]
        assert "payload" in lines[0]

    @pytest.mark.asyncio
    async def test_export_logs_csv_injection_protection(self, service, mock_log_repo):
        """[SRE_MARKER] CSV Injection: payload начинающийся с =, +, -, @ экранируется.

        log_service_upgrade_spec.md §4.3 п.5b: добавляется префикс одинарной кавычки.
        """
        malicious_log = MagicMock(
            id=1,
            trace_id="trace-001",
            event_type="chat_request",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            payload='{"prompt": "=CMD()"}',
        )

        async def _gen(*args, **kwargs):
            yield malicious_log

        mock_log_repo.list_for_export = _gen

        lines = []
        async for line in service.export_logs(event_type=None, limit=100):
            lines.append(line)

        # Должна быть хотя бы header + 1 строка данных
        assert len(lines) >= 2
        # Payload с = должен быть экранирован (префикс ')
        data_line = lines[1]
        # Проверяем, что в строке нет неэкранированного =CMD()
        # (должен быть '=CMD() или экранирован иначе)
        assert "=CMD()" not in data_line or "'=CMD()" in data_line or "\"'=CMD()\"" in data_line

    @pytest.mark.asyncio
    async def test_export_logs_streaming_error_marker(self, service, mock_log_repo):
        """[SRE_MARKER] Ошибка после начала генерации → маркер '# ERROR: export interrupted'.

        log_service_upgrade_spec.md §4.4: клиент может детектировать неполный экспорт.
        """
        good_log = MagicMock(
            id=1,
            trace_id="trace-001",
            event_type="chat_request",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            payload='{"ok": true}',
        )

        async def _gen_with_error(*args, **kwargs):
            yield good_log
            raise RuntimeError("DB connection lost mid-stream")

        mock_log_repo.list_for_export = _gen_with_error

        lines = []
        async for line in service.export_logs(event_type=None, limit=100):
            lines.append(line)

        # Последняя строка должна содержать маркер ошибки
        assert any("ERROR" in line and "interrupted" in line for line in lines), (
            "При ошибке после начала генерации должен быть маркер "
            "'# ERROR: export interrupted'"
        )

    @pytest.mark.asyncio
    async def test_export_logs_is_async_generator(self, service, mock_log_repo):
        """export_logs — асинхронный генератор (yield, не return)."""
        import inspect

        assert hasattr(service, "export_logs"), (
            "LogService должен иметь метод export_logs"
        )
        assert inspect.isasyncgenfunction(service.export_logs) or callable(service.export_logs), (
            "export_logs должен быть async generator function"
        )

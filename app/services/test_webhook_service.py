"""
Unit tests for WebhookService.
Specification: app/services/webhook_service_spec.md

TDD Red phase: all tests should fail with ImportError,
until WebhookService is not implemented.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Import tested class (should fail during Red phase) ──────────────
from app.services.webhook_service import WebhookService

# ── Импорт доменных объектов (already implemented in scaffolding) ────────────
from app.domain.entities.log_entry import EventType

# ── UUID v4 regex for validation ─────────────────────────────────────
_UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_log_service():
    """Mock LogService with async methods."""
    svc = AsyncMock()
    svc.log_guardrail_incident = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def mock_log_repo():
    """Mock LogRepository with async methods."""
    repo = AsyncMock()
    repo.get_by_trace_id = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_log_service, mock_log_repo):
    """Instance of WebhookService with mocked dependencies."""
    return WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)


@pytest.fixture
def valid_trace_id():
    """Valid UUID v4 trace_id."""
    return "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
def sample_guardrail_payload(valid_trace_id):
    """Sample incoming webhook payload with trace_id at root."""
    return {
        "trace_id": valid_trace_id,
        "event": "guardrail_triggered",
        "rule": "content_filter",
        "severity": "high",
        "blocked": True,
    }


@pytest.fixture
def sample_payload_trace_in_metadata(valid_trace_id):
    """Payload with trace_id in nested metadata."""
    return {
        "event": "guardrail_triggered",
        "rule": "pii_detection",
        "metadata": {
            "trace_id": valid_trace_id,
            "source": "provider_x",
        },
    }


@pytest.fixture
def sample_payload_no_trace():
    """Payload without trace_id anywhere."""
    return {
        "event": "guardrail_triggered",
        "rule": "toxicity_filter",
        "severity": "medium",
    }


@pytest.fixture
def fake_chat_request_log(valid_trace_id):
    """Fake chat_request ORM record simulating prompt linkage."""
    log = MagicMock()
    log.trace_id = valid_trace_id
    log.event_type = EventType.CHAT_REQUEST
    log.payload = {"prompt": {}, "response": {}}
    log.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return log


# ═══════════════════════════════════════════════════════════════════════════
# Constructor (specification §2)
# ═══════════════════════════════════════════════════════════════════════════


class TestWebhookServiceConstructor:
    """Constructor tests for WebhookService (specification §2)."""

    def test_constructor_accepts_log_service_and_log_repo(
        self, mock_log_service, mock_log_repo
    ):
        """WebhookService accepts log_service и log_repo via constructor."""
        svc = WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)
        assert svc is not None

    def test_constructor_stores_log_service(self, mock_log_service, mock_log_repo):
        """Dependency log_service is stored as an instance attribute."""
        svc = WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)
        assert svc.log_service is mock_log_service

    def test_constructor_stores_log_repo(self, mock_log_service, mock_log_repo):
        """Dependency log_repo is stored as an instance attribute."""
        svc = WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)
        assert svc.log_repo is mock_log_repo


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Извлечение trace_id (specification §4, шаг 1)
# ═══════════════════════════════════════════════════════════════════════════


class TestTraceIdExtraction:
    """Tests for trace_id extraction from payload (specification §4, step 1)."""

    @pytest.mark.asyncio
    async def test_trace_id_from_root(
        self, service, mock_log_repo, sample_guardrail_payload, valid_trace_id
    ):
        """trace_id берётся из корня payload, если он там есть."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["trace_id"] == valid_trace_id

    @pytest.mark.asyncio
    async def test_trace_id_from_metadata(
        self, service, mock_log_repo, sample_payload_trace_in_metadata, valid_trace_id
    ):
        """trace_id берётся из payload.metadata.trace_id, если в корне нет."""
        result = await service.process_guardrail_incident(
            payload=sample_payload_trace_in_metadata
        )
        assert result["trace_id"] == valid_trace_id

    @pytest.mark.asyncio
    async def test_trace_id_generated_when_missing(
        self, service, mock_log_repo, sample_payload_no_trace
    ):
        """If trace_id нигде нет — генерируется новый UUID."""
        result = await service.process_guardrail_incident(
            payload=sample_payload_no_trace
        )
        assert _UUID_V4_RE.match(result["trace_id"]) is not None

    @pytest.mark.asyncio
    async def test_trace_id_generated_when_empty_string(self, service, mock_log_repo):
        """If trace_id — пустая строка, генерируется новый UUID."""
        payload = {"trace_id": "", "event": "guardrail_triggered"}
        result = await service.process_guardrail_incident(payload=payload)
        assert result["trace_id"] != ""
        assert _UUID_V4_RE.match(result["trace_id"]) is not None

    @pytest.mark.asyncio
    async def test_trace_id_source_webhook_when_from_root(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """trace_id_source = 'webhook' когда trace_id извлечён из payload."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        # Verify incident_payload passed to log_service
        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert incident_payload["trace_id_source"] == "webhook"

    @pytest.mark.asyncio
    async def test_trace_id_source_webhook_when_from_metadata(
        self, service, mock_log_service, mock_log_repo, sample_payload_trace_in_metadata
    ):
        """trace_id_source = 'webhook' когда trace_id извлечён из metadata."""
        await service.process_guardrail_incident(
            payload=sample_payload_trace_in_metadata
        )

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert incident_payload["trace_id_source"] == "webhook"

    @pytest.mark.asyncio
    async def test_trace_id_source_generated_when_missing(
        self, service, mock_log_service, mock_log_repo, sample_payload_no_trace
    ):
        """trace_id_source = 'generated' когда trace_id сгенерирован системой."""
        await service.process_guardrail_incident(payload=sample_payload_no_trace)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert incident_payload["trace_id_source"] == "generated"


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Валидация формата trace_id (specification §4, шаг 2)
# ═══════════════════════════════════════════════════════════════════════════


class TestTraceIdValidation:
    """Tests for trace_id format validation (specification §4, step 2)."""

    @pytest.mark.asyncio
    async def test_valid_uuid_trace_id_accepted(
        self, service, sample_guardrail_payload, valid_trace_id
    ):
        """Валидный UUID v4 trace_id acceptsся без проблем."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["trace_id"] == valid_trace_id

    @pytest.mark.asyncio
    async def test_invalid_trace_id_used_as_is(self, service, mock_log_repo):
        """Невалидный trace_id используется как есть (не отбрасывается)."""
        payload = {
            "trace_id": "not-a-valid-uuid",
            "event": "guardrail_triggered",
        }
        result = await service.process_guardrail_incident(payload=payload)
        assert result["trace_id"] == "not-a-valid-uuid"

    @pytest.mark.asyncio
    async def test_invalid_trace_id_triggers_warning_log(self, service, mock_log_repo):
        """[SRE_MARKER] Невалидный trace_id — предупреждение в лог."""
        payload = {
            "trace_id": "not-a-valid-uuid",
            "event": "guardrail_triggered",
        }
        with patch("app.services.webhook_service.logging") as mock_logging:
            await service.process_guardrail_incident(payload=payload)
            mock_logging.warning.assert_called()


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Связь с исходным запросом (specification §4, шаг 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestLinkedToPrompt:
    """Tests for original request linkage check (specification §4, step 3)."""

    @pytest.mark.asyncio
    async def test_linked_to_prompt_true_when_chat_request_found(
        self, service, mock_log_repo, sample_guardrail_payload, fake_chat_request_log
    ):
        """linked_to_prompt=True если найдены записи с event_type=chat_request."""
        mock_log_repo.get_by_trace_id.return_value = [fake_chat_request_log]

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["linked_to_prompt"] is True

    @pytest.mark.asyncio
    async def test_linked_to_prompt_false_when_no_records(
        self, service, mock_log_repo, sample_guardrail_payload
    ):
        """linked_to_prompt=False если нет записей по trace_id (осиротевший)."""
        mock_log_repo.get_by_trace_id.return_value = []

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["linked_to_prompt"] is False

    @pytest.mark.asyncio
    async def test_linked_to_prompt_false_when_only_non_chat_records(
        self, service, mock_log_repo, sample_guardrail_payload
    ):
        """linked_to_prompt=False если есть записи, но не chat_request."""
        non_chat_log = MagicMock()
        non_chat_log.event_type = EventType.SYSTEM_ERROR
        mock_log_repo.get_by_trace_id.return_value = [non_chat_log]

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["linked_to_prompt"] is False

    @pytest.mark.asyncio
    async def test_log_repo_get_by_trace_id_called(
        self, service, mock_log_repo, sample_guardrail_payload, valid_trace_id
    ):
        """log_repo.get_by_trace_id вызывается с правильным trace_id."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        mock_log_repo.get_by_trace_id.assert_awaited_once_with(valid_trace_id)

    @pytest.mark.asyncio
    async def test_orphaned_incident_still_recorded(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Orphaned incident (no linkage) is still recorded in the audit log."""
        mock_log_repo.get_by_trace_id.return_value = []

        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        mock_log_service.log_guardrail_incident.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Формирование записи инцидента (specification §4, шаг 4)
# ═══════════════════════════════════════════════════════════════════════════


class TestIncidentPayloadFormation:
    """Tests for incident record formation (specification §4, step 4)."""

    @pytest.mark.asyncio
    async def test_incident_contains_original_webhook_body(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Incident record contains original_webhook_body with original payload."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert "original_webhook_body" in incident_payload
        assert incident_payload["original_webhook_body"] == sample_guardrail_payload

    @pytest.mark.asyncio
    async def test_incident_contains_trace_id_source(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Incident record contains trace_id_source."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert "trace_id_source" in incident_payload

    @pytest.mark.asyncio
    async def test_incident_contains_linked_to_prompt(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Incident record contains linked_to_prompt (boolean)."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert "linked_to_prompt" in incident_payload
        assert isinstance(incident_payload["linked_to_prompt"], bool)

    @pytest.mark.asyncio
    async def test_incident_contains_processed_at_iso(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Incident record contains processed_at in ISO 8601 UTC format."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert "processed_at" in incident_payload
        parsed = datetime.fromisoformat(incident_payload["processed_at"])
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_incident_has_exactly_four_keys(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Запись инцидента contains exactly 4 ключа."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        expected_keys = {
            "original_webhook_body",
            "trace_id_source",
            "linked_to_prompt",
            "processed_at",
        }
        assert set(incident_payload.keys()) == expected_keys


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Запись в журнал (specification §4, шаг 5)
# ═══════════════════════════════════════════════════════════════════════════


class TestJournalWrite:
    """Tests for audit log writing via log_service (specification §4, step 5)."""

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_called(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """log_service.log_guardrail_incident is called."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        mock_log_service.log_guardrail_incident.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_receives_trace_id(
        self,
        service,
        mock_log_service,
        mock_log_repo,
        sample_guardrail_payload,
        valid_trace_id,
    ):
        """log_service.log_guardrail_incident receives the correct trace_id."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        passed_trace_id = (
            call_args[0][0] if call_args[0] else call_args[1].get("trace_id")
        )
        assert passed_trace_id == valid_trace_id

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_receives_incident_payload(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """log_service.log_guardrail_incident receives a dict incident_payload."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert isinstance(incident_payload, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Возврат подтверждения (specification §4, шаг 6)
# ═══════════════════════════════════════════════════════════════════════════


class TestReturnConfirmation:
    """Tests for the returned confirmation dict (specification §4, step 6)."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, service, sample_guardrail_payload):
        """Method returns словарь."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_status_accepted(self, service, sample_guardrail_payload):
        """Returned dict contains status='accepted'."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_trace_id_in_response(
        self, service, sample_guardrail_payload, valid_trace_id
    ):
        """Returned dict contains trace_id."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["trace_id"] == valid_trace_id

    @pytest.mark.asyncio
    async def test_linked_to_prompt_in_response(
        self, service, sample_guardrail_payload
    ):
        """Returned dict contains linked_to_prompt (boolean)."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert "linked_to_prompt" in result
        assert isinstance(result["linked_to_prompt"], bool)

    @pytest.mark.asyncio
    async def test_response_has_exactly_three_keys(
        self, service, sample_guardrail_payload
    ):
        """Возвращаемый словарь contains exactly 3 ключа: status, trace_id, linked_to_prompt."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert set(result.keys()) == {"status", "trace_id", "linked_to_prompt"}

    @pytest.mark.asyncio
    async def test_generated_trace_id_in_response_when_missing(
        self, service, sample_payload_no_trace
    ):
        """Generated trace_id is returned in the response."""
        result = await service.process_guardrail_incident(
            payload=sample_payload_no_trace
        )
        assert _UUID_V4_RE.match(result["trace_id"]) is not None


# ═══════════════════════════════════════════════════════════════════════════
# 5. Обработка ошибок (specification §5)
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Error handling tests (specification §5)."""

    @pytest.mark.asyncio
    async def test_empty_payload_returns_rejected(self, service):
        """Empty payload → status='rejected', reason='empty payload'."""
        result = await service.process_guardrail_incident(payload={})
        assert result["status"] == "rejected"
        assert result["reason"] == "empty payload"

    @pytest.mark.asyncio
    async def test_none_payload_returns_rejected(self, service):
        """None payload → status='rejected', reason='empty payload'."""
        result = await service.process_guardrail_incident(payload=None)
        assert result["status"] == "rejected"
        assert result["reason"] == "empty payload"

    @pytest.mark.asyncio
    async def test_db_write_error_returns_error_status(
        self, service, mock_log_service, sample_guardrail_payload
    ):
        """[SRE_MARKER] Ошибка записи в БД → status='error'."""
        mock_log_service.log_guardrail_incident.side_effect = Exception(
            "DB connection lost"
        )

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_db_write_error_logged(
        self, service, mock_log_service, sample_guardrail_payload
    ):
        """[SRE_MARKER] Ошибка записи в БД логируется через logging.error."""
        mock_log_service.log_guardrail_incident.side_effect = Exception(
            "DB connection lost"
        )

        with patch("app.services.webhook_service.logging") as mock_logging:
            await service.process_guardrail_incident(payload=sample_guardrail_payload)
            mock_logging.error.assert_called()

    @pytest.mark.asyncio
    async def test_db_write_error_does_not_propagate(
        self, service, mock_log_service, sample_guardrail_payload
    ):
        """[SRE_MARKER] Ошибка записи в БД не пробрасывается наверх."""
        mock_log_service.log_guardrail_incident.side_effect = RuntimeError("DB timeout")

        # Should not raise an exception
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_db_read_error_during_trace_lookup_returns_error(
        self, service, mock_log_repo, sample_guardrail_payload
    ):
        """[SRE_MARKER] Ошибка при чтении log_repo.get_by_trace_id → status='error'."""
        mock_log_repo.get_by_trace_id.side_effect = Exception("DB read failed")

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_db_read_error_during_trace_lookup_logged(
        self, service, mock_log_repo, sample_guardrail_payload
    ):
        """[SRE_MARKER] Ошибка при чтении log_repo логируется."""
        mock_log_repo.get_by_trace_id.side_effect = Exception("DB read failed")

        with patch("app.services.webhook_service.logging") as mock_logging:
            await service.process_guardrail_incident(payload=sample_guardrail_payload)
            mock_logging.error.assert_called()


# ═══════════════════════════════════════════════════════════════════════════
# Integration scenarios (full path)
# ═══════════════════════════════════════════════════════════════════════════


class TestFullFlow:
    """Интеграционные сценарии: полный путь обработки webhook."""

    @pytest.mark.asyncio
    async def test_full_flow_linked_incident(
        self,
        service,
        mock_log_service,
        mock_log_repo,
        sample_guardrail_payload,
        valid_trace_id,
        fake_chat_request_log,
    ):
        """Full path: trace_id из payload, связан с промптом."""
        mock_log_repo.get_by_trace_id.return_value = [fake_chat_request_log]

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )

        # 1. Verify trace_id
        assert result["trace_id"] == valid_trace_id
        # 2. Prompt linkage
        assert result["linked_to_prompt"] is True
        # 3. Status
        assert result["status"] == "accepted"
        # 4. log_repo.get_by_trace_id was called
        mock_log_repo.get_by_trace_id.assert_awaited_once_with(valid_trace_id)
        # 5. log_service.log_guardrail_incident was called
        mock_log_service.log_guardrail_incident.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_flow_orphaned_incident(
        self,
        service,
        mock_log_service,
        mock_log_repo,
        sample_payload_no_trace,
    ):
        """Full path: trace_id отсутствует, инцидент осиротевший."""
        mock_log_repo.get_by_trace_id.return_value = []

        result = await service.process_guardrail_incident(
            payload=sample_payload_no_trace
        )

        # 1. trace_id was generated
        assert _UUID_V4_RE.match(result["trace_id"]) is not None
        # 2. No prompt linkage
        assert result["linked_to_prompt"] is False
        # 3. Status
        assert result["status"] == "accepted"
        # 4. Record was still written
        mock_log_service.log_guardrail_incident.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_flow_trace_from_metadata_linked(
        self,
        service,
        mock_log_service,
        mock_log_repo,
        sample_payload_trace_in_metadata,
        valid_trace_id,
        fake_chat_request_log,
    ):
        """Full path: trace_id из metadata, связан с промптом."""
        mock_log_repo.get_by_trace_id.return_value = [fake_chat_request_log]

        result = await service.process_guardrail_incident(
            payload=sample_payload_trace_in_metadata
        )

        assert result["trace_id"] == valid_trace_id
        assert result["linked_to_prompt"] is True
        assert result["status"] == "accepted"

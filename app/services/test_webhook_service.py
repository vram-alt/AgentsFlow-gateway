"""
Модульные тесты для WebhookService.
Спецификация: app/services/webhook_service_spec.md

TDD Red-фаза: все тесты должны падать с ImportError,
пока WebhookService не реализован.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Импорт тестируемого класса (должен упасть на Red-фазе) ──────────────
from app.services.webhook_service import WebhookService

# ── Импорт доменных объектов (уже реализованы в скаффолдинге) ────────────
from app.domain.entities.log_entry import EventType

# ── Регулярка UUID v4 для валидации ─────────────────────────────────────
_UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# ═══════════════════════════════════════════════════════════════════════════
# Фикстуры
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_log_service():
    """Мок LogService с async-методами."""
    svc = AsyncMock()
    svc.log_guardrail_incident = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def mock_log_repo():
    """Мок LogRepository с async-методами."""
    repo = AsyncMock()
    repo.get_by_trace_id = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_log_service, mock_log_repo):
    """Экземпляр WebhookService с замоканными зависимостями."""
    return WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)


@pytest.fixture
def valid_trace_id():
    """Валидный UUID v4 trace_id."""
    return "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
def sample_guardrail_payload(valid_trace_id):
    """Пример входящего webhook-payload с trace_id в корне."""
    return {
        "trace_id": valid_trace_id,
        "event": "guardrail_triggered",
        "rule": "content_filter",
        "severity": "high",
        "blocked": True,
    }


@pytest.fixture
def sample_payload_trace_in_metadata(valid_trace_id):
    """Payload с trace_id во вложенном metadata."""
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
    """Payload без trace_id нигде."""
    return {
        "event": "guardrail_triggered",
        "rule": "toxicity_filter",
        "severity": "medium",
    }


@pytest.fixture
def fake_chat_request_log(valid_trace_id):
    """Фейковая ORM-запись chat_request для имитации связи с промптом."""
    log = MagicMock()
    log.trace_id = valid_trace_id
    log.event_type = EventType.CHAT_REQUEST
    log.payload = {"prompt": {}, "response": {}}
    log.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return log


# ═══════════════════════════════════════════════════════════════════════════
# Конструктор (спецификация §2)
# ═══════════════════════════════════════════════════════════════════════════


class TestWebhookServiceConstructor:
    """Тесты конструктора WebhookService (спецификация §2)."""

    def test_constructor_accepts_log_service_and_log_repo(
        self, mock_log_service, mock_log_repo
    ):
        """WebhookService принимает log_service и log_repo через конструктор."""
        svc = WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)
        assert svc is not None

    def test_constructor_stores_log_service(self, mock_log_service, mock_log_repo):
        """Зависимость log_service сохраняется как атрибут экземпляра."""
        svc = WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)
        assert svc.log_service is mock_log_service

    def test_constructor_stores_log_repo(self, mock_log_service, mock_log_repo):
        """Зависимость log_repo сохраняется как атрибут экземпляра."""
        svc = WebhookService(log_service=mock_log_service, log_repo=mock_log_repo)
        assert svc.log_repo is mock_log_repo


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Извлечение trace_id (спецификация §4, шаг 1)
# ═══════════════════════════════════════════════════════════════════════════


class TestTraceIdExtraction:
    """Тесты извлечения trace_id из payload (спецификация §4, шаг 1)."""

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
        """Если trace_id нигде нет — генерируется новый UUID."""
        result = await service.process_guardrail_incident(
            payload=sample_payload_no_trace
        )
        assert _UUID_V4_RE.match(result["trace_id"]) is not None

    @pytest.mark.asyncio
    async def test_trace_id_generated_when_empty_string(self, service, mock_log_repo):
        """Если trace_id — пустая строка, генерируется новый UUID."""
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

        # Проверяем incident_payload, переданный в log_service
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
# 4. process_guardrail_incident — Валидация формата trace_id (спецификация §4, шаг 2)
# ═══════════════════════════════════════════════════════════════════════════


class TestTraceIdValidation:
    """Тесты валидации формата trace_id (спецификация §4, шаг 2)."""

    @pytest.mark.asyncio
    async def test_valid_uuid_trace_id_accepted(
        self, service, sample_guardrail_payload, valid_trace_id
    ):
        """Валидный UUID v4 trace_id принимается без проблем."""
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
# 4. process_guardrail_incident — Связь с исходным запросом (спецификация §4, шаг 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestLinkedToPrompt:
    """Тесты проверки связи с исходным запросом (спецификация §4, шаг 3)."""

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
        """Осиротевший инцидент (нет связи) всё равно записывается в журнал."""
        mock_log_repo.get_by_trace_id.return_value = []

        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        mock_log_service.log_guardrail_incident.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Формирование записи инцидента (спецификация §4, шаг 4)
# ═══════════════════════════════════════════════════════════════════════════


class TestIncidentPayloadFormation:
    """Тесты формирования записи инцидента (спецификация §4, шаг 4)."""

    @pytest.mark.asyncio
    async def test_incident_contains_original_webhook_body(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """Запись инцидента содержит original_webhook_body с исходным payload."""
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
        """Запись инцидента содержит trace_id_source."""
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
        """Запись инцидента содержит linked_to_prompt (булево)."""
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
        """Запись инцидента содержит processed_at в формате ISO 8601 UTC."""
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
        """Запись инцидента содержит ровно 4 ключа."""
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
# 4. process_guardrail_incident — Запись в журнал (спецификация §4, шаг 5)
# ═══════════════════════════════════════════════════════════════════════════


class TestJournalWrite:
    """Тесты записи в журнал через log_service (спецификация §4, шаг 5)."""

    @pytest.mark.asyncio
    async def test_log_guardrail_incident_called(
        self, service, mock_log_service, mock_log_repo, sample_guardrail_payload
    ):
        """log_service.log_guardrail_incident вызывается."""
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
        """log_service.log_guardrail_incident получает правильный trace_id."""
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
        """log_service.log_guardrail_incident получает словарь incident_payload."""
        await service.process_guardrail_incident(payload=sample_guardrail_payload)

        call_args = mock_log_service.log_guardrail_incident.call_args
        incident_payload = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("incident_data", call_args[0][1])
        )
        assert isinstance(incident_payload, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 4. process_guardrail_incident — Возврат подтверждения (спецификация §4, шаг 6)
# ═══════════════════════════════════════════════════════════════════════════


class TestReturnConfirmation:
    """Тесты возвращаемого словаря подтверждения (спецификация §4, шаг 6)."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, service, sample_guardrail_payload):
        """Метод возвращает словарь."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_status_accepted(self, service, sample_guardrail_payload):
        """Возвращаемый словарь содержит status='accepted'."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_trace_id_in_response(
        self, service, sample_guardrail_payload, valid_trace_id
    ):
        """Возвращаемый словарь содержит trace_id."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert result["trace_id"] == valid_trace_id

    @pytest.mark.asyncio
    async def test_linked_to_prompt_in_response(
        self, service, sample_guardrail_payload
    ):
        """Возвращаемый словарь содержит linked_to_prompt (булево)."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert "linked_to_prompt" in result
        assert isinstance(result["linked_to_prompt"], bool)

    @pytest.mark.asyncio
    async def test_response_has_exactly_three_keys(
        self, service, sample_guardrail_payload
    ):
        """Возвращаемый словарь содержит ровно 3 ключа: status, trace_id, linked_to_prompt."""
        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )
        assert set(result.keys()) == {"status", "trace_id", "linked_to_prompt"}

    @pytest.mark.asyncio
    async def test_generated_trace_id_in_response_when_missing(
        self, service, sample_payload_no_trace
    ):
        """Сгенерированный trace_id возвращается в ответе."""
        result = await service.process_guardrail_incident(
            payload=sample_payload_no_trace
        )
        assert _UUID_V4_RE.match(result["trace_id"]) is not None


# ═══════════════════════════════════════════════════════════════════════════
# 5. Обработка ошибок (спецификация §5)
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Тесты обработки ошибок (спецификация §5)."""

    @pytest.mark.asyncio
    async def test_empty_payload_returns_rejected(self, service):
        """Пустой payload → status='rejected', reason='empty payload'."""
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

        # Не должно бросить исключение
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
# Интеграционные сценарии (полный путь)
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
        """Полный путь: trace_id из payload, связан с промптом."""
        mock_log_repo.get_by_trace_id.return_value = [fake_chat_request_log]

        result = await service.process_guardrail_incident(
            payload=sample_guardrail_payload
        )

        # 1. Проверка trace_id
        assert result["trace_id"] == valid_trace_id
        # 2. Связь с промптом
        assert result["linked_to_prompt"] is True
        # 3. Статус
        assert result["status"] == "accepted"
        # 4. log_repo.get_by_trace_id вызван
        mock_log_repo.get_by_trace_id.assert_awaited_once_with(valid_trace_id)
        # 5. log_service.log_guardrail_incident вызван
        mock_log_service.log_guardrail_incident.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_flow_orphaned_incident(
        self,
        service,
        mock_log_service,
        mock_log_repo,
        sample_payload_no_trace,
    ):
        """Полный путь: trace_id отсутствует, инцидент осиротевший."""
        mock_log_repo.get_by_trace_id.return_value = []

        result = await service.process_guardrail_incident(
            payload=sample_payload_no_trace
        )

        # 1. trace_id сгенерирован
        assert _UUID_V4_RE.match(result["trace_id"]) is not None
        # 2. Нет связи с промптом
        assert result["linked_to_prompt"] is False
        # 3. Статус
        assert result["status"] == "accepted"
        # 4. Запись всё равно произведена
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
        """Полный путь: trace_id из metadata, связан с промптом."""
        mock_log_repo.get_by_trace_id.return_value = [fake_chat_request_log]

        result = await service.process_guardrail_incident(
            payload=sample_payload_trace_in_metadata
        )

        assert result["trace_id"] == valid_trace_id
        assert result["linked_to_prompt"] is True
        assert result["status"] == "accepted"

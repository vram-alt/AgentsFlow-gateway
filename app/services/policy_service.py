"""
PolicyService — сервис политик безопасности (Guardrails).
Координирует CRUD между локальной БД и облаком провайдера.

Спецификация: app/services/policy_service_spec.md
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.dto.gateway_error import GatewayError


def _make_error(error_code: str, message: str) -> GatewayError:
    """Фабрика для создания GatewayError с автоматическим trace_id."""
    return GatewayError(
        trace_id=str(uuid.uuid4()),
        error_code=error_code,
        message=message,
    )


class PolicyService:
    """Сервис управления политиками безопасности (Guardrails)."""

    def __init__(
        self,
        *,
        policy_repo: Any,
        provider_repo: Any,
        adapter: Any,
        log_service: Any,
    ) -> None:
        self.policy_repo = policy_repo
        self.provider_repo = provider_repo
        self.adapter = adapter
        self.log_service = log_service

    # ── 3. create_policy ─────────────────────────────────────────────
    async def create_policy(
        self,
        name: str,
        body: dict[str, Any],
        provider_name: str = "portkey",
    ) -> Any:
        """Создание политики: облако → БД → возврат Policy."""
        # 1. Получить учётные данные провайдера
        provider = await self.provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return _make_error("AUTH_FAILED", "Провайдер не найден")

        # 2. Отправить конфигурацию в облако
        cloud_result = await self.adapter.create_guardrail(
            body, provider.api_key, provider.base_url
        )
        if isinstance(cloud_result, GatewayError):
            return cloud_result

        # 3. Сохранить в локальную БД
        try:
            created = await self.policy_repo.create(
                name=name,
                body=body,
                remote_id=cloud_result["remote_id"],
                provider_id=provider.id,
            )
        except Exception:
            return _make_error("UNKNOWN", "Ошибка при сохранении в БД")

        # 4. Вернуть доменную сущность
        return created

    # ── 4. update_policy ─────────────────────────────────────────────
    async def update_policy(
        self,
        policy_id: int,
        name: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Обновление политики: проверка → облако (если нужно) → БД."""
        # 1. Найти политику в БД
        policy = await self.policy_repo.get_by_id(policy_id)
        if policy is None:
            return _make_error("VALIDATION_ERROR", "Политика не найдена")

        # 2. Если изменилось body и есть remote_id — синхронизация с облаком
        if body is not None and policy.remote_id:
            provider = await self.provider_repo.get_active_by_name("portkey")
            cloud_result = await self.adapter.update_guardrail(
                policy.remote_id, body, provider.api_key, provider.base_url
            )
            if isinstance(cloud_result, GatewayError):
                return cloud_result

        # 3. Обновить запись в БД
        changed: dict[str, Any] = {}
        if name is not None:
            changed["name"] = name
        if body is not None:
            changed["body"] = body

        updated = await self.policy_repo.update(policy_id, **changed)

        # 4. Вернуть обновлённую сущность
        return updated

    # ── 5. delete_policy ─────────────────────────────────────────────
    async def delete_policy(self, policy_id: int) -> Any:
        """Удаление политики: облако (если есть remote_id) → soft_delete в БД."""
        # 1. Найти политику в БД
        policy = await self.policy_repo.get_by_id(policy_id)
        if policy is None:
            return _make_error("VALIDATION_ERROR", "Политика не найдена")

        # 2. Если есть remote_id — удалить в облаке
        if policy.remote_id:
            provider = await self.provider_repo.get_active_by_name("portkey")
            cloud_result = await self.adapter.delete_guardrail(
                policy.remote_id, provider.api_key, provider.base_url
            )
            if isinstance(cloud_result, GatewayError):
                return cloud_result

        # 3. Soft delete в БД
        result = await self.policy_repo.soft_delete(policy_id)

        # 4. Вернуть True
        return result

    # ── 6. list_policies ─────────────────────────────────────────────
    async def list_policies(self, only_active: bool = True) -> list[Any]:
        """Получение списка политик из БД."""
        return await self.policy_repo.list_all(only_active=only_active)

    # ── 7. sync_policies_from_provider ───────────────────────────────
    async def sync_policies_from_provider(self, provider_name: str = "portkey") -> Any:
        """Синхронизация политик из облака провайдера в локальную БД."""
        # 1. Получить учётные данные провайдера
        provider = await self.provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return _make_error("AUTH_FAILED", "Провайдер не найден")

        # 2. Запросить список политик из облака
        cloud_policies = await self.adapter.list_guardrails(
            provider.api_key, provider.base_url
        )
        if isinstance(cloud_policies, GatewayError):
            return cloud_policies

        # 3. Для каждой политики из облака — синхронизировать
        created = 0
        updated = 0
        unchanged = 0

        for remote_policy in cloud_policies:
            try:
                existing = await self.policy_repo.get_by_remote_id(
                    remote_policy["remote_id"]
                )

                if existing is None:
                    # Создать новую запись
                    await self.policy_repo.create(
                        name=remote_policy["name"],
                        body=remote_policy["config"],
                        remote_id=remote_policy["remote_id"],
                        provider_id=provider.id,
                    )
                    created += 1
                else:
                    # Проверить, изменились ли данные (сравниваем только body)
                    if existing.body != remote_policy["config"]:
                        await self.policy_repo.update(
                            existing.id if hasattr(existing, "id") else None,
                            name=remote_policy["name"],
                            body=remote_policy["config"],
                        )
                        updated += 1
                    else:
                        unchanged += 1
            except Exception:
                # [SRE_MARKER] Ошибка при синхронизации одной политики — пропустить
                continue

        # 4. Вернуть отчёт
        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "total_remote": len(cloud_policies),
        }

"""
PolicyService — security policy (Guardrails) service.
Coordinates CRUD between local DB and cloud provider.

Spec: app/services/policy_service_spec.md
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.infrastructure.database.models import PolicyModel
from app.infrastructure.database.repositories import (
    PolicyRepository,
    ProviderRepository,
)
from app.services.log_service import LogService

logger = logging.getLogger(__name__)


# Map error codes to appropriate HTTP status codes
_ERROR_CODE_STATUS: dict[str, int] = {
    "AUTH_FAILED": 424,  # Failed Dependency — provider not configured
    "VALIDATION_ERROR": 404,  # Not Found — resource doesn't exist
    "RATE_LIMITED": 429,  # Too Many Requests
    "TIMEOUT": 504,  # Gateway Timeout
    "PROVIDER_ERROR": 502,  # Bad Gateway — upstream provider error
    "UNKNOWN": 500,  # Internal Server Error
}


def _make_error(error_code: str, message: str) -> GatewayError:
    """Factory for creating GatewayError with automatic trace_id and proper status_code."""
    return GatewayError(
        trace_id=str(uuid.uuid4()),
        error_code=error_code,
        message=message,
        status_code=_ERROR_CODE_STATUS.get(error_code, 500),
    )


class PolicyService:
    """Service for managing security policies (Guardrails)."""

    def __init__(
        self,
        *,
        policy_repo: PolicyRepository,
        provider_repo: ProviderRepository,
        adapter: GatewayProvider,
        log_service: LogService,
    ) -> None:
        """[YEL-1] Concrete types instead of Any for dependency injection."""
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
    ) -> PolicyModel | GatewayError:
        """Create policy: cloud -> DB -> return Policy."""
        # 1. Get provider credentials
        provider = await self.provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return _make_error(
                "AUTH_FAILED",
                f"Provider '{provider_name}' not found or inactive — add it in Configuration > Providers first",
            )

        # 2. Build the cloud config — ensure 'name' is included for Portkey API
        cloud_config = dict(body)
        if "name" not in cloud_config:
            cloud_config["name"] = name

        # 3. Send configuration to cloud
        cloud_result = await self.adapter.create_guardrail(
            cloud_config, provider.api_key, provider.base_url
        )
        if isinstance(cloud_result, GatewayError):
            return cloud_result

        # 4. Save to local DB
        try:
            created = await self.policy_repo.create(
                name=name,
                body=body,
                remote_id=cloud_result["remote_id"],
                provider_id=provider.id,
            )
        except Exception as exc:
            logger.error("Failed to save policy to DB: %s", exc)
            return _make_error("UNKNOWN", f"Failed to save policy to database: {exc}")

        # 5. Return domain entity
        return created

    # ── 4. update_policy ─────────────────────────────────────────────
    async def update_policy(
        self,
        policy_id: int,
        name: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> PolicyModel | GatewayError | None:
        """Update policy: check -> cloud (if needed) -> DB."""
        # 1. Find policy in DB
        policy = await self.policy_repo.get_by_id(policy_id)
        if policy is None:
            return _make_error(
                "VALIDATION_ERROR",
                f"Policy with ID {policy_id} not found — it may have been deleted",
            )

        # 2. If body changed and remote_id exists — sync with cloud
        if body is not None and policy.remote_id:
            provider = await self.provider_repo.get_active_by_name("portkey")
            # [RED-2] Guard against None provider
            if provider is None:
                return _make_error(
                    "AUTH_FAILED",
                    "Provider 'portkey' not found or inactive — add it in Configuration > Providers first",
                )
            cloud_result = await self.adapter.update_guardrail(
                policy.remote_id, body, provider.api_key, provider.base_url
            )
            if isinstance(cloud_result, GatewayError):
                return cloud_result

        # 3. Update record in DB
        changed: dict[str, Any] = {}
        if name is not None:
            changed["name"] = name
        if body is not None:
            changed["body"] = body

        updated = await self.policy_repo.update(policy_id, **changed)

        # 4. Return updated entity
        return updated

    # ── 5. delete_policy ─────────────────────────────────────────────
    async def delete_policy(self, policy_id: int) -> bool | GatewayError:
        """Delete policy: cloud (if remote_id exists) -> soft_delete in DB.

        If cloud deletion fails with AUTH_FAILED (403) or PROVIDER_ERROR (404),
        we still proceed with local soft-delete — the guardrail may not exist
        on the cloud anymore (e.g., demo-mode IDs or already deleted).
        """
        # 1. Find policy in DB
        policy = await self.policy_repo.get_by_id(policy_id)
        if policy is None:
            return _make_error(
                "VALIDATION_ERROR",
                f"Policy with ID {policy_id} not found — it may have been deleted",
            )

        # 2. If remote_id exists — try to delete in cloud
        if policy.remote_id:
            provider = await self.provider_repo.get_active_by_name("portkey")
            if provider is None:
                # Provider not configured — skip cloud deletion, proceed with local soft-delete
                logger.warning(
                    "Provider 'portkey' not found during delete of policy %s — "
                    "skipping cloud deletion, proceeding with local soft-delete",
                    policy_id,
                )
            else:
                cloud_result = await self.adapter.delete_guardrail(
                    policy.remote_id, provider.api_key, provider.base_url
                )
                if isinstance(cloud_result, GatewayError):
                    # If cloud returns 403 (no permission) or 404 (not found),
                    # proceed with local deletion — the guardrail may not exist
                    # on the cloud (demo IDs, already deleted, or insufficient permissions)
                    if cloud_result.error_code in ("AUTH_FAILED", "PROVIDER_ERROR"):
                        logger.warning(
                            "Cloud deletion failed for policy %s (remote_id=%s): %s — "
                            "proceeding with local soft-delete",
                            policy_id,
                            policy.remote_id,
                            cloud_result.message,
                        )
                    else:
                        # For other errors (timeout, rate limit, etc.) — return the error
                        return cloud_result

        # 3. Hard delete from DB (permanent removal so it doesn't reappear in list)
        result = await self.policy_repo.hard_delete(policy_id)

        # 4. Return True
        return result

    # ── 6. list_policies ─────────────────────────────────────────────
    async def list_policies(self, only_active: bool = True) -> Sequence[PolicyModel]:
        """Get list of policies from DB."""
        return await self.policy_repo.list_all(only_active=only_active)

    # ── 6b. toggle_policy ────────────────────────────────────────────
    async def toggle_policy(self, policy_id: int) -> PolicyModel | GatewayError:
        """Toggle is_active status of a policy."""
        result = await self.policy_repo.toggle_active(policy_id)
        if result is None:
            return _make_error(
                "VALIDATION_ERROR",
                f"Policy with ID {policy_id} not found — it may have been deleted",
            )
        return result

    # ── 7. sync_policies_from_provider ───────────────────────────────
    async def sync_policies_from_provider(
        self, provider_name: str = "portkey"
    ) -> dict[str, int] | GatewayError:
        """Sync policies from cloud provider to local DB.

        Full two-way sync:
        - Creates local policies for cloud guardrails not in DB
        - Updates local policies if cloud config changed
        - Soft-deletes local policies whose remote_id no longer exists in cloud
        """
        # 1. Get provider credentials
        provider = await self.provider_repo.get_active_by_name(provider_name)
        if provider is None:
            return _make_error(
                "AUTH_FAILED",
                f"Provider '{provider_name}' not found or inactive — add it in Configuration > Providers first",
            )

        # 2. Request policy list from cloud
        cloud_policies = await self.adapter.list_guardrails(
            provider.api_key, provider.base_url
        )
        if isinstance(cloud_policies, GatewayError):
            return cloud_policies

        # 3. Build set of cloud remote IDs
        cloud_remote_ids: set[str] = set()
        for rp in cloud_policies:
            rid = rp.get("remote_id")
            if rid:
                cloud_remote_ids.add(rid)

        # 4. For each cloud policy — create or update locally
        created = 0
        updated = 0
        unchanged = 0

        for remote_policy in cloud_policies:
            try:
                remote_id = remote_policy.get("remote_id")
                if not remote_id:
                    continue

                existing = await self.policy_repo.get_by_remote_id(remote_id)

                policy_name = remote_policy.get("name") or f"synced-{remote_id}"
                policy_config = remote_policy.get("config") or {}

                if existing is None:
                    # Create new record
                    await self.policy_repo.create(
                        name=policy_name,
                        body=policy_config,
                        remote_id=remote_id,
                        provider_id=provider.id,
                    )
                    created += 1
                else:
                    # Check if data changed (compare body only)
                    if existing.body != policy_config:
                        await self.policy_repo.update(
                            existing.id if hasattr(existing, "id") else None,
                            name=policy_name,
                            body=policy_config,
                        )
                        updated += 1
                    else:
                        unchanged += 1
            except Exception as exc:
                # [SRE_MARKER] [YEL-4] Error syncing one policy — skip but log
                logger.warning(
                    "Error syncing policy %s: %s", remote_policy.get("remote_id"), exc
                )
                continue

        # 5. Remove local policies whose remote_id no longer exists in cloud
        deleted = 0
        all_local = await self.policy_repo.list_all(only_active=False)
        for local_policy in all_local:
            if (
                local_policy.remote_id
                and local_policy.remote_id not in cloud_remote_ids
            ):
                # This policy was synced from cloud but no longer exists there
                try:
                    await self.policy_repo.hard_delete(local_policy.id)
                    deleted += 1
                    logger.info(
                        "Soft-deleted local policy %s (remote_id=%s) — "
                        "no longer exists in cloud",
                        local_policy.id,
                        local_policy.remote_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "Error deleting orphaned policy %s: %s",
                        local_policy.id,
                        exc,
                    )

        # 6. Return report
        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "deleted": deleted,
            "total_remote": len(cloud_policies),
        }

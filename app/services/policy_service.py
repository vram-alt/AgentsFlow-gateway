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
from urllib.parse import urlparse

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


def _validate_http_url(url: Any, field_name: str) -> str | None:
    """Validate that a guardrail URL is a non-empty http/https endpoint."""
    if not isinstance(url, str) or not url.strip():
        return f"{field_name} must be a non-empty http/https URL"

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return f"{field_name} must be a valid http/https URL"
    return None


def _validate_headers_object(headers: Any, field_name: str) -> str | None:
    """Validate optional headers for Portkey Webhook / Log checks."""
    if headers is None:
        return None
    if not isinstance(headers, dict):
        return f"{field_name} must be a JSON object of header names to values"

    for key, value in headers.items():
        if not isinstance(key, str) or not key.strip():
            return f"{field_name} keys must be non-empty strings"
        if not isinstance(value, (str, int, float, bool)):
            return f"{field_name}['{key}'] must be a string, number, or boolean"
    return None


def _validate_custom_guardrail_body(body: dict[str, Any]) -> str | None:
    """Validate custom guardrail check parameters without affecting other policies."""
    checks = body.get("checks")
    if checks is None:
        return None
    if not isinstance(checks, list):
        return "Policy body field 'checks' must be a list"

    for index, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            return f"Policy check #{index} must be a JSON object"

        check_id = str(check.get("id", "")).strip().lower()
        parameters = check.get("parameters") or {}
        if not isinstance(parameters, dict):
            return f"Policy check #{index} parameters must be a JSON object"

        if "webhook" in check_id:
            error = _validate_http_url(
                parameters.get("webhookURL"),
                f"checks[{index}].parameters.webhookURL",
            )
            if error:
                return error
            error = _validate_headers_object(
                parameters.get("headers"),
                f"checks[{index}].parameters.headers",
            )
            if error:
                return error

        if check_id == "log" or check_id.endswith(".log"):
            error = _validate_http_url(
                parameters.get("logURL"),
                f"checks[{index}].parameters.logURL",
            )
            if error:
                return error
            error = _validate_headers_object(
                parameters.get("headers"),
                f"checks[{index}].parameters.headers",
            )
            if error:
                return error

        for timeout_key in ("timeout", "timeoutMs"):
            timeout_value = parameters.get(timeout_key)
            if timeout_value is not None and (
                not isinstance(timeout_value, int) or timeout_value <= 0
            ):
                return (
                    f"checks[{index}].parameters.{timeout_key} must be a positive integer"
                )

        # ── Validate deterministic BASIC check parameters ────────
        error = _validate_deterministic_check_params(index, check_id, parameters)
        if error:
            return error

    return None


def _validate_range_params(
    index: int,
    parameters: dict[str, Any],
    min_key: str,
    max_key: str,
) -> str | None:
    """Validate that min/max range parameters are non-negative integers."""
    for key in (min_key, max_key):
        value = parameters.get(key)
        if value is not None:
            if not isinstance(value, (int, float)) or value < 0:
                return f"checks[{index}].parameters.{key} must be a non-negative number"
    min_val = parameters.get(min_key)
    max_val = parameters.get(max_key)
    if min_val is not None and max_val is not None and min_val > max_val:
        return f"checks[{index}].parameters.{min_key} must be <= {max_key}"
    return None


def _validate_deterministic_check_params(
    index: int, check_id: str, parameters: dict[str, Any]
) -> str | None:
    """Validate parameters for deterministic Portkey BASIC checks."""
    if "sentencecount" in check_id:
        return _validate_range_params(index, parameters, "minSentences", "maxSentences")

    if "wordcount" in check_id:
        return _validate_range_params(index, parameters, "minWords", "maxWords")

    if "charactercount" in check_id:
        return _validate_range_params(index, parameters, "minCharacters", "maxCharacters")

    if "endswith" in check_id:
        suffix = parameters.get("Suffix") or parameters.get("suffix")
        if suffix is not None and not isinstance(suffix, str):
            return f"checks[{index}].parameters.Suffix must be a string"

    if "jsonschema" in check_id:
        schema = parameters.get("schema")
        if schema is not None and not isinstance(schema, dict):
            return f"checks[{index}].parameters.schema must be a JSON object"

    if "jsonkeys" in check_id:
        keys = parameters.get("keys")
        if keys is not None and not isinstance(keys, list):
            return f"checks[{index}].parameters.keys must be an array"
        operator = parameters.get("operator")
        if operator is not None and str(operator).lower() not in ("any", "all", "none"):
            return f"checks[{index}].parameters.operator must be 'any', 'all', or 'none'"

    if check_id in ("default.contains", "contains"):
        words = parameters.get("words")
        if words is not None and not isinstance(words, list):
            return f"checks[{index}].parameters.words must be an array"
        operator = parameters.get("operator")
        if operator is not None and str(operator).lower() not in ("any", "all", "none"):
            return f"checks[{index}].parameters.operator must be 'any', 'all', or 'none'"

    if "modelwhitelist" in check_id:
        models = parameters.get("Models") or parameters.get("models")
        if models is not None and not isinstance(models, list):
            return f"checks[{index}].parameters.Models must be an array"

    if "modelrules" in check_id:
        rules = parameters.get("rules")
        if rules is not None and not isinstance(rules, dict):
            return f"checks[{index}].parameters.rules must be a JSON object"

    if "allowedrequesttypes" in check_id:
        for key in ("allowedTypes", "blockedTypes"):
            val = parameters.get(key)
            if val is not None and not isinstance(val, list):
                return f"checks[{index}].parameters.{key} must be an array"

    if "requiredmetadatakeyvalue" in check_id:
        pairs = parameters.get("metadataPairs")
        if pairs is not None and not isinstance(pairs, dict):
            return f"checks[{index}].parameters.metadataPairs must be a JSON object"
    elif "requiredmetadatakey" in check_id:
        keys = parameters.get("metadataKeys")
        if keys is not None and not isinstance(keys, list):
            return f"checks[{index}].parameters.metadataKeys must be an array"

    return None


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

        # 2. Validate custom Webhook / Log checks without changing normal policies
        validation_error = _validate_custom_guardrail_body(body)
        if validation_error:
            return _make_error("VALIDATION_ERROR", validation_error)

        # 3. Build the cloud config — ensure 'name' is included for Portkey API
        cloud_config = dict(body)
        if "name" not in cloud_config:
            cloud_config["name"] = name

        # 3. Send configuration to cloud
        cloud_result = await self.adapter.create_guardrail(
            cloud_config, provider.api_key, provider.base_url
        )

        remote_id: str | None = None
        if isinstance(cloud_result, GatewayError):
            # If cloud returns 403 (no permission) or 404 (not found),
            # proceed with local-only save — the API key may not have
            # write access or the endpoint may not be available.
            if cloud_result.error_code in ("AUTH_FAILED", "PROVIDER_ERROR"):
                logger.warning(
                    "Cloud creation failed for policy '%s': %s — "
                    "saving locally without remote_id",
                    name,
                    cloud_result.message,
                )
                remote_id = None
            else:
                return cloud_result
        else:
            remote_id = cloud_result["remote_id"]

        # 4. Save to local DB
        try:
            created = await self.policy_repo.create(
                name=name,
                body=body,
                remote_id=remote_id,
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

        # 2. Validate custom Webhook / Log checks without affecting other updates
        if body is not None:
            validation_error = _validate_custom_guardrail_body(body)
            if validation_error:
                return _make_error("VALIDATION_ERROR", validation_error)

        # 3. If body changed and remote_id exists — sync with cloud
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

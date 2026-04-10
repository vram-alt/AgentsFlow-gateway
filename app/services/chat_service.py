"""
ChatService — orchestrator for the full prompt-to-LLM cycle via an adapter.

Specification: app/services/chat_service_spec.md
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

from app.domain.contracts.gateway_provider import GatewayProvider
from app.domain.dto.gateway_error import GatewayError
from app.domain.dto.unified_prompt import MessageItem, UnifiedPrompt
from app.domain.dto.unified_response import UnifiedResponse
from app.infrastructure.database.repositories import PolicyRepository, ProviderRepository
from app.services.log_service import LogService

logger = logging.getLogger(__name__)


class ChatService:
    """Chat orchestrator: provider → adapter → log → response."""

    def __init__(
        self,
        provider_repo: ProviderRepository,
        log_service: LogService,
        adapter: GatewayProvider,
        policy_repo: PolicyRepository | None = None,
    ) -> None:
        """[YEL-1] Concrete types instead of Any for dependency injection."""
        self.provider_repo = provider_repo
        self.policy_repo = policy_repo
        self.log_service = log_service
        self.adapter = adapter

    async def send_chat_message(
        self,
        model: str,
        messages: list[dict[str, str]],
        provider_name: str = "portkey",
        temperature: float | None = None,
        max_tokens: int | None = None,
        guardrail_ids: list[str] | None = None,
    ) -> UnifiedResponse | GatewayError:
        """Full cycle: evaluate local guardrails → provider → log → return."""

        trace_id = str(uuid.uuid4())
        result: UnifiedResponse | GatewayError

        requested_guardrail_ids = [
            guardrail_id.strip()
            for guardrail_id in (guardrail_ids or [])
            if isinstance(guardrail_id, str) and guardrail_id.strip()
        ]
        effective_guardrail_ids = list(requested_guardrail_ids)
        remote_guardrail_ids = list(requested_guardrail_ids)
        local_policies: list[Any] = []

        if self.policy_repo is not None:
            (
                effective_guardrail_ids,
                remote_guardrail_ids,
                local_policies,
            ) = await self._resolve_effective_guardrails(requested_guardrail_ids)

        prompt = UnifiedPrompt(
            trace_id=trace_id,
            model=model,
            messages=[MessageItem(**m) for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            guardrail_ids=effective_guardrail_ids,
        )

        local_guardrail_state: dict[str, Any] | None = None
        if local_policies:
            local_guardrail_state = await self._evaluate_local_policies(
                trace_id=trace_id,
                model=model,
                messages=messages,
                policies=local_policies,
            )
            blocked_response = local_guardrail_state.get("blocked_response") if local_guardrail_state else None
            if isinstance(blocked_response, UnifiedResponse):
                await self._safe_log(
                    trace_id=trace_id,
                    prompt=prompt,
                    response=blocked_response,
                )
                return blocked_response

        try:
            provider_record = await self.provider_repo.get_active_by_name(provider_name)
        except Exception as exc:
            logger.error("DB error fetching provider %s: %s", provider_name, exc)
            result = GatewayError(
                trace_id=trace_id,
                error_code="UNKNOWN",
                message=f"Failed to fetch provider credentials from database: {exc}",
            )
            await self._safe_log(trace_id=trace_id, prompt=prompt, response=result)
            return result

        if provider_record is None:
            result = GatewayError(
                trace_id=trace_id,
                error_code="AUTH_FAILED",
                message=f"Provider '{provider_name}' not found or inactive — add it in Configuration > Providers first",
            )
            await self._safe_log(trace_id=trace_id, prompt=prompt, response=result)
            return result

        api_key: str = provider_record.api_key
        base_url: str = provider_record.base_url
        adapter_prompt = prompt.model_copy(update={"guardrail_ids": remote_guardrail_ids})

        try:
            result = await self.adapter.send_prompt(adapter_prompt, api_key, base_url)
        except Exception as exc:
            logger.error("Adapter exception: %s", exc)
            result = GatewayError(
                trace_id=trace_id,
                error_code="UNKNOWN",
                message=f"Adapter error: {exc}",
            )

        local_details = local_guardrail_state.get("details") if local_guardrail_state else None
        if isinstance(result, UnifiedResponse) and local_details:
            result = result.model_copy(
                update={
                    "guardrail_details": self._merge_guardrail_details(
                        local_details,
                        result.guardrail_details,
                    )
                }
            )

        await self._safe_log(trace_id=trace_id, prompt=prompt, response=result)
        return result

    async def _resolve_effective_guardrails(
        self,
        requested_guardrail_ids: list[str],
    ) -> tuple[list[str], list[str], list[Any]]:
        """Resolve active local/cloud policies for the current chat request."""
        if self.policy_repo is None:
            return requested_guardrail_ids, requested_guardrail_ids, []

        try:
            active_policies = list(await self.policy_repo.list_all(only_active=True))
        except Exception as exc:
            logger.warning("Policy lookup failed (continuing without local guardrails): %s", exc)
            return requested_guardrail_ids, requested_guardrail_ids, []

        if not requested_guardrail_ids:
            effective_ids: list[str] = []
            remote_ids: list[str] = []
            local_policies: list[Any] = []
            for policy in active_policies:
                identifier = self._policy_identifier(policy)
                if identifier and identifier not in effective_ids:
                    effective_ids.append(identifier)

                remote_id = getattr(policy, "remote_id", None)
                if isinstance(remote_id, str) and remote_id.strip():
                    if remote_id not in remote_ids:
                        remote_ids.append(remote_id.strip())
                else:
                    local_policies.append(policy)

            return effective_ids, remote_ids, local_policies

        requested_set = set(requested_guardrail_ids)
        selected_policies = [
            policy
            for policy in active_policies
            if self._policy_matches_token(policy, requested_set)
        ]

        remote_ids = [
            policy.remote_id.strip()
            for policy in selected_policies
            if isinstance(getattr(policy, "remote_id", None), str)
            and policy.remote_id.strip()
        ]
        unresolved_ids = [
            token for token in requested_guardrail_ids if token not in remote_ids
        ]
        for token in unresolved_ids:
            if token not in remote_ids and not any(
                str(getattr(policy, "name", "")).strip() == token
                or str(getattr(policy, "id", "")).strip() == token
                for policy in selected_policies
            ):
                remote_ids.append(token)

        local_policies = [
            policy for policy in selected_policies if not getattr(policy, "remote_id", None)
        ]
        return requested_guardrail_ids, remote_ids, local_policies

    @staticmethod
    def _policy_identifier(policy: Any) -> str:
        """Return the best identifier for a policy in logs/UI."""
        remote_id = getattr(policy, "remote_id", None)
        if isinstance(remote_id, str) and remote_id.strip():
            return remote_id.strip()
        name = getattr(policy, "name", None)
        if isinstance(name, str) and name.strip():
            return name.strip()
        return str(getattr(policy, "id", ""))

    @classmethod
    def _policy_matches_token(cls, policy: Any, tokens: set[str]) -> bool:
        """Check whether any requested token refers to the given policy."""
        candidates = {
            cls._policy_identifier(policy),
            str(getattr(policy, "id", "")).strip(),
        }
        remote_id = getattr(policy, "remote_id", None)
        if isinstance(remote_id, str) and remote_id.strip():
            candidates.add(remote_id.strip())
        name = getattr(policy, "name", None)
        if isinstance(name, str) and name.strip():
            candidates.add(name.strip())
        return any(candidate in tokens for candidate in candidates if candidate)

    @staticmethod
    def _coerce_policy_body(raw_body: Any) -> dict[str, Any]:
        """Normalize a policy body from DB/storage into a plain dict."""
        if isinstance(raw_body, dict):
            return raw_body
        if isinstance(raw_body, str):
            try:
                parsed = json.loads(raw_body)
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _extract_text_from_messages(messages: list[dict[str, str]]) -> str:
        """Join chat message contents into a single text blob for local checks."""
        return "\n".join(
            str(message.get("content", "")).strip()
            for message in messages
            if str(message.get("content", "")).strip()
        )

    async def _evaluate_local_policies(
        self,
        *,
        trace_id: str,
        model: str,
        messages: list[dict[str, str]],
        policies: Sequence[Any],
    ) -> dict[str, Any] | None:
        """Apply local-only policies in the gateway before contacting the provider."""
        if not policies:
            return None

        request_payload = {
            "trace_id": trace_id,
            "metadata": {
                "trace_id": trace_id,
                "source": "local-guardrail-evaluator",
            },
            "request": {
                "text": self._extract_text_from_messages(messages),
                "json": {
                    "model": model,
                    "messages": messages,
                },
            },
            "response": {},
        }

        hooks: list[dict[str, Any]] = []
        passed_checks: list[dict[str, Any]] = []
        failed_checks: list[dict[str, Any]] = []
        blocked_policy_names: list[str] = []

        for policy in policies:
            hook = await self._evaluate_single_local_policy(policy, request_payload)
            hooks.append(hook)

            for check in hook.get("checks", []):
                check_info = {
                    "id": check.get("id", "unknown"),
                    "verdict": bool(check.get("verdict", False)),
                    "explanation": str(check.get("explanation", "")),
                }
                if check_info["verdict"]:
                    passed_checks.append(check_info)
                else:
                    failed_checks.append(check_info)

            if not hook.get("verdict", True) and hook.get("deny", False):
                blocked_policy_names.append(str(getattr(policy, "name", hook.get("id", "unknown"))))

        summary = (
            f"Blocked by local policy: {', '.join(blocked_policy_names)}"
            if blocked_policy_names
            else "All local guardrails passed"
        )
        details = {
            "summary": summary,
            "hooks": hooks,
            "failed_checks": failed_checks,
            "passed_checks": passed_checks,
        }

        blocked_response: UnifiedResponse | None = None
        if blocked_policy_names:
            blocked_response = UnifiedResponse(
                trace_id=trace_id,
                content=summary,
                model=model,
                provider_raw={
                    "source": "local-guardrail-evaluator",
                    "blocked_policies": blocked_policy_names,
                },
                guardrail_blocked=True,
                guardrail_details=details,
            )

        return {
            "details": details,
            "blocked_response": blocked_response,
        }

    async def _evaluate_single_local_policy(
        self,
        policy: Any,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate one local policy body and return a Portkey-like hook result."""
        body = self._coerce_policy_body(getattr(policy, "body", {}))
        checks = body.get("checks")
        actions = body.get("actions") if isinstance(body.get("actions"), dict) else {}
        deny = bool(body.get("deny")) or str(actions.get("onFail", "")).strip().lower() == "block"

        check_results: list[dict[str, Any]] = []
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    check_results.append(
                        {
                            "id": "invalid-check",
                            "verdict": False,
                            "explanation": "Local policy contains an invalid check definition.",
                        }
                    )
                    continue
                check_results.append(await self._evaluate_local_check(check, request_payload))

        if not check_results:
            check_results.append(
                {
                    "id": "local.noop",
                    "verdict": True,
                    "explanation": "No local checks configured.",
                }
            )

        verdict = all(bool(check.get("verdict", False)) for check in check_results)
        return {
            "id": self._policy_identifier(policy),
            "verdict": verdict,
            "deny": deny,
            "checks": check_results,
        }

    async def _evaluate_local_check(
        self,
        check: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate a single local check (regex, webhook, or log)."""
        check_id = str(check.get("id", "unknown")).strip() or "unknown"
        normalized_id = check_id.lower()
        parameters = check.get("parameters") if isinstance(check.get("parameters"), dict) else {}

        if "regexmatch" in normalized_id:
            return self._evaluate_regex_check(check_id, parameters, request_payload)
        if "webhook" in normalized_id:
            return await self._evaluate_webhook_check(check_id, parameters, request_payload)
        if normalized_id == "log" or normalized_id.endswith(".log"):
            return await self._evaluate_log_check(check_id, parameters, request_payload)

        return {
            "id": check_id,
            "verdict": True,
            "explanation": "Unsupported local check skipped.",
        }

    def _evaluate_regex_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate regex-based guardrails locally against the request text."""
        rule = str(parameters.get("rule") or parameters.get("pattern") or "").strip()
        if not rule:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Regex guardrail is missing a rule or pattern.",
            }

        text_to_check = str(request_payload.get("request", {}).get("text", ""))
        try:
            compiled = re.compile(rule, flags=re.IGNORECASE)
        except re.error as exc:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"Invalid regex rule: {exc}",
            }

        match = compiled.search(text_to_check)
        invert_match = bool(parameters.get("not"))
        matched = match is not None
        verdict = not matched if invert_match else matched

        if verdict:
            explanation = "Regex check passed."
        elif matched:
            explanation = f"Blocked by regex rule: {match.group(0)}"
        else:
            explanation = "Message did not satisfy the required regex rule."

        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": explanation,
        }

    async def _evaluate_webhook_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a local/custom validation webhook and interpret its verdict."""
        webhook_url = str(parameters.get("webhookURL") or "").strip()
        if not webhook_url:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Webhook guardrail is missing webhookURL.",
            }

        headers = parameters.get("headers") if isinstance(parameters.get("headers"), dict) else {}
        timeout_ms = parameters.get("timeoutMs") or parameters.get("timeout") or 3000
        timeout_seconds = max(float(timeout_ms) / 1000.0, 1.0)

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    webhook_url,
                    headers={str(key): str(value) for key, value in headers.items()},
                    json=request_payload,
                )
        except Exception as exc:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"Webhook validation failed: {exc}",
            }

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else response.text
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"Webhook validation failed: HTTP {response.status_code} — {detail or response.text}",
            }

        verdict = bool(payload.get("verdict", True)) if isinstance(payload, dict) else True
        explanation = "Webhook validation passed."
        if isinstance(payload, dict):
            explanation = str(payload.get("reason") or explanation)

        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": explanation,
        }

    async def _evaluate_log_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a best-effort local log hook without blocking the request."""
        log_url = str(parameters.get("logURL") or "").strip()
        if not log_url:
            return {
                "id": check_id,
                "verdict": True,
                "explanation": "Log hook skipped because no logURL was configured.",
            }

        headers = parameters.get("headers") if isinstance(parameters.get("headers"), dict) else {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    log_url,
                    headers={str(key): str(value) for key, value in headers.items()},
                    json=request_payload,
                )
            if response.status_code >= 400:
                logger.warning("Local log hook returned HTTP %s for %s", response.status_code, log_url)
                return {
                    "id": check_id,
                    "verdict": True,
                    "explanation": f"Log hook returned HTTP {response.status_code}.",
                }
        except Exception as exc:
            logger.warning("Local log hook failed for %s: %s", log_url, exc)
            return {
                "id": check_id,
                "verdict": True,
                "explanation": f"Log hook failed: {exc}",
            }

        return {
            "id": check_id,
            "verdict": True,
            "explanation": "Log hook executed successfully.",
        }

    @staticmethod
    def _merge_guardrail_details(
        local_details: dict[str, Any] | None,
        provider_details: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Merge local guardrail results with provider-returned guardrail details."""
        if not local_details:
            return provider_details
        if not provider_details:
            return local_details

        def _as_list(value: Any) -> list[Any]:
            return list(value) if isinstance(value, list) else []

        summaries = [
            str(summary).strip()
            for summary in (local_details.get("summary"), provider_details.get("summary"))
            if isinstance(summary, str) and summary.strip()
        ]

        return {
            "summary": " | ".join(summaries) if summaries else None,
            "hooks": _as_list(local_details.get("hooks")) + _as_list(provider_details.get("hooks")),
            "failed_checks": _as_list(local_details.get("failed_checks")) + _as_list(provider_details.get("failed_checks")),
            "passed_checks": _as_list(local_details.get("passed_checks")) + _as_list(provider_details.get("passed_checks")),
        }

    async def _safe_log(
        self,
        trace_id: str,
        prompt: UnifiedPrompt | None,
        response: UnifiedResponse | GatewayError,
    ) -> None:
        """Call log_service.log_chat_request, suppressing any exceptions."""
        try:
            prompt_data: dict[str, Any] = (
                prompt.model_dump() if prompt is not None else {}
            )
            response_data: dict[str, Any] = (
                response.model_dump() if hasattr(response, "model_dump") else {}
            )
            await self.log_service.log_chat_request(
                trace_id=trace_id,
                prompt_data=prompt_data,
                response_data=response_data,
            )
        except Exception as exc:
            logger.warning("Logging failed (suppressed): %s", exc)

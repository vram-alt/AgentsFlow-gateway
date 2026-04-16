"""
ChatService — orchestrator for the full prompt-to-LLM cycle via an adapter.

Specification: app/services/chat_service_spec.md
"""

from __future__ import annotations

import copy
import json
import logging
import re
import uuid
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

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
        metadata: dict[str, Any] | None = None,
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
            metadata=metadata or {},
        )

        local_guardrail_state: dict[str, Any] | None = None
        if local_policies:
            local_guardrail_state = await self._evaluate_local_policies(
                trace_id=trace_id,
                model=model,
                messages=messages,
                policies=local_policies,
                metadata=metadata,
                stage="beforeRequestHook",
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

        post_guardrail_state: dict[str, Any] | None = None
        if isinstance(result, UnifiedResponse) and local_policies:
            post_guardrail_state = await self._evaluate_local_policies(
                trace_id=trace_id,
                model=model,
                messages=messages,
                policies=local_policies,
                metadata=metadata,
                stage="afterResponseHook",
                provider_response=result,
            )
            blocked_response = post_guardrail_state.get("blocked_response") if post_guardrail_state else None
            if isinstance(blocked_response, UnifiedResponse):
                combined_local_details = self._merge_local_guardrail_states(
                    local_guardrail_state.get("details") if local_guardrail_state else None,
                    post_guardrail_state.get("details"),
                )
                blocked_response = blocked_response.model_copy(
                    update={"guardrail_details": combined_local_details}
                )
                await self._safe_log(
                    trace_id=trace_id,
                    prompt=prompt,
                    response=blocked_response,
                )
                return blocked_response

        local_details = self._merge_local_guardrail_states(
            local_guardrail_state.get("details") if local_guardrail_state else None,
            post_guardrail_state.get("details") if post_guardrail_state else None,
        )
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
        metadata: dict[str, Any] | None = None,
        stage: str = "beforeRequestHook",
        provider_response: UnifiedResponse | None = None,
    ) -> dict[str, Any] | None:
        """Apply local-only policies in the gateway before contacting the provider."""
        if not policies:
            return None

        request_payload = self._build_local_request_payload(
            trace_id=trace_id,
            model=model,
            messages=messages,
            metadata=metadata,
            stage=stage,
            provider_response=provider_response,
        )

        hooks: list[dict[str, Any]] = []
        passed_checks: list[dict[str, Any]] = []
        failed_checks: list[dict[str, Any]] = []
        blocked_policy_names: list[str] = []
        blocked_content: str | None = None

        for policy in policies:
            hook = await self._evaluate_single_local_policy(policy, request_payload, stage=stage)
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
                if blocked_content is None and isinstance(hook.get("blocked_content"), str):
                    blocked_content = hook.get("blocked_content")

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
                content=blocked_content or summary,
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
        *,
        stage: str = "beforeRequestHook",
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
                check_results.append(
                    await self._evaluate_local_check(check, request_payload, stage=stage)
                )

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
            "blocked_content": next(
                (
                    str(check.get("blocked_content"))
                    for check in check_results
                    if isinstance(check.get("blocked_content"), str)
                    and str(check.get("blocked_content")).strip()
                ),
                None,
            ),
        }

    async def _evaluate_local_check(
        self,
        check: dict[str, Any],
        request_payload: dict[str, Any],
        stage: str = "beforeRequestHook",
    ) -> dict[str, Any]:
        """Evaluate a single local check (regex, webhook, or log)."""
        check_id = str(check.get("id", "unknown")).strip() or "unknown"
        normalized_id = check_id.lower()
        parameters = check.get("parameters") if isinstance(check.get("parameters"), dict) else {}

        if normalized_id in {"external.validation", "external.validate"}:
            return await self._evaluate_external_validation_check(
                check_id,
                parameters,
                request_payload,
                stage=stage,
            )

        if "regexmatch" in normalized_id:
            return self._evaluate_regex_check(check_id, parameters, request_payload)
        if "webhook" in normalized_id:
            return await self._evaluate_webhook_check(check_id, parameters, request_payload)
        if normalized_id == "log" or normalized_id.endswith(".log"):
            return await self._evaluate_log_check(check_id, parameters, request_payload)

        # ── Deterministic BASIC checks (Portkey-compatible) ──────────
        if "sentencecount" in normalized_id:
            return self._evaluate_sentence_count_check(check_id, parameters, request_payload)
        if "wordcount" in normalized_id:
            return self._evaluate_word_count_check(check_id, parameters, request_payload)
        if "charactercount" in normalized_id:
            return self._evaluate_character_count_check(check_id, parameters, request_payload)
        if "uppercase" in normalized_id:
            return self._evaluate_uppercase_check(check_id, parameters, request_payload)
        if "lowercase" in normalized_id:
            return self._evaluate_lowercase_check(check_id, parameters, request_payload)
        if "endswith" in normalized_id:
            return self._evaluate_ends_with_check(check_id, parameters, request_payload)
        if "jsonschema" in normalized_id:
            return self._evaluate_json_schema_check(check_id, parameters, request_payload)
        if "jsonkeys" in normalized_id:
            return self._evaluate_json_keys_check(check_id, parameters, request_payload)
        if "validurls" in normalized_id:
            return self._evaluate_valid_urls_check(check_id, parameters, request_payload)
        if "containscode" in normalized_id:
            return self._evaluate_contains_code_check(check_id, parameters, request_payload)
        if "notnull" in normalized_id:
            return self._evaluate_not_null_check(check_id, parameters, request_payload)
        if normalized_id in ("default.contains", "contains"):
            return self._evaluate_contains_check(check_id, parameters, request_payload)
        if "modelwhitelist" in normalized_id:
            return self._evaluate_model_whitelist_check(check_id, parameters, request_payload)
        if "modelrules" in normalized_id:
            return self._evaluate_model_rules_check(check_id, parameters, request_payload)
        if "allowedrequesttypes" in normalized_id:
            return self._evaluate_allowed_request_types_check(check_id, parameters, request_payload)
        if "requiredmetadatakeyvalue" in normalized_id:
            return self._evaluate_required_metadata_kv_check(check_id, parameters, request_payload)
        if "requiredmetadatakey" in normalized_id:
            return self._evaluate_required_metadata_keys_check(check_id, parameters, request_payload)

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

    # ── Deterministic BASIC check evaluators ─────────────────────────

    def _evaluate_sentence_count_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content contains a certain number of sentences."""
        text = str(request_payload.get("request", {}).get("text", ""))
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        count = len(sentences)
        try:
            min_s = int(parameters.get("minSentences", 0))
        except (TypeError, ValueError):
            min_s = 0
        try:
            max_s = int(parameters.get("maxSentences", 999999))
        except (TypeError, ValueError):
            max_s = 999999
        verdict = min_s <= count <= max_s
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Sentence count ({count}) {'is' if verdict else 'is not'} "
                f"within range {min_s}–{max_s}."
            ),
        }

    def _evaluate_word_count_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content contains a certain number of words."""
        text = str(request_payload.get("request", {}).get("text", ""))
        count = len(text.split())
        try:
            min_w = int(parameters.get("minWords", 0))
        except (TypeError, ValueError):
            min_w = 0
        try:
            max_w = int(parameters.get("maxWords", 999999))
        except (TypeError, ValueError):
            max_w = 999999
        verdict = min_w <= count <= max_w
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Word count ({count}) {'is' if verdict else 'is not'} "
                f"within range {min_w}–{max_w}."
            ),
        }

    def _evaluate_character_count_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content contains a certain number of characters."""
        text = str(request_payload.get("request", {}).get("text", ""))
        count = len(text)
        try:
            min_c = int(parameters.get("minCharacters", 0))
        except (TypeError, ValueError):
            min_c = 0
        try:
            max_c = int(parameters.get("maxCharacters", 9999999))
        except (TypeError, ValueError):
            max_c = 9999999
        verdict = min_c <= count <= max_c
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Character count ({count}) {'is' if verdict else 'is not'} "
                f"within range {min_c}–{max_c}."
            ),
        }

    def _evaluate_uppercase_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content has all uppercase letters."""
        text = str(request_payload.get("request", {}).get("text", ""))
        is_upper = text == text.upper() if text.strip() else False
        invert = bool(parameters.get("not", False))
        verdict = (not is_upper) if invert else is_upper
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Text {'is' if is_upper else 'is not'} all uppercase"
                f"{' (inverted)' if invert else ''}."
            ),
        }

    def _evaluate_lowercase_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content is all lowercase."""
        text = str(request_payload.get("request", {}).get("text", ""))
        is_lower = text == text.lower() if text.strip() else False
        invert = bool(parameters.get("not", False))
        verdict = (not is_lower) if invert else is_lower
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Text {'is' if is_lower else 'is not'} all lowercase"
                f"{' (inverted)' if invert else ''}."
            ),
        }

    def _evaluate_ends_with_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content ends with a specified string."""
        text = str(request_payload.get("request", {}).get("text", ""))
        suffix = str(parameters.get("Suffix") or parameters.get("suffix") or "")
        if not suffix:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Ends-with check is missing a Suffix parameter.",
            }
        verdict = text.rstrip().endswith(suffix)
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": f"Text {'ends' if verdict else 'does not end'} with '{suffix}'.",
        }

    def _evaluate_json_schema_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if response JSON matches a JSON schema."""
        text = str(request_payload.get("request", {}).get("text", ""))
        schema = parameters.get("schema")
        if not isinstance(schema, dict):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "JSON Schema check is missing a valid schema parameter.",
            }
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Content is not valid JSON.",
            }
        verdict, explanation = self._validate_json_against_schema(data, schema)
        return {"id": check_id, "verdict": verdict, "explanation": explanation}

    @staticmethod
    def _validate_json_against_schema(
        data: Any, schema: dict[str, Any]
    ) -> tuple[bool, str]:
        """Minimal JSON schema validation (type, required, properties)."""
        schema_type = schema.get("type")
        if schema_type:
            type_map: dict[str, type | tuple[type, ...]] = {
                "object": dict,
                "array": list,
                "string": str,
                "number": (int, float),
                "boolean": bool,
            }
            expected = type_map.get(schema_type)
            if expected and not isinstance(data, expected):
                return False, f"Expected type '{schema_type}', got '{type(data).__name__}'."
        if isinstance(data, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in data:
                    return False, f"Missing required key: '{key}'."
            properties = schema.get("properties", {})
            for key, prop_schema in properties.items():
                if key in data and isinstance(prop_schema, dict):
                    ok, msg = ChatService._validate_json_against_schema(data[key], prop_schema)
                    if not ok:
                        return False, f"Property '{key}': {msg}"
        return True, "JSON matches the schema."

    def _evaluate_json_keys_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if response JSON contains any, all or none of the mentioned keys."""
        text = str(request_payload.get("request", {}).get("text", ""))
        keys = parameters.get("keys", [])
        operator = str(parameters.get("operator", "all")).lower()
        if not isinstance(keys, list):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "JSON Keys check requires a 'keys' array.",
            }
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Content is not valid JSON.",
            }
        if not isinstance(data, dict):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Content is not a JSON object.",
            }
        if operator == "all":
            verdict = all(k in data for k in keys)
        elif operator == "any":
            verdict = any(k in data for k in keys)
        elif operator == "none":
            verdict = not any(k in data for k in keys)
        else:
            verdict = all(k in data for k in keys)
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"JSON keys check ({operator}): {'passed' if verdict else 'failed'}. "
                f"Expected keys: {keys}."
            ),
        }

    def _evaluate_valid_urls_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if all URLs mentioned in the content are valid."""
        text = str(request_payload.get("request", {}).get("text", ""))
        url_pattern = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")
        urls = url_pattern.findall(text)
        if not urls:
            return {
                "id": check_id,
                "verdict": True,
                "explanation": "No URLs found in content.",
            }
        invalid = []
        for url in urls:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                invalid.append(url)
        verdict = len(invalid) == 0
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"All {len(urls)} URL(s) are valid."
                if verdict
                else f"{len(invalid)} URL(s) are invalid: {', '.join(invalid[:3])}."
            ),
        }

    def _evaluate_contains_code_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content contains code of a specific format."""
        text = str(request_payload.get("request", {}).get("text", ""))
        code_format = str(parameters.get("format", "")).lower()
        patterns: dict[str, str] = {
            "sql": r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|FROM|WHERE|JOIN)\b",
            "python": r"\b(def |class |import |from .+ import|if __name__)",
            "typescript": r"\b(interface |type |const |let |function |=>|import \{)",
            "javascript": r"\b(function |const |let |var |=>|require\(|import )",
        }
        pattern = patterns.get(
            code_format,
            r"```[\s\S]*?```|\b(def |function |class |SELECT |import )",
        )
        verdict = bool(re.search(pattern, text, re.IGNORECASE))
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Content {'contains' if verdict else 'does not contain'} "
                f"{code_format or 'any'} code."
            ),
        }

    def _evaluate_not_null_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if the response content is not null, undefined, or empty."""
        text = str(request_payload.get("request", {}).get("text", ""))
        is_not_null = bool(text.strip())
        invert = bool(parameters.get("not", False))
        verdict = (not is_not_null) if invert else is_not_null
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Content {'is not' if is_not_null else 'is'} null/empty"
                f"{' (inverted)' if invert else ''}."
            ),
        }

    def _evaluate_contains_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if content contains any, all or none of the words or phrases."""
        text = str(request_payload.get("request", {}).get("text", "")).lower()
        words = parameters.get("words", [])
        operator = str(parameters.get("operator", "any")).lower()
        if not isinstance(words, list):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Contains check requires a 'words' array.",
            }
        matched = [w for w in words if str(w).lower() in text]
        if operator == "all":
            verdict = len(matched) == len(words)
        elif operator == "none":
            verdict = len(matched) == 0
        else:
            verdict = len(matched) > 0
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Contains check ({operator}): {'passed' if verdict else 'failed'}. "
                f"Words: {words}, matched: {matched}."
            ),
        }

    def _evaluate_model_whitelist_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if the inference model is in the whitelist."""
        model = str(
            request_payload.get("request", {}).get("json", {}).get("model", "")
        ).strip().lower()
        models = parameters.get("Models") or parameters.get("models") or []
        inverse = bool(parameters.get("Inverse") or parameters.get("inverse", False))
        if not isinstance(models, list):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Model Whitelist requires a 'Models' array.",
            }
        models_lower = [str(m).strip().lower() for m in models]
        in_list = model in models_lower
        verdict = (not in_list) if inverse else in_list
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Model '{model}' {'is' if in_list else 'is not'} in whitelist"
                f"{' (inverted)' if inverse else ''}."
            ),
        }

    def _evaluate_model_rules_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Allow requests based on metadata-driven rules mapping to allowed models."""
        model = str(
            request_payload.get("request", {}).get("json", {}).get("model", "")
        ).strip().lower()
        metadata = request_payload.get("metadata", {})
        rules = parameters.get("rules", {})
        invert = bool(parameters.get("not", False))
        if not isinstance(rules, dict):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Model Rules requires a 'rules' object.",
            }
        verdict = True
        for meta_key, allowed_models in rules.items():
            if meta_key in metadata:
                if isinstance(allowed_models, list) and model not in [
                    str(m).strip().lower() for m in allowed_models
                ]:
                    verdict = False
                    break
        if invert:
            verdict = not verdict
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Model rules check {'passed' if verdict else 'failed'} "
                f"for model '{model}'."
            ),
        }

    def _evaluate_allowed_request_types_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Control which request types can be processed."""
        request_type = "chat"
        allowed = parameters.get("allowedTypes", [])
        blocked = parameters.get("blockedTypes", [])
        if isinstance(blocked, list) and request_type in blocked:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"Request type '{request_type}' is blocked.",
            }
        if isinstance(allowed, list) and allowed and request_type not in allowed:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"Request type '{request_type}' is not in allowed list.",
            }
        return {
            "id": check_id,
            "verdict": True,
            "explanation": f"Request type '{request_type}' is allowed.",
        }

    def _evaluate_required_metadata_keys_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if metadata contains all the required keys."""
        metadata = request_payload.get("metadata", {})
        keys = parameters.get("metadataKeys", [])
        operator = str(parameters.get("operator", "all")).lower()
        if not isinstance(keys, list):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Required Metadata Keys needs a 'metadataKeys' array.",
            }
        if operator == "all":
            verdict = all(k in metadata for k in keys)
        elif operator == "any":
            verdict = any(k in metadata for k in keys)
        elif operator == "none":
            verdict = not any(k in metadata for k in keys)
        else:
            verdict = all(k in metadata for k in keys)
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Metadata keys check ({operator}): "
                f"{'passed' if verdict else 'failed'}. Required: {keys}."
            ),
        }

    def _evaluate_required_metadata_kv_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if metadata contains specified key-value pairs."""
        metadata = request_payload.get("metadata", {})
        pairs = parameters.get("metadataPairs", {})
        operator = str(parameters.get("operator", "all")).lower()
        if not isinstance(pairs, dict):
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "Required Metadata KV Pairs needs a 'metadataPairs' object.",
            }
        matches = [
            k in metadata and str(metadata[k]) == str(v) for k, v in pairs.items()
        ]
        if operator == "all":
            verdict = all(matches)
        elif operator == "any":
            verdict = any(matches)
        elif operator == "none":
            verdict = not any(matches)
        else:
            verdict = all(matches)
        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": (
                f"Metadata KV check ({operator}): "
                f"{'passed' if verdict else 'failed'}."
            ),
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
    def _extract_latest_text_from_messages(messages: list[dict[str, str]]) -> str:
        """Return the latest non-empty chat message text."""
        for message in reversed(messages):
            content = str(message.get("content", "")).strip()
            if content:
                return content
        return ""

    def _build_local_request_payload(
        self,
        *,
        trace_id: str,
        model: str,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None,
        stage: str,
        provider_response: UnifiedResponse | None,
    ) -> dict[str, Any]:
        """Build the context payload shared with local guardrail checks."""
        request_text = self._extract_text_from_messages(messages)
        latest_text = self._extract_latest_text_from_messages(messages)
        merged_metadata = {
            "trace_id": trace_id,
            "source": "local-guardrail-evaluator",
            **(metadata or {}),
        }
        response_payload: dict[str, Any] = {}
        if provider_response is not None:
            response_payload = {
                "text": provider_response.content,
                "model": provider_response.model,
                "json": provider_response.provider_raw,
            }

        return {
            "trace_id": trace_id,
            "eventType": stage,
            "metadata": merged_metadata,
            "request": {
                "text": request_text,
                "latest_text": latest_text,
                "json": {
                    "model": model,
                    "messages": messages,
                },
            },
            "response": response_payload,
        }

    @staticmethod
    def _extract_path_value(payload: Any, path: str) -> Any:
        """Resolve a dotted path with numeric array indexes from a JSON-like object."""
        if not path:
            return payload

        current = payload
        for raw_part in path.split("."):
            part = raw_part.strip()
            if not part:
                return None
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (TypeError, ValueError, IndexError):
                    return None
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None
        return current

    @classmethod
    def _render_template_string(cls, template: str, context: dict[str, Any]) -> Any:
        """Replace {{path}} tokens inside a string using request/response metadata."""
        exact_match = re.fullmatch(r"\s*\{\{\s*([^{}]+?)\s*\}\}\s*", template)
        if exact_match:
            return cls._extract_path_value(context, exact_match.group(1).strip())

        def _replace(match: re.Match[str]) -> str:
            value = cls._extract_path_value(context, match.group(1).strip())
            if value is None:
                return ""
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)

        return re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", _replace, template)

    @classmethod
    def _render_template_value(cls, template: Any, context: dict[str, Any]) -> Any:
        """Recursively render a template object using {{path}} placeholders."""
        if isinstance(template, str):
            return cls._render_template_string(template, context)
        if isinstance(template, list):
            return [cls._render_template_value(item, context) for item in template]
        if isinstance(template, dict):
            return {
                str(key): cls._render_template_value(value, context)
                for key, value in template.items()
            }
        return copy.deepcopy(template)

    @staticmethod
    def _coerce_verdict(value: Any, *, default: bool = False) -> bool:
        """Normalize a provider-specific verdict payload into a boolean result."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "allow", "allowed", "pass", "passed", "ok"}:
                return True
            if normalized in {"false", "block", "blocked", "deny", "denied", "fail", "failed"}:
                return False
        return default

    async def _evaluate_external_validation_check(
        self,
        check_id: str,
        parameters: dict[str, Any],
        request_payload: dict[str, Any],
        *,
        stage: str,
    ) -> dict[str, Any]:
        """Call a configurable external validation endpoint and use its verdict."""
        event_type = str(parameters.get("eventType") or "beforeRequestHook").strip() or "beforeRequestHook"
        if event_type != "both" and event_type != stage:
            return {
                "id": check_id,
                "verdict": True,
                "explanation": f"Skipped for {stage}.",
            }

        method = str(parameters.get("method") or "POST").strip().upper() or "POST"
        url_template = str(parameters.get("url") or "").strip()
        if not url_template:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": "External validation is missing the target URL.",
            }

        timeout_ms = parameters.get("timeoutMs") or parameters.get("timeout") or 5000
        timeout_seconds = max(float(timeout_ms) / 1000.0, 1.0)
        url = str(self._render_template_string(url_template, request_payload) or "").strip()
        headers_template = parameters.get("headers") if isinstance(parameters.get("headers"), dict) else {}
        headers_rendered = self._render_template_value(headers_template, request_payload)
        headers = {
            str(key): str(value)
            for key, value in headers_rendered.items()
        } if isinstance(headers_rendered, dict) else {}
        body_template = parameters.get("bodyTemplate", request_payload)
        rendered_body = self._render_template_value(body_template, request_payload)

        request_kwargs: dict[str, Any] = {"headers": headers}
        if method in {"GET", "HEAD"}:
            if isinstance(rendered_body, dict):
                request_kwargs["params"] = {
                    str(key): "" if value is None else str(value)
                    for key, value in rendered_body.items()
                }
        else:
            request_kwargs["json"] = rendered_body

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.request(method, url, **request_kwargs)
        except Exception as exc:
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"External validation failed: {exc}",
            }

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        verdict_path = str(parameters.get("verdictPath") or "result.verdict").strip()
        verdict_value = self._extract_path_value(payload, verdict_path)
        verdict = self._coerce_verdict(
            verdict_value,
            default=bool(parameters.get("passIfMissingVerdict", False)),
        )

        message_path = str(parameters.get("messagePath") or "").strip()
        explanation_value = self._extract_path_value(payload, message_path) if message_path else None
        explanation = str(explanation_value).strip() if explanation_value not in (None, "") else "External validation passed." if verdict else "External validation blocked the request."
        transformed_message_path = str(parameters.get("transformedMessagePath") or "").strip()
        blocked_content = self._extract_path_value(payload, transformed_message_path) if transformed_message_path else None
        policies_path = str(parameters.get("policiesPath") or "").strip()
        policies_value = self._extract_path_value(payload, policies_path) if policies_path else None

        if response.status_code >= 400:
            detail = explanation if explanation else response.text
            return {
                "id": check_id,
                "verdict": False,
                "explanation": f"External validation failed: HTTP {response.status_code} — {detail}",
                "blocked_content": str(blocked_content).strip() if isinstance(blocked_content, str) and blocked_content.strip() else None,
            }

        policy_suffix = ""
        if isinstance(policies_value, list) and policies_value:
            policy_suffix = f" Policies: {', '.join(str(item) for item in policies_value)}"

        return {
            "id": check_id,
            "verdict": verdict,
            "explanation": f"{explanation}{policy_suffix}".strip(),
            "blocked_content": str(blocked_content).strip() if isinstance(blocked_content, str) and blocked_content.strip() else None,
            "external_response": payload,
        }

    @staticmethod
    def _merge_local_guardrail_states(
        first: dict[str, Any] | None,
        second: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Merge two local guardrail detail payloads from before/after stages."""
        if not first:
            return second
        if not second:
            return first

        hooks = [*list(first.get("hooks", [])), *list(second.get("hooks", []))]
        failed_checks = [
            *list(first.get("failed_checks", [])),
            *list(second.get("failed_checks", [])),
        ]
        passed_checks = [
            *list(first.get("passed_checks", [])),
            *list(second.get("passed_checks", [])),
        ]
        summaries = [
            str(summary).strip()
            for summary in (first.get("summary"), second.get("summary"))
            if isinstance(summary, str) and summary.strip()
        ]
        return {
            "summary": " | ".join(dict.fromkeys(summaries)) if summaries else "Local guardrails evaluated",
            "hooks": hooks,
            "failed_checks": failed_checks,
            "passed_checks": passed_checks,
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

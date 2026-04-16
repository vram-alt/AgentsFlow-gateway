"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogDescription,
} from "@/components/ui/dialog";
import {
    Shield,
    Plus,
    Pencil,
    Trash2,
    RefreshCw,
    Loader2,
    CloudDownload,
    AlertTriangle,
    Eye,
    Power,
    X,
    Cloud,
    HardDrive,
    Lightbulb,
    Plus as PlusIcon,
} from "lucide-react";
import { api, ApiError, type Policy, type Provider } from "@/lib/api-client";

/** Extract a human-readable message from any caught error. */
function humanError(err: unknown): string {
    if (err instanceof ApiError) return err.message;
    if (err instanceof TypeError) {
        if (err.message.includes("fetch") || err.message.includes("network") || err.message.includes("Failed")) {
            return "Network error — unable to reach the server. Please check your connection and try again.";
        }
        return `Unexpected client error: ${err.message}`;
    }
    if (err instanceof Error) return err.message;
    return "An unexpected error occurred. Please try again later.";
}

function getPrimaryProviderName(providers: { name: string; is_active: boolean }[]): string {
    return providers.find((provider) => provider.name.toLowerCase() === "portkey")?.name
        ?? providers[0]?.name
        ?? "portkey";
}

const DEFAULT_WEBHOOK_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const POLICY_PRESET_PATTERNS = {
    pii: "([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}|\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b)",
    sql: "(DROP TABLE|DELETE FROM|INSERT INTO|UNION SELECT|drop table|delete from|insert into|union select)",
    custom: "(blocked-word|secret-token)",
} as const;

type PolicyTemplateKind = "manual" | "regex-pii" | "regex-sql" | "regex-custom" | "webhook-validate" | "log-only" | "validate-and-log"
    | "external-validation"
    | "sentence-count" | "word-count" | "character-count"
    | "uppercase-check" | "lowercase-check" | "ends-with"
    | "json-schema" | "json-keys" | "valid-urls"
    | "contains-code" | "not-null" | "contains"
    | "model-whitelist" | "model-rules" | "allowed-request-types"
    | "required-metadata-keys" | "required-metadata-kv";
type PolicyTemplateMode = "contains" | "regex";
type PolicyTemplateTarget = "request" | "response" | "both";
type ExternalPolicyEventType = "beforeRequestHook" | "afterResponseHook" | "both";

type PolicyTemplateConfig = {
    mode: PolicyTemplateMode;
    target: PolicyTemplateTarget;
    terms: string;
    pattern: string;
    logLabel: string;
    timeoutMs: string;
    deny: boolean;
    async: boolean;
    invertMatch: boolean;
    externalMethod: string;
    externalUrl: string;
    externalEventType: ExternalPolicyEventType;
    externalHeaders: string;
    externalBodyTemplate: string;
    externalVerdictPath: string;
    externalMessagePath: string;
    externalTransformedMessagePath: string;
    externalPoliciesPath: string;
};

const DEFAULT_TEMPLATE_CONFIG: PolicyTemplateConfig = {
    mode: "contains",
    target: "request",
    terms: "blocked-word, secret-token",
    pattern: POLICY_PRESET_PATTERNS.custom,
    logLabel: "policy-audit",
    timeoutMs: "3000",
    deny: true,
    async: false,
    invertMatch: false,
    externalMethod: "POST",
    externalUrl: "https://ven07172.service-now.com/api/x_juro_appsflow/agent_policy_api/execute",
    externalEventType: "beforeRequestHook",
    externalHeaders: JSON.stringify({ "Content-Type": "application/json" }, null, 2),
    externalBodyTemplate: JSON.stringify({
        request: {
            text: "{{request.latest_text}}",
        },
        eventType: "{{eventType}}",
        metadata: {
            agent_id: "{{metadata.agent_id}}",
            agency_id: "{{metadata.agency_id}}",
        },
    }, null, 2),
    externalVerdictPath: "result.verdict",
    externalMessagePath: "result.metadata.decision",
    externalTransformedMessagePath: "result.transformedData.request.json.messages.0.content",
    externalPoliciesPath: "result.metadata.policies",
};

const TEMPLATE_DEFAULT_NAMES: Record<Exclude<PolicyTemplateKind, "manual">, string> = {
    "regex-pii": "Block PII Leaks",
    "regex-sql": "Block SQL Injection",
    "regex-custom": "Custom Regex Policy",
    "external-validation": "External Validation Policy",
    "webhook-validate": "Custom Webhook Validation",
    "log-only": "Custom Output Logging",
    "validate-and-log": "Validate and Log",
    "sentence-count": "Sentence Count",
    "word-count": "Word Count",
    "character-count": "Character Count",
    "uppercase-check": "Uppercase Check",
    "lowercase-check": "Lowercase Detection",
    "ends-with": "Ends With",
    "json-schema": "JSON Schema",
    "json-keys": "JSON Keys",
    "valid-urls": "Valid URLs",
    "contains-code": "Contains Code",
    "not-null": "Not Null",
    "contains": "Contains",
    "model-whitelist": "Model Whitelist",
    "model-rules": "Model Rules",
    "allowed-request-types": "Allowed Request Types",
    "required-metadata-keys": "Required Metadata Keys",
    "required-metadata-kv": "Required Metadata Key-Value Pairs",
};

type TemplateCategory = "popular" | "content" | "structured" | "request";

const TEMPLATE_CATEGORY_OPTIONS: Array<{
    key: TemplateCategory;
    label: string;
    description: string;
    kinds: Exclude<PolicyTemplateKind, "manual">[];
}> = [
    {
        key: "popular",
        label: "Popular",
        description: "Fast starters for the most common policies",
        kinds: ["regex-pii", "regex-sql", "regex-custom", "external-validation", "webhook-validate", "validate-and-log", "log-only"],
    },
    {
        key: "content",
        label: "Content",
        description: "Text and format checks for prompts and responses",
        kinds: ["sentence-count", "word-count", "character-count", "uppercase-check", "lowercase-check", "contains", "ends-with", "contains-code"],
    },
    {
        key: "structured",
        label: "Structured",
        description: "JSON, null, and URL validation helpers",
        kinds: ["json-schema", "json-keys", "valid-urls", "not-null"],
    },
    {
        key: "request",
        label: "Request",
        description: "Model, request type, and metadata rules",
        kinds: ["model-whitelist", "model-rules", "allowed-request-types", "required-metadata-keys", "required-metadata-kv"],
    },
];

function parseJsonInput<T>(value: string, fallback: T): T {
    try {
        return JSON.parse(value) as T;
    } catch {
        return fallback;
    }
}

function buildPolicyTemplate(
    kind: Exclude<PolicyTemplateKind, "manual">,
    config: PolicyTemplateConfig,
): string {
    const secretPlaceholder = "REPLACE_WITH_YOUR_WEBHOOK_SECRET";
    const baseUrl = DEFAULT_WEBHOOK_BASE_URL.replace(/\/$/, "");

    if (kind === "external-validation") {
        const renderedHeaders = parseJsonInput<Record<string, string>>(config.externalHeaders, {
            "Content-Type": "application/json",
        });
        const renderedBodyTemplate = parseJsonInput<Record<string, unknown>>(config.externalBodyTemplate, {
            request: { text: "{{request.latest_text}}" },
            eventType: "{{eventType}}",
            metadata: { agent_id: "{{metadata.agent_id}}" },
        });

        return JSON.stringify(
            {
                checks: [
                    {
                        id: "external.validation",
                        parameters: {
                            method: config.externalMethod || "POST",
                            url: config.externalUrl,
                            eventType: config.externalEventType,
                            headers: renderedHeaders,
                            timeoutMs: Number.parseInt(config.timeoutMs, 10) || 5000,
                            bodyTemplate: renderedBodyTemplate,
                            verdictPath: config.externalVerdictPath || "result.verdict",
                            messagePath: config.externalMessagePath || "result.metadata.decision",
                            transformedMessagePath: config.externalTransformedMessagePath || "result.transformedData.request.json.messages.0.content",
                            policiesPath: config.externalPoliciesPath || "result.metadata.policies",
                        },
                    },
                ],
                actions: {
                    onFail: config.deny ? "block" : "allow",
                    onPass: "allow",
                },
                deny: config.deny,
            },
            null,
            2,
        );
    }

    if (kind === "regex-pii" || kind === "regex-sql" || kind === "regex-custom") {
        const regexRule = kind === "regex-pii"
            ? POLICY_PRESET_PATTERNS.pii
            : kind === "regex-sql"
                ? POLICY_PRESET_PATTERNS.sql
                : (config.pattern || POLICY_PRESET_PATTERNS.custom);

        const regexParameters: Record<string, unknown> = {
            rule: regexRule,
        };
        if (kind === "regex-pii" || config.invertMatch) {
            regexParameters.not = true;
        }

        return JSON.stringify(
            {
                checks: [
                    {
                        id: "default.regexMatch",
                        parameters: regexParameters,
                    },
                ],
                actions: {
                    onFail: "block",
                    onPass: "allow",
                },
                deny: true,
            },
            null,
            2,
        );
    }

    // ── Deterministic BASIC check templates ──────────────────────
    if (kind === "sentence-count") {
        return JSON.stringify({
            checks: [{ id: "default.sentenceCount", parameters: { minSentences: 1, maxSentences: 10 } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "word-count") {
        return JSON.stringify({
            checks: [{ id: "default.wordCount", parameters: { minWords: 1, maxWords: 500 } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "character-count") {
        return JSON.stringify({
            checks: [{ id: "default.characterCount", parameters: { minCharacters: 1, maxCharacters: 5000 } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "uppercase-check") {
        return JSON.stringify({
            checks: [{ id: "default.uppercaseCheck", parameters: { not: config.invertMatch } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "lowercase-check") {
        return JSON.stringify({
            checks: [{ id: "default.lowercaseDetection", parameters: { format: "lowercase" } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "ends-with") {
        return JSON.stringify({
            checks: [{ id: "default.endsWith", parameters: { Suffix: config.pattern || "." } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "json-schema") {
        return JSON.stringify({
            checks: [{ id: "default.jsonSchema", parameters: { schema: { type: "object", required: ["key"], properties: { key: { type: "string" } } } } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "json-keys") {
        return JSON.stringify({
            checks: [{ id: "default.jsonKeys", parameters: { keys: ["key1", "key2"], operator: "all" } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "valid-urls") {
        return JSON.stringify({
            checks: [{ id: "default.validUrls", parameters: { onlyDNS: false } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "contains-code") {
        return JSON.stringify({
            checks: [{ id: "default.containsCode", parameters: { format: config.pattern || "sql" } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "not-null") {
        return JSON.stringify({
            checks: [{ id: "default.notNull", parameters: { not: false } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "contains") {
        return JSON.stringify({
            checks: [{ id: "default.contains", parameters: { words: (config.terms || "blocked-word, secret-token").split(",").map((w: string) => w.trim()), operator: "any" } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "model-whitelist") {
        return JSON.stringify({
            checks: [{ id: "default.modelWhitelist", parameters: { Models: ["gemini-2.5-flash", "gpt-4o"], Inverse: false } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "model-rules") {
        return JSON.stringify({
            checks: [{ id: "default.modelRules", parameters: { rules: { tier: ["gemini-2.5-flash", "gpt-4o-mini"] }, not: false } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "allowed-request-types") {
        return JSON.stringify({
            checks: [{ id: "default.allowedRequestTypes", parameters: { allowedTypes: ["chat", "completions"], blockedTypes: [] } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "required-metadata-keys") {
        return JSON.stringify({
            checks: [{ id: "default.requiredMetadataKeys", parameters: { metadataKeys: ["user_id", "session_id"], operator: "all" } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }
    if (kind === "required-metadata-kv") {
        return JSON.stringify({
            checks: [{ id: "default.requiredMetadataKeyValuePairs", parameters: { metadataPairs: { environment: "production" }, operator: "all" } }],
            actions: { onFail: config.deny ? "block" : "allow", onPass: "allow" },
            deny: config.deny,
        }, null, 2);
    }

    const validateParams = new URLSearchParams({
        mode: config.mode,
        target: config.target,
    });
    if (config.mode === "regex") {
        validateParams.set("pattern", config.pattern || POLICY_PRESET_PATTERNS.custom);
    } else {
        validateParams.set("terms", config.terms || DEFAULT_TEMPLATE_CONFIG.terms);
    }

    const timeoutMs = Number.parseInt(config.timeoutMs, 10);
    const normalizedTimeout = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 3000;

    const actions = {
        onFail: config.deny ? "block" : "allow",
        onPass: "allow",
        execution: config.async ? "async" : "sync",
    };

    const webhookCheck = {
        id: "webhook",
        parameters: {
            webhookURL: `${baseUrl}/api/webhook/custom/validate?${validateParams.toString()}`,
            headers: {
                "X-Webhook-Secret": secretPlaceholder,
            },
            timeoutMs: normalizedTimeout,
        },
    };

    const logCheck = {
        id: "log",
        parameters: {
            logURL: `${baseUrl}/api/webhook/custom/log?label=${encodeURIComponent(config.logLabel || "policy-audit")}`,
            headers: {
                "X-Webhook-Secret": secretPlaceholder,
            },
        },
    };

    if (kind === "log-only") {
        return JSON.stringify(
            {
                checks: [logCheck],
                actions: {
                    onFail: "allow",
                    onPass: "allow",
                    execution: config.async ? "async" : "sync",
                },
                deny: false,
                async: true,
            },
            null,
            2,
        );
    }

    if (kind === "validate-and-log") {
        return JSON.stringify(
            {
                checks: [webhookCheck, logCheck],
                actions,
                deny: config.deny,
                async: config.async,
            },
            null,
            2,
        );
    }

    return JSON.stringify(
        {
            checks: [webhookCheck],
            actions,
            deny: config.deny,
            async: config.async,
        },
        null,
        2,
    );
}

function validateCustomPolicyBody(body: Record<string, unknown>): string | null {
    const checks = body.checks;
    if (checks === undefined) return null;
    if (!Array.isArray(checks)) return "The 'checks' field must be an array.";

    for (let index = 0; index < checks.length; index += 1) {
        const check = checks[index];
        if (!check || typeof check !== "object") {
            return `Check #${index + 1} must be a JSON object.`;
        }

        const checkRecord = check as Record<string, unknown>;
        const checkId = String(checkRecord.id || "").toLowerCase();
        const parameters = (checkRecord.parameters ?? {}) as Record<string, unknown>;
        if (typeof parameters !== "object" || Array.isArray(parameters)) {
            return `Check #${index + 1} parameters must be a JSON object.`;
        }

        const isValidHttpUrl = (value: unknown) => {
            if (typeof value !== "string" || value.trim().length === 0) return false;
            try {
                const parsed = new URL(value);
                return parsed.protocol === "http:" || parsed.protocol === "https:";
            } catch {
                return false;
            }
        };

        if (checkId.includes("webhook") && !isValidHttpUrl(parameters.webhookURL)) {
            return `Check #${index + 1} must include a valid 'webhookURL'.`;
        }

        if ((checkId === "log" || checkId.endsWith(".log")) && !isValidHttpUrl(parameters.logURL)) {
            return `Check #${index + 1} must include a valid 'logURL'.`;
        }

        if ((checkId === "external.validation" || checkId === "external.validate") && !isValidHttpUrl(parameters.url)) {
            return `Check #${index + 1} must include a valid 'url'.`;
        }

        if (checkId === "external.validation" || checkId === "external.validate") {
            if (typeof parameters.method !== "string" || parameters.method.trim().length === 0) {
                return `Check #${index + 1} must include an HTTP 'method'.`;
            }
            if (typeof parameters.verdictPath !== "string" || parameters.verdictPath.trim().length === 0) {
                return `Check #${index + 1} must include a 'verdictPath'.`;
            }
            if (parameters.bodyTemplate !== undefined) {
                try {
                    JSON.stringify(parameters.bodyTemplate);
                } catch {
                    return `Check #${index + 1} bodyTemplate must be valid JSON.`;
                }
            }
        }

        if (parameters.headers !== undefined && (typeof parameters.headers !== "object" || Array.isArray(parameters.headers))) {
            return `Check #${index + 1} headers must be a JSON object.`;
        }
    }

    return null;
}

export default function PoliciesPage() {
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [providers, setProviders] = useState<{ name: string, is_active: boolean }[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingPolicy, setEditingPolicy] = useState<Policy | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
    const [syncLoading, setSyncLoading] = useState(false);
    const [formData, setFormData] = useState({
        name: "",
        body: "{}",
        provider_name: "portkey",
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [pageError, setPageError] = useState<string | null>(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
    const [templateKind, setTemplateKind] = useState<PolicyTemplateKind>("manual");
    const [templateCategory, setTemplateCategory] = useState<TemplateCategory>("popular");
    const [templateConfig, setTemplateConfig] = useState<PolicyTemplateConfig>(DEFAULT_TEMPLATE_CONFIG);

    // Persist the Local/Cloud tab choice in localStorage so it survives navigation
    const [isCloudMode, setIsCloudMode] = useState<boolean>(() => {
        if (typeof window !== "undefined") {
            const saved = localStorage.getItem("policies_cloud_mode");
            if (saved !== null) return saved === "true";
        }
        return true; // default to cloud
    });

    const setCloudMode = (value: boolean) => {
        setIsCloudMode(value);
        if (typeof window !== "undefined") {
            localStorage.setItem("policies_cloud_mode", String(value));
        }
    };

    const fetchPolicies = useCallback(async () => {
        setLoading(true);
        setPageError(null);
        try {
            const data = await api.listPolicies();
            setPolicies(Array.isArray(data) ? data : []);

            const providersResponse = await api.listProviders();
            const providersData = Array.isArray(providersResponse) ? providersResponse : [];
            setProviders(providersData);
            setFormData((prev) => ({ ...prev, provider_name: getPrimaryProviderName(providersData) }));

            // Auto-detect cloud mode ONLY if user has never manually chosen a tab
            if (typeof window !== "undefined" && localStorage.getItem("policies_cloud_mode") === null) {
                const activeProviders = (Array.isArray(providersData) ? providersData : []).filter((p: Provider) => p.is_active);
                const hasCloudProvider = activeProviders.some((p: Provider) =>
                    p.base_url?.includes("portkey.ai") || p.api_key?.includes("::")
                );
                setCloudMode(hasCloudProvider);
            }
        } catch (err: unknown) {
            setPolicies([]);
            setPageError(humanError(err));
        } finally {
            setLoading(false);
        }
    }, []);

    const handleRefresh = () => {
        fetchPolicies();
    };

    useEffect(() => {
        fetchPolicies();
    }, [fetchPolicies]);

    const openCreate = () => {
        setEditingPolicy(null);
        setTemplateKind("manual");
        setTemplateCategory("popular");
        setTemplateConfig(DEFAULT_TEMPLATE_CONFIG);
        setFormData({ name: "", body: '{\n  "checks": [\n    {\n      "id": "default.regexMatch",\n      "parameters": {\n        "rule": "block-word",\n        "pattern": "badword"\n      }\n    }\n  ],\n  "actions": {\n    "onFail": "block",\n    "onPass": "allow"\n  }\n}', provider_name: getPrimaryProviderName(providers) });
        setError(null);
        setDialogOpen(true);
    };

    const applyTemplate = (kind: Exclude<PolicyTemplateKind, "manual">) => {
        const nextConfig: PolicyTemplateConfig = kind === "regex-pii"
            ? { ...templateConfig, pattern: POLICY_PRESET_PATTERNS.pii, invertMatch: true, deny: true, async: false, target: "request" }
            : kind === "regex-sql"
                ? { ...templateConfig, pattern: POLICY_PRESET_PATTERNS.sql, invertMatch: false, deny: true, async: false, target: "request" }
                : kind === "regex-custom"
                    ? { ...templateConfig, pattern: POLICY_PRESET_PATTERNS.custom, invertMatch: false, deny: true, async: false, target: "request" }
                    : kind === "external-validation"
                        ? {
                            ...templateConfig,
                            externalMethod: "POST",
                            externalUrl: DEFAULT_TEMPLATE_CONFIG.externalUrl,
                            externalEventType: "beforeRequestHook",
                            externalHeaders: DEFAULT_TEMPLATE_CONFIG.externalHeaders,
                            externalBodyTemplate: DEFAULT_TEMPLATE_CONFIG.externalBodyTemplate,
                            externalVerdictPath: DEFAULT_TEMPLATE_CONFIG.externalVerdictPath,
                            externalMessagePath: DEFAULT_TEMPLATE_CONFIG.externalMessagePath,
                            externalTransformedMessagePath: DEFAULT_TEMPLATE_CONFIG.externalTransformedMessagePath,
                            externalPoliciesPath: DEFAULT_TEMPLATE_CONFIG.externalPoliciesPath,
                            timeoutMs: "5000",
                            deny: true,
                            async: false,
                        }
                    : kind === "log-only"
                        ? { ...templateConfig, target: "response", deny: false, async: true }
                        : kind === "contains"
                            ? { ...templateConfig, terms: "blocked-word, secret-token", deny: true, async: false, target: "request" }
                            : kind === "ends-with"
                                ? { ...templateConfig, pattern: ".", deny: true, async: false, target: "request" }
                                : kind === "contains-code"
                                    ? { ...templateConfig, pattern: "sql", deny: true, async: false, target: "request" }
                                    : { ...templateConfig, deny: true, async: false };

        setTemplateKind(kind);
        setTemplateConfig(nextConfig);
        setFormData((prev) => ({
            ...prev,
            name: prev.name || TEMPLATE_DEFAULT_NAMES[kind],
            body: buildPolicyTemplate(kind, nextConfig),
        }));
    };

    const patchTemplateConfig = (patch: Partial<PolicyTemplateConfig>) => {
        setTemplateConfig((prev) => {
            const next = { ...prev, ...patch };
            if (templateKind !== "manual") {
                setFormData((current) => ({
                    ...current,
                    body: buildPolicyTemplate(templateKind, next),
                }));
            }
            return next;
        });
    };

    const openEdit = (policy: Policy) => {
        setTemplateKind("manual");
        setTemplateCategory("popular");
        setTemplateConfig(DEFAULT_TEMPLATE_CONFIG);
        setEditingPolicy(policy);
        setFormData({
            name: policy.name,
            body: JSON.stringify(policy.body, null, 2),
            provider_name: policy.provider_name,
        });
        setError(null);
        setDialogOpen(true);
    };

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            let parsedBody: Record<string, unknown>;
            try {
                parsedBody = JSON.parse(formData.body);
            } catch {
                setError("Invalid JSON in policy body");
                setSaving(false);
                return;
            }

            const validationMessage = validateCustomPolicyBody(parsedBody);
            if (validationMessage) {
                setError(validationMessage);
                setSaving(false);
                return;
            }

            if (editingPolicy) {
                await api.updatePolicy(editingPolicy.id, {
                    name: formData.name || null,
                    body: parsedBody,
                });
            } else {
                await api.createPolicy({
                    name: formData.name,
                    body: parsedBody,
                    provider_name: formData.provider_name,
                });
            }
            setDialogOpen(false);
            fetchPolicies();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to save");
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id: number) => {
        setDeleteLoading(true);
        setPageError(null);
        try {
            await api.deletePolicy(id);
            setDeleteConfirm(null);
            // Remove from local state immediately — no tab switch
            setPolicies((prev) => prev.filter((p) => p.id !== id));
        } catch (err: unknown) {
            setDeleteConfirm(null);
            setPageError(`Failed to delete policy: ${humanError(err)}`);
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleToggle = async (id: number) => {
        setPageError(null);
        try {
            const updated = await api.togglePolicy(id);
            // Update local state in-place — policy stays in list, just greyed out
            setPolicies((prev) =>
                prev.map((p) => (p.id === id ? { ...p, is_active: updated.is_active } : p))
            );
        } catch (err: unknown) {
            setPageError(`Failed to toggle policy: ${humanError(err)}`);
        }
    };

    // Filter policies by tab: Local = no remote_id, Cloud = has remote_id
    const displayedPolicies = isCloudMode
        ? policies.filter((p) => !!p.remote_id)
        : policies.filter((p) => !p.remote_id);

    const activeTemplateCategory = TEMPLATE_CATEGORY_OPTIONS.find((category) => category.key === templateCategory)
        ?? TEMPLATE_CATEGORY_OPTIONS[0];

    const handleSync = async () => {
        setSyncLoading(true);
        setPageError(null);
        try {
            await api.syncPolicies("portkey");
            fetchPolicies();
        } catch (err: unknown) {
            setPageError(`Sync failed: ${humanError(err)}`);
        } finally {
            setSyncLoading(false);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Policies</h1>
                    <p className="text-muted-foreground">Manage guardrail and security policies. Policies are synced with your Portkey cloud account.</p>
                </div>
                <div className="flex gap-2">
                    {isCloudMode && (
                        <Button variant="outline" size="sm" onClick={handleSync} disabled={syncLoading}>
                            {syncLoading ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <CloudDownload className="w-4 h-4 mr-2" />
                            )}
                            Sync from Cloud
                        </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={openCreate}>
                        <Plus className="w-4 h-4 mr-2" />
                        Add Policy
                    </Button>
                </div>
            </div>

            {/* Page Error Banner */}
            {pageError && (
                <div className="flex items-center gap-3 p-4 rounded-lg border border-destructive/50 bg-destructive/10 text-destructive">
                    <AlertTriangle className="w-5 h-5 shrink-0" />
                    <p className="text-sm font-medium">{pageError}</p>
                    <button
                        onClick={() => setPageError(null)}
                        className="ml-auto p-1 rounded hover:bg-destructive/20 cursor-pointer"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}

            {/* Mode Toggle */}
            <div className="flex items-center gap-4">
                <div className="relative flex items-center w-56 rounded-lg bg-secondary/60 p-0.5 text-xs">
                    {/* Sliding highlight */}
                    <div
                        className="absolute top-0.5 bottom-0.5 w-[calc(50%-2px)] rounded-md bg-primary shadow-sm transition-transform duration-200 ease-in-out"
                        style={{ transform: isCloudMode ? "translateX(calc(100% + 4px))" : "translateX(0)" }}
                    />
                    <button
                        onClick={() => setCloudMode(false)}
                        className={`relative z-10 flex items-center justify-center gap-1.5 w-1/2 py-1.5 rounded-md font-medium transition-colors duration-200 cursor-pointer ${!isCloudMode
                            ? "text-primary-foreground"
                            : "text-muted-foreground hover:text-foreground"
                            }`}
                    >
                        <HardDrive className="w-3.5 h-3.5" />
                        Local
                    </button>
                    <button
                        onClick={() => setCloudMode(true)}
                        className={`relative z-10 flex items-center justify-center gap-1.5 w-1/2 py-1.5 rounded-md font-medium transition-colors duration-200 cursor-pointer ${isCloudMode
                            ? "text-primary-foreground"
                            : "text-muted-foreground hover:text-foreground"
                            }`}
                    >
                        <Cloud className="w-3.5 h-3.5" />
                        Cloud
                    </button>
                </div>
                <span className="text-xs text-muted-foreground">
                    {isCloudMode ? "Policies synced with Portkey Cloud" : "Policies stored locally only"}
                </span>
            </div>

            {/* Policies Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border">
                                    <th className="text-left p-4 text-muted-foreground font-medium">Name</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Provider</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Status</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Rules</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Updated</th>
                                    <th className="text-right p-4 text-muted-foreground font-medium">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading && (
                                    <tr>
                                        <td colSpan={6} className="p-8 text-center">
                                            <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
                                        </td>
                                    </tr>
                                )}
                                {!loading && displayedPolicies.length === 0 && (
                                    <tr>
                                        <td colSpan={6} className="p-8 text-center text-muted-foreground">
                                            <Shield className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                            <p>No policies configured</p>
                                            <p className="text-xs mt-1 max-w-sm mx-auto">Policies (guardrails) filter and validate AI requests and responses. Create one below or sync existing guardrails from your Portkey cloud account.</p>
                                            <Button size="sm" className="mt-3" onClick={openCreate}>
                                                <Plus className="w-4 h-4 mr-2" />
                                                Create policy
                                            </Button>
                                        </td>
                                    </tr>
                                )}
                                {!loading &&
                                    displayedPolicies.map((policy) => (
                                        <tr
                                            key={policy.id}
                                            className={`border-b border-border/50 hover:bg-secondary/30 transition-colors ${!policy.is_active ? "opacity-60" : ""}`}
                                        >
                                            <td className="p-4">
                                                <div className="flex items-center gap-3">
                                                    <div className={`p-1.5 rounded-lg ${policy.is_active ? "bg-accent/10" : "bg-muted"}`}>
                                                        <Shield className={`w-4 h-4 ${policy.is_active ? "text-accent" : "text-muted-foreground"}`} />
                                                    </div>
                                                    <span className={`font-medium ${!policy.is_active ? "text-muted-foreground" : ""}`}>
                                                        {policy.name}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="p-4">
                                                <div className="flex items-center gap-1.5">
                                                    <Badge variant="outline" className="text-xs">
                                                        {policy.provider_name}
                                                    </Badge>
                                                    {policy.remote_id ? (
                                                        <Badge variant="outline" className="text-xs text-blue-500 border-blue-500/30">
                                                            <Cloud className="w-3 h-3 mr-1" />
                                                            Cloud
                                                        </Badge>
                                                    ) : (
                                                        <Badge variant="outline" className="text-xs text-orange-500 border-orange-500/30">
                                                            <HardDrive className="w-3 h-3 mr-1" />
                                                            Local
                                                        </Badge>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="p-4">
                                                <Badge variant={policy.is_active ? "success" : "secondary"}>
                                                    {policy.is_active ? "Active" : "Inactive"}
                                                </Badge>
                                            </td>
                                            <td className="p-4 text-muted-foreground">
                                                {Object.keys(policy.body).length} rules
                                            </td>
                                            <td className="p-4 text-xs text-muted-foreground">
                                                {new Date(policy.updated_at).toLocaleString()}
                                            </td>
                                            <td className="p-4 text-right">
                                                <div className="flex items-center justify-end gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className={`h-8 w-8 ${policy.is_active
                                                            ? "text-green-500 hover:text-red-500"
                                                            : "text-muted-foreground hover:text-green-500"
                                                            }`}
                                                        onClick={() => handleToggle(policy.id)}
                                                        title={policy.is_active ? "Deactivate policy" : "Activate policy"}
                                                    >
                                                        <Power className="w-3.5 h-3.5" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => setSelectedPolicy(policy)}
                                                        title="View details"
                                                    >
                                                        <Eye className="w-3.5 h-3.5" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => openEdit(policy)}
                                                        title="Edit policy"
                                                    >
                                                        <Pencil className="w-3.5 h-3.5" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-destructive"
                                                        onClick={() => setDeleteConfirm(policy.id)}
                                                        title="Delete policy"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </Button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Create/Edit Dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="flex max-h-[88vh] w-[96vw] max-w-5xl flex-col overflow-hidden">
                    <DialogHeader className="shrink-0 border-b pb-3">
                        <DialogTitle>
                            {editingPolicy ? "Edit Policy" : "Create Policy"}
                        </DialogTitle>
                        <DialogDescription>
                            {editingPolicy
                                ? "Update the policy configuration"
                                : "Define a new guardrail policy"}
                        </DialogDescription>
                        <p className="text-xs text-muted-foreground">
                            <strong>Selected builder:</strong>{" "}
                            {templateKind === "manual"
                                ? "Editable JSON"
                                : TEMPLATE_DEFAULT_NAMES[templateKind]}
                        </p>
                    </DialogHeader>
                    <div className="flex h-full flex-1 min-h-0 flex-col overflow-hidden py-3">
                        {error && (
                            <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
                                <AlertTriangle className="w-4 h-4" />
                                {error}
                            </div>
                        )}
                        <div className={`grid shrink-0 gap-3 ${editingPolicy ? "md:grid-cols-1" : "md:grid-cols-[minmax(0,1fr)_220px]"}`}>
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Name</label>
                                <Input
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="e.g. content-filter"
                                />
                            </div>
                            {!editingPolicy && (
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Provider</label>
                                    <Select
                                        value={formData.provider_name}
                                        onChange={(e) =>
                                            setFormData({ ...formData, provider_name: e.target.value })
                                        }
                                    >
                                        <option value={getPrimaryProviderName(providers)}>
                                            Portkey
                                        </option>
                                    </Select>
                                </div>
                            )}
                        </div>
                        <div className="mt-3 flex h-full min-h-0 flex-1 flex-col space-y-2 overflow-hidden">
                            <div className="flex items-center justify-between gap-2">
                                <label className="text-sm font-medium">Policy Body (JSON)</label>
                                <Badge variant="outline" className="text-[11px]">
                                    {templateKind === "manual" ? "Manual JSON" : TEMPLATE_DEFAULT_NAMES[templateKind]}
                                </Badge>
                            </div>
                            <div className="grid h-full min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[280px_minmax(0,1fr)]">
                                <div className="min-h-0 overflow-y-auto rounded-xl border border-border/60 bg-secondary/20 p-3">
                                    <div className="space-y-3">
                                    <div className="space-y-1">
                                        <p className="text-sm font-medium">Starter templates</p>
                                        <p className="text-[11px] text-muted-foreground">
                                            Pick a category, choose a starter, then fine-tune the JSON on the right.
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {TEMPLATE_CATEGORY_OPTIONS.map((category) => (
                                            <button
                                                key={category.key}
                                                type="button"
                                                onClick={() => setTemplateCategory(category.key)}
                                                className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors cursor-pointer ${templateCategory === category.key
                                                    ? "border-primary bg-primary text-primary-foreground"
                                                    : "border-border bg-background text-muted-foreground hover:text-foreground"
                                                    }`}
                                            >
                                                {category.label}
                                            </button>
                                        ))}
                                    </div>
                                    <div className="rounded-lg border border-border/50 bg-background/80 p-2.5">
                                        <p className="text-[11px] font-medium text-foreground">
                                            {activeTemplateCategory.label} templates
                                        </p>
                                        <p className="mb-3 mt-1 text-[11px] text-muted-foreground">
                                            {activeTemplateCategory.description}
                                        </p>
                                        <div className="grid gap-2 sm:grid-cols-2 xl:max-h-64 xl:grid-cols-1 xl:overflow-y-auto xl:pr-1">
                                            {activeTemplateCategory.kinds.map((kind) => (
                                                <Button
                                                    key={kind}
                                                    type="button"
                                                    variant={templateKind === kind ? "default" : "outline"}
                                                    size="sm"
                                                    className="h-auto justify-start px-3 py-2 text-left whitespace-normal leading-snug"
                                                    onClick={() => applyTemplate(kind)}
                                                >
                                                    <PlusIcon className="mr-1.5 h-3.5 w-3.5 shrink-0" />
                                                    <span>{TEMPLATE_DEFAULT_NAMES[kind]}</span>
                                                </Button>
                                            ))}
                                        </div>
                                    </div>
                                    </div>
                                </div>
                                <div className="min-h-0 min-w-0 overflow-y-auto pr-1">
                                    <div className="space-y-3">
                                    {templateKind !== "manual" && (
                                        <div className="space-y-3 rounded-lg border border-border/60 bg-secondary/30 p-3">
                                            {(templateKind === "regex-pii" || templateKind === "regex-sql" || templateKind === "regex-custom") ? (
                                                <div className="space-y-3">
                                                    <div className="space-y-1">
                                                        <label className="text-xs font-medium">Regex rule</label>
                                                        <Input
                                                            value={templateConfig.pattern}
                                                            onChange={(e) => patchTemplateConfig({ pattern: e.target.value })}
                                                            placeholder="(DROP TABLE|DELETE FROM|INSERT INTO|UNION SELECT)"
                                                        />
                                                    </div>
                                                    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                                                        <label className="flex items-center gap-2">
                                                            <input
                                                                type="checkbox"
                                                                checked={templateConfig.invertMatch}
                                                                onChange={(e) => patchTemplateConfig({ invertMatch: e.target.checked })}
                                                                disabled={templateKind === "regex-pii"}
                                                            />
                                                            Use <code className="bg-secondary px-1 rounded">not: true</code>
                                                        </label>
                                                    </div>
                                                    <p className="text-[11px] text-muted-foreground">
                                                        Good for quick policies like <strong>Block PII Leaks</strong> and <strong>Block SQL Injection</strong>. The builder keeps the same JSON structure as your existing saved policies.
                                                    </p>
                                                </div>
                                            ) : templateKind === "external-validation" ? (
                                                <div className="space-y-3">
                                                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                                        <div className="space-y-1 sm:col-span-2">
                                                            <label className="text-xs font-medium">External endpoint URL</label>
                                                            <Input
                                                                value={templateConfig.externalUrl}
                                                                onChange={(e) => patchTemplateConfig({ externalUrl: e.target.value })}
                                                                placeholder="https://ven07172.service-now.com/api/x_juro_appsflow/agent_policy_api/execute"
                                                            />
                                                        </div>
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">HTTP method</label>
                                                            <Select
                                                                value={templateConfig.externalMethod}
                                                                onChange={(e) => patchTemplateConfig({ externalMethod: e.target.value })}
                                                            >
                                                                <option value="POST">POST</option>
                                                                <option value="PUT">PUT</option>
                                                                <option value="PATCH">PATCH</option>
                                                                <option value="GET">GET</option>
                                                            </Select>
                                                        </div>
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Run when</label>
                                                            <Select
                                                                value={templateConfig.externalEventType}
                                                                onChange={(e) => patchTemplateConfig({ externalEventType: e.target.value as ExternalPolicyEventType })}
                                                            >
                                                                <option value="beforeRequestHook">Before request</option>
                                                                <option value="afterResponseHook">After response</option>
                                                                <option value="both">Before + after</option>
                                                            </Select>
                                                        </div>
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Verdict path</label>
                                                            <Input
                                                                value={templateConfig.externalVerdictPath}
                                                                onChange={(e) => patchTemplateConfig({ externalVerdictPath: e.target.value })}
                                                                placeholder="result.verdict"
                                                            />
                                                        </div>
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Message path</label>
                                                            <Input
                                                                value={templateConfig.externalMessagePath}
                                                                onChange={(e) => patchTemplateConfig({ externalMessagePath: e.target.value })}
                                                                placeholder="result.metadata.decision"
                                                            />
                                                        </div>
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Transformed message path</label>
                                                            <Input
                                                                value={templateConfig.externalTransformedMessagePath}
                                                                onChange={(e) => patchTemplateConfig({ externalTransformedMessagePath: e.target.value })}
                                                                placeholder="result.transformedData.request.json.messages.0.content"
                                                            />
                                                        </div>
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Policies path</label>
                                                            <Input
                                                                value={templateConfig.externalPoliciesPath}
                                                                onChange={(e) => patchTemplateConfig({ externalPoliciesPath: e.target.value })}
                                                                placeholder="result.metadata.policies"
                                                            />
                                                        </div>
                                                        <div className="space-y-1 sm:col-span-2">
                                                            <label className="text-xs font-medium">Headers JSON</label>
                                                            <Textarea
                                                                value={templateConfig.externalHeaders}
                                                                onChange={(e) => patchTemplateConfig({ externalHeaders: e.target.value })}
                                                                className="min-h-28 font-mono text-xs"
                                                            />
                                                        </div>
                                                        <div className="space-y-1 sm:col-span-2">
                                                            <label className="text-xs font-medium">Body template JSON</label>
                                                            <Textarea
                                                                value={templateConfig.externalBodyTemplate}
                                                                onChange={(e) => patchTemplateConfig({ externalBodyTemplate: e.target.value })}
                                                                className="min-h-40 font-mono text-xs"
                                                            />
                                                        </div>
                                                    </div>
                                                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Timeout (ms)</label>
                                                            <Input
                                                                value={templateConfig.timeoutMs}
                                                                onChange={(e) => patchTemplateConfig({ timeoutMs: e.target.value })}
                                                                placeholder="5000"
                                                            />
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                                                        <label className="flex items-center gap-2">
                                                            <input
                                                                type="checkbox"
                                                                checked={templateConfig.deny}
                                                                onChange={(e) => patchTemplateConfig({ deny: e.target.checked })}
                                                            />
                                                            Block on failed verdict
                                                        </label>
                                                    </div>
                                                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                                                        This builder creates a <strong>local-only</strong> policy. Use placeholders like <code className="bg-secondary px-1 rounded">{"{{request.latest_text}}"}</code>, <code className="bg-secondary px-1 rounded">{"{{metadata.agent_id}}"}</code>, <code className="bg-secondary px-1 rounded">{"{{metadata.agency_id}}"}</code>, <code className="bg-secondary px-1 rounded">{"{{eventType}}"}</code>, and <code className="bg-secondary px-1 rounded">{"{{response.text}}"}</code> inside the body template.
                                                    </p>
                                                </div>
                                            ) : (templateKind === "sentence-count" || templateKind === "word-count" || templateKind === "character-count"
                                                || templateKind === "uppercase-check" || templateKind === "lowercase-check" || templateKind === "ends-with"
                                                || templateKind === "json-schema" || templateKind === "json-keys" || templateKind === "valid-urls"
                                                || templateKind === "contains-code" || templateKind === "not-null" || templateKind === "contains"
                                                || templateKind === "model-whitelist" || templateKind === "model-rules" || templateKind === "allowed-request-types"
                                                || templateKind === "required-metadata-keys" || templateKind === "required-metadata-kv") ? (
                                                <div className="space-y-3">
                                                    <p className="text-[11px] text-muted-foreground">
                                                        <strong>{TEMPLATE_DEFAULT_NAMES[templateKind]}</strong> — Portkey BASIC deterministic guardrail. Edit the JSON below to customize parameters. The policy will be enforced locally when used in Local mode, or on Portkey Cloud in Cloud mode.
                                                    </p>
                                                    {(templateKind === "contains" || templateKind === "ends-with" || templateKind === "contains-code") && (
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">
                                                                {templateKind === "contains" ? "Words (comma separated)" : templateKind === "contains-code" ? "Code format" : "Suffix"}
                                                            </label>
                                                            <Input
                                                                value={templateKind === "contains" ? templateConfig.terms : templateConfig.pattern}
                                                                onChange={(e) => patchTemplateConfig(
                                                                    templateKind === "contains"
                                                                        ? { terms: e.target.value }
                                                                        : { pattern: e.target.value }
                                                                )}
                                                                placeholder={templateKind === "contains" ? "blocked-word, secret-token" : templateKind === "contains-code" ? "sql, python, typescript, javascript" : "."}
                                                            />
                                                        </div>
                                                    )}
                                                    {(templateKind === "uppercase-check") && (
                                                        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                                                            <label className="flex items-center gap-2">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={templateConfig.invertMatch}
                                                                    onChange={(e) => patchTemplateConfig({ invertMatch: e.target.checked })}
                                                                />
                                                                Use <code className="bg-secondary px-1 rounded">not: true</code> (invert check)
                                                            </label>
                                                        </div>
                                                    )}
                                                    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                                                        <label className="flex items-center gap-2">
                                                            <input
                                                                type="checkbox"
                                                                checked={templateConfig.deny}
                                                                onChange={(e) => patchTemplateConfig({ deny: e.target.checked })}
                                                            />
                                                            Block on fail
                                                        </label>
                                                    </div>
                                                </div>
                                            ) : (
                                                <>
                                                    {templateKind !== "log-only" && (
                                                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                                            <div className="space-y-1">
                                                                <label className="text-xs font-medium">Validation mode</label>
                                                                <Select value={templateConfig.mode} onChange={(e) => patchTemplateConfig({ mode: e.target.value as PolicyTemplateMode })}>
                                                                    <option value="contains">Contains blocked words</option>
                                                                    <option value="regex">Regex pattern</option>
                                                                </Select>
                                                            </div>
                                                            <div className="space-y-1">
                                                                <label className="text-xs font-medium">Check target</label>
                                                                <Select value={templateConfig.target} onChange={(e) => patchTemplateConfig({ target: e.target.value as PolicyTemplateTarget })}>
                                                                    <option value="request">User request</option>
                                                                    <option value="response">Model response</option>
                                                                    <option value="both">Request + response</option>
                                                                </Select>
                                                            </div>
                                                            <div className="space-y-1 sm:col-span-2">
                                                                <label className="text-xs font-medium">{templateConfig.mode === "regex" ? "Regex pattern" : "Blocked words (comma separated)"}</label>
                                                                <Input
                                                                    value={templateConfig.mode === "regex" ? templateConfig.pattern : templateConfig.terms}
                                                                    onChange={(e) => patchTemplateConfig(
                                                                        templateConfig.mode === "regex"
                                                                            ? { pattern: e.target.value }
                                                                            : { terms: e.target.value }
                                                                    )}
                                                                    placeholder={templateConfig.mode === "regex" ? "(blocked-word|secret-token)" : "blocked-word, secret-token"}
                                                                />
                                                            </div>
                                                        </div>
                                                    )}
                                                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                                        <div className="space-y-1">
                                                            <label className="text-xs font-medium">Webhook timeout (ms)</label>
                                                            <Input
                                                                value={templateConfig.timeoutMs}
                                                                onChange={(e) => patchTemplateConfig({ timeoutMs: e.target.value })}
                                                                placeholder="3000"
                                                            />
                                                        </div>
                                                        {templateKind !== "webhook-validate" && (
                                                            <div className="space-y-1">
                                                                <label className="text-xs font-medium">Log label</label>
                                                                <Input
                                                                    value={templateConfig.logLabel}
                                                                    onChange={(e) => patchTemplateConfig({ logLabel: e.target.value })}
                                                                    placeholder="policy-audit"
                                                                />
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                                                        {templateKind !== "log-only" && (
                                                            <label className="flex items-center gap-2">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={templateConfig.deny}
                                                                    onChange={(e) => patchTemplateConfig({ deny: e.target.checked })}
                                                                />
                                                                Block on fail
                                                            </label>
                                                        )}
                                                        <label className="flex items-center gap-2">
                                                            <input
                                                                type="checkbox"
                                                                checked={templateConfig.async}
                                                                onChange={(e) => patchTemplateConfig({ async: e.target.checked })}
                                                            />
                                                            Run async / observe-only
                                                        </label>
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    )}
                                    <Textarea
                                        value={formData.body}
                                        onChange={(e) => setFormData({ ...formData, body: e.target.value })}
                                        className="h-[40vh] min-h-72 resize-none rounded-xl border-border/70 bg-background/80 font-mono text-xs leading-5 shadow-inner"
                                        placeholder='{"checks": [...], "actions": [{"type": "block", "message": "Blocked"}]}'
                                    />
                                    <p className="text-[11px] text-muted-foreground">
                                        The JSON stays fully editable — template selections only prefill the structure for you.
                                    </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <DialogFooter className="shrink-0 border-t pt-4">
                        <Button variant="outline" onClick={() => setDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSave} disabled={saving}>
                            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            {editingPolicy ? "Update" : "Create"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Quick Tips */}
            <div className="p-4 rounded-lg border border-primary/20 bg-primary/5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2 mb-3">
                    <Lightbulb className="w-4 h-4 text-primary" />
                    <span className="font-medium text-sm text-primary">Quick Tips</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {isCloudMode ? (
                        <>
                            <div className="flex items-start gap-2">
                                <Cloud className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Cloud Mode:</strong> Policies are guardrails synced with your Portkey Cloud account.</p>
                            </div>
                            <div className="flex items-start gap-2">
                                <Plus className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Create:</strong> Saves the guardrail to Portkey Cloud and to the local database.</p>
                            </div>
                            <div className="flex items-start gap-2">
                                <Trash2 className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Delete:</strong> Removes from both Portkey Cloud and the local database.</p>
                            </div>
                            <div className="flex items-start gap-2">
                                <CloudDownload className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Sync from Cloud:</strong> Pulls guardrails from Portkey, creates missing ones locally, removes orphaned.</p>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="flex items-start gap-2">
                                <HardDrive className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Local Mode:</strong> Policies are stored only in the local database. No cloud sync.</p>
                            </div>
                            <div className="flex items-start gap-2">
                                <Plus className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Create:</strong> Saves the policy to the local database only.</p>
                            </div>
                            <div className="flex items-start gap-2">
                                <Trash2 className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Delete:</strong> Removes from the local database only.</p>
                            </div>
                            <div className="flex items-start gap-2">
                                <Shield className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                                <p><strong>Use case:</strong> Self-hosted Portkey Gateway or offline environments.</p>
                            </div>
                        </>
                    )}
                </div>
            </div>

            {/* Delete Confirmation */}
            <Dialog open={deleteConfirm !== null} onOpenChange={() => setDeleteConfirm(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Policy</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete this policy? This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => deleteConfirm !== null && handleDelete(deleteConfirm)}
                            disabled={deleteLoading}
                        >
                            {deleteLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Detail Modal — large */}
            {selectedPolicy && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
                    <div className="bg-card border border-border rounded-xl w-full max-w-3xl max-h-[85vh] overflow-hidden">
                        <div className="flex items-center justify-between p-5 border-b border-border">
                            <div className="flex items-center gap-3">
                                <div className={`p-2 rounded-lg ${selectedPolicy.is_active ? "bg-accent/10" : "bg-muted"}`}>
                                    <Shield className={`w-5 h-5 ${selectedPolicy.is_active ? "text-accent" : "text-muted-foreground"}`} />
                                </div>
                                <div>
                                    <h3 className="font-semibold text-lg">{selectedPolicy.name}</h3>
                                    <div className="flex items-center gap-2 mt-1">
                                        <Badge variant={selectedPolicy.is_active ? "success" : "secondary"}>
                                            {selectedPolicy.is_active ? "Active" : "Inactive"}
                                        </Badge>
                                        <Badge variant="outline" className="text-xs">
                                            {selectedPolicy.provider_name}
                                        </Badge>
                                    </div>
                                </div>
                            </div>
                            <button
                                onClick={() => setSelectedPolicy(null)}
                                className="p-1.5 rounded-lg hover:bg-secondary cursor-pointer"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="p-5 overflow-y-auto max-h-[calc(85vh-5rem)] space-y-5">
                            <div className="grid grid-cols-2 gap-5">
                                <div className="p-4 rounded-lg bg-secondary/30">
                                    <label className="text-xs text-muted-foreground uppercase tracking-wider">Created At</label>
                                    <p className="text-sm font-medium mt-1">{new Date(selectedPolicy.created_at).toLocaleString()}</p>
                                </div>
                                <div className="p-4 rounded-lg bg-secondary/30">
                                    <label className="text-xs text-muted-foreground uppercase tracking-wider">Updated At</label>
                                    <p className="text-sm font-medium mt-1">{new Date(selectedPolicy.updated_at).toLocaleString()}</p>
                                </div>
                            </div>
                            <div>
                                <label className="text-xs text-muted-foreground uppercase tracking-wider">Policy Body (JSON)</label>
                                <pre className="mt-2 max-h-[50vh] overflow-auto rounded-lg bg-secondary p-5 font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-break-word">
                                    {JSON.stringify(selectedPolicy.body, null, 2)}
                                </pre>
                            </div>
                            <div className="flex justify-end gap-2 pt-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                        setSelectedPolicy(null);
                                        openEdit(selectedPolicy);
                                    }}
                                >
                                    <Pencil className="w-3.5 h-3.5 mr-2" />
                                    Edit
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setSelectedPolicy(null)}
                                >
                                    Close
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

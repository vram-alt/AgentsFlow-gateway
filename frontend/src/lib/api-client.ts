/**
 * Centralized API client for AI Gateway backend.
 * Uses same-origin `/api` requests in the browser to avoid CORS issues.
 */

import { getStoredAuthToken } from "@/lib/auth-context";

const SERVER_API_BASE =
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000";
const API_BASE = typeof window === "undefined" ? SERVER_API_BASE : "";

// ─── Auth header (HTTP Basic Auth) ──────────────────────────────────────
function getHeaders(): HeadersInit {
    const token = getStoredAuthToken();
    if (token) {
        return {
            "Content-Type": "application/json",
            Authorization: `Basic ${token}`,
        };
    }
    // Fallback to env vars (for SSR or when not logged in yet)
    const username = process.env.NEXT_PUBLIC_ADMIN_USERNAME || "gateway_operator";
    const password = process.env.NEXT_PUBLIC_ADMIN_PASSWORD || "Str0ng!Pass#2024";
    const encoded = typeof btoa === "function"
        ? btoa(`${username}:${password}`)
        : Buffer.from(`${username}:${password}`).toString("base64");
    return {
        "Content-Type": "application/json",
        Authorization: `Basic ${encoded}`,
    };
}

// ─── Human-readable error messages ──────────────────────────────────────
function formatErrorMessage(status: number, detail: string, errorCode: string): string {
    // If backend returned a detailed message, prefer it (it's already human-readable)
    if (detail && detail.length > 20) {
        return detail;
    }

    // Map error codes from backend to readable messages
    const codeMessages: Record<string, string> = {
        AUTH_FAILED: "Authentication failed — provider not found or invalid API key",
        VALIDATION_ERROR: "Validation error — check your input data",
        RATE_LIMITED: "Rate limit exceeded — too many requests, please wait and try again",
        TIMEOUT: "Request timed out — the provider did not respond in time",
        PROVIDER_ERROR: "External provider error — the service returned an unexpected response",
        INTERNAL_ERROR: "Internal server error — please try again later",
        UNKNOWN: "An unexpected error occurred",
    };

    if (errorCode && codeMessages[errorCode]) {
        return detail ? `${codeMessages[errorCode]}: ${detail}` : codeMessages[errorCode];
    }

    // Map HTTP status codes to readable messages
    const statusMessages: Record<number, string> = {
        400: "Bad request — check your input data",
        401: "Authentication failed — check your username and password",
        403: "Access denied — you don't have permission for this action",
        404: "Resource not found",
        409: "Conflict — this resource already exists",
        422: "Validation error — check the format of your data",
        429: "Too many requests — please wait and try again",
        500: "Internal server error — please try again later",
        502: "External provider error",
        503: "Service temporarily unavailable — please try again later",
        504: "Request timed out — the provider did not respond in time",
    };

    const base = statusMessages[status] || `Error ${status}`;
    return detail ? `${base}: ${detail}` : base;
}

// ─── Generic fetch wrapper ──────────────────────────────────────────────
async function apiFetch<T>(
    path: string,
    options: RequestInit = {}
): Promise<T> {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        ...options,
        headers: {
            ...getHeaders(),
            ...(options.headers || {}),
        },
    });

    if (!res.ok) {
        const body = await res.json().catch(() => ({ message: res.statusText }));

        // Normalize detail: backend may return a string (custom handler)
        // or an array of Pydantic error objects (fallback/default handler).
        let rawDetail = body.message || body.detail || "";
        if (Array.isArray(rawDetail)) {
            // Convert array of Pydantic error objects to readable text
            rawDetail = rawDetail
                .map((err: { loc?: string[]; msg?: string }) => {
                    const loc = (err.loc || [])
                        .filter((p: string) => p !== "body")
                        .join(" → ");
                    const msg = err.msg || "invalid value";
                    return loc ? `${loc}: ${msg}` : msg;
                })
                .join("; ");
        } else if (typeof rawDetail === "object" && rawDetail !== null) {
            // Safety: if detail is some other object, stringify it
            rawDetail = JSON.stringify(rawDetail);
        }

        const detail = String(rawDetail);
        const errorCode = body.error_code || "";
        const humanMessage = formatErrorMessage(res.status, detail, errorCode);
        throw new ApiError(res.status, humanMessage, body);
    }

    // Handle empty responses (204, etc.)
    const text = await res.text();
    if (!text) return {} as T;
    return JSON.parse(text) as T;
}

export class ApiError extends Error {
    constructor(
        public status: number,
        message: string,
        public body?: unknown
    ) {
        super(message);
        this.name = "ApiError";
    }
}

// ─── Types ──────────────────────────────────────────────────────────────

export interface MessageItem {
    role: string;
    content: string;
}

export interface ChatRequest {
    model: string;
    messages: MessageItem[];
    provider_name?: string;
    temperature?: number | null;
    max_tokens?: number | null;
    guardrail_ids?: string[];
    metadata?: Record<string, unknown>;
}

export interface UsageInfo {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
}

export interface GuardrailCheckInfo {
    id: string;
    verdict: boolean;
    explanation: string;
}

export interface GuardrailDetails {
    summary: string;
    hooks: Array<{
        id: string;
        verdict: boolean;
        deny: boolean;
        checks: GuardrailCheckInfo[];
    }>;
    failed_checks: GuardrailCheckInfo[];
    passed_checks: GuardrailCheckInfo[];
}

export interface ChatResponse {
    trace_id: string;
    content: string;
    model: string;
    usage?: UsageInfo | null;
    guardrail_blocked: boolean;
    guardrail_details?: GuardrailDetails | null;
}

export interface Provider {
    id: number;
    name: string;
    api_key: string;
    base_url: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface ProviderCreateRequest {
    name: string;
    api_key: string;
    base_url: string;
}

export interface ProviderUpdateRequest {
    name?: string | null;
    api_key?: string | null;
    base_url?: string | null;
}

export interface ProviderHealth {
    name: string;
    status: string;
    latency_ms?: number;
    error?: string;
}

export interface Policy {
    id: number;
    name: string;
    body: Record<string, unknown>;
    remote_id?: string | null;
    provider_name: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface PolicyCreateRequest {
    name: string;
    body: Record<string, unknown>;
    provider_name?: string;
}

export interface PolicyUpdateRequest {
    name?: string | null;
    body?: Record<string, unknown> | null;
}

export interface LogEntry {
    id: number;
    event_type: string;
    trace_id: string;
    payload: Record<string, unknown>;
    created_at: string;
}

export interface LogStats {
    total: number;
    by_event_type: Record<string, number>;
}

export interface StatsSummary {
    total_requests: number;
    total_errors: number;
    avg_latency_ms: number;
    requests_today: number;
    error_rate: number;
    top_models: Array<{ model: string; count: number }>;
    top_providers: Array<{ provider: string; count: number }>;
    // Legacy fields from backend
    total?: number;
    chat_requests?: number;
    guardrail_incidents?: number;
    system_errors?: number;
    total_tokens?: number;
}

export type ChartData = Array<{ hour: string; count: number }>;

export interface TesterProxyRequest {
    provider_name: string;
    method?: string;
    path?: string;
    body?: Record<string, unknown> | null;
    headers?: Record<string, string> | null;
}

export interface TesterProxyResponse {
    status_code: number;
    headers: Record<string, string>;
    body: unknown;
    latency_ms: number;
}

export interface TesterFormSchema {
    fields: Array<{
        name: string;
        type: string;
        label: string;
        required: boolean;
        default: unknown;
        options: string[] | null;
    }>;
}

// ─── Config Types ───────────────────────────────────────────────────────

export interface PortkeyConfig {
    id: string;
    name: string;
    slug: string;
    status: string;
    is_default: number;
    created_at: string;
    last_updated_at: string;
}

export interface PortkeyConfigDetail {
    config: Record<string, unknown>;
    [key: string]: unknown;
}

export interface ConfigCreateRequest {
    name: string;
    config: Record<string, unknown>;
    is_default?: number;
    provider_name?: string;
}

export interface ConfigUpdateRequest {
    name?: string | null;
    config?: Record<string, unknown> | null;
    status?: string | null;
}

export interface PortkeyIntegration {
    id: string;
    name: string;
    slug: string;
    ai_provider_id: string;
    status: string;
    created_at: string;
}

export interface PortkeyGuardrail {
    remote_id: string;
    name: string;
    config: Record<string, unknown>;
}

// ─── API Methods ────────────────────────────────────────────────────────

// Health
export const api = {
    // Health
    health: () => apiFetch<{ status: string }>("/health"),

    // Chat
    sendChat: (data: ChatRequest) =>
        apiFetch<ChatResponse>("/api/chat/send", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    // Providers
    listProviders: () => apiFetch<Provider[]>("/api/providers"),
    createProvider: (data: ProviderCreateRequest) =>
        apiFetch<Provider>("/api/providers", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    updateProvider: (id: number, data: ProviderUpdateRequest) =>
        apiFetch<Provider>(`/api/providers/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    deleteProvider: (id: number) =>
        apiFetch<{ status: string }>(`/api/providers/${id}`, {
            method: "DELETE",
        }),
    toggleProvider: (id: number) =>
        apiFetch<Provider>(`/api/providers/${id}/toggle`, {
            method: "PATCH",
        }),
    getProvidersHealth: () =>
        apiFetch<ProviderHealth[]>("/api/providers/health"),

    // Policies
    listPolicies: () => apiFetch<Policy[]>("/api/policies"),
    createPolicy: (data: PolicyCreateRequest) =>
        apiFetch<Policy>("/api/policies", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    updatePolicy: (id: number, data: PolicyUpdateRequest) =>
        apiFetch<Policy>(`/api/policies/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    deletePolicy: (id: number) =>
        apiFetch<{ status: string }>(`/api/policies/${id}`, {
            method: "DELETE",
        }),
    togglePolicy: (id: number) =>
        apiFetch<Policy>(`/api/policies/${id}/toggle`, {
            method: "PATCH",
        }),
    syncPolicies: (providerName: string = "portkey") =>
        apiFetch<unknown>("/api/policies/sync", {
            method: "POST",
            body: JSON.stringify({ provider_name: providerName }),
        }),

    // Logs
    getLogs: (params?: {
        limit?: number;
        offset?: number;
        event_type?: string;
        trace_id?: string;
    }) => {
        const searchParams = new URLSearchParams();
        if (params?.limit) searchParams.set("limit", String(params.limit));
        if (params?.offset) searchParams.set("offset", String(params.offset));
        if (params?.event_type) searchParams.set("event_type", params.event_type);
        if (params?.trace_id) searchParams.set("trace_id", params.trace_id);
        const qs = searchParams.toString();
        return apiFetch<LogEntry[]>(`/api/logs${qs ? `?${qs}` : ""}`);
    },
    getLogStats: () => apiFetch<LogStats>("/api/logs/stats"),
    getLogsByTraceId: (traceId: string) =>
        apiFetch<LogEntry[]>(`/api/logs/${traceId}`),
    replayLog: (logId: number) =>
        apiFetch<ChatResponse>(`/api/logs/${logId}/replay`, {
            method: "POST",
        }),
    exportLogs: (params?: { event_type?: string; limit?: number }): string => {
        const searchParams = new URLSearchParams();
        if (params?.event_type) searchParams.set("event_type", params.event_type);
        if (params?.limit) searchParams.set("limit", String(params.limit));
        const qs = searchParams.toString();
        return `${API_BASE}/api/logs/export${qs ? `?${qs}` : ""}`;
    },

    /** Download CSV export with auth headers, returning a Blob. */
    downloadExportCsv: async (params?: { event_type?: string; limit?: number }): Promise<void> => {
        const searchParams = new URLSearchParams();
        if (params?.event_type) searchParams.set("event_type", params.event_type);
        if (params?.limit) searchParams.set("limit", String(params.limit));
        const qs = searchParams.toString();
        const url = `${API_BASE}/api/logs/export${qs ? `?${qs}` : ""}`;

        const res = await fetch(url, {
            headers: getHeaders(),
        });

        if (!res.ok) {
            const body = await res.json().catch(() => ({ detail: res.statusText }));
            const detail = body.detail || body.message || res.statusText;
            throw new ApiError(res.status, formatErrorMessage(res.status, String(detail), ""), body);
        }

        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = "logs_export.csv";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
    },

    // Stats (Dashboard)
    getStatsSummary: () => apiFetch<StatsSummary>("/api/stats/summary"),
    getStatsCharts: (hours: number = 24) =>
        apiFetch<ChartData>(`/api/stats/charts?hours=${hours}`),

    // Tester
    getTesterSchema: () => apiFetch<TesterFormSchema>("/api/tester/schema"),
    testerProxy: (data: TesterProxyRequest) =>
        apiFetch<TesterProxyResponse>("/api/tester/proxy", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    // Settings
    getDemoMode: () => apiFetch<{ enabled: boolean }>("/api/settings/demo-mode"),
    setDemoMode: (enabled: boolean) =>
        apiFetch<{ enabled: boolean; message: string }>("/api/settings/demo-mode", {
            method: "PUT",
            body: JSON.stringify({ enabled }),
        }),

    // Configs (Portkey)
    listConfigs: () => apiFetch<PortkeyConfig[]>("/api/configs/"),
    createConfig: (data: ConfigCreateRequest) =>
        apiFetch<{ id: string; version_id: string }>("/api/configs/", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    retrieveConfig: (slug: string) =>
        apiFetch<PortkeyConfigDetail>(`/api/configs/${slug}`),
    updateConfig: (slug: string, data: ConfigUpdateRequest) =>
        apiFetch<{ version_id: string }>(`/api/configs/${slug}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    deleteConfig: (slug: string) =>
        apiFetch<{ status: string }>(`/api/configs/${slug}`, {
            method: "DELETE",
        }),
    toggleConfig: (slug: string) =>
        apiFetch<unknown>(`/api/configs/${slug}/toggle`, {
            method: "PATCH",
        }),
    listConfigGuardrails: () =>
        apiFetch<PortkeyGuardrail[]>("/api/configs/guardrails"),
    listIntegrations: () =>
        apiFetch<PortkeyIntegration[]>("/api/configs/integrations"),
};

/**
 * Centralized API client for AI Gateway backend (http://localhost:8000).
 * All 22 endpoints covered.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Auth header ────────────────────────────────────────────────────────
function getHeaders(): HeadersInit {
    return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_TOKEN || "dev-token"}`,
    };
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
        throw new ApiError(res.status, body.message || body.detail || res.statusText, body);
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
}

export interface UsageInfo {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
}

export interface ChatResponse {
    trace_id: string;
    content: string;
    model: string;
    usage?: UsageInfo | null;
    guardrail_blocked: boolean;
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
}

export interface ChartData {
    hourly_requests: Array<{ hour: string; count: number }>;
    hourly_errors: Array<{ hour: string; count: number }>;
    hourly_latency: Array<{ hour: string; avg_ms: number }>;
}

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
    listProviders: () => apiFetch<Provider[]>("/api/providers/"),
    createProvider: (data: ProviderCreateRequest) =>
        apiFetch<Provider>("/api/providers/", {
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
    getProvidersHealth: () =>
        apiFetch<ProviderHealth[]>("/api/providers/health"),

    // Policies
    listPolicies: () => apiFetch<Policy[]>("/api/policies/"),
    createPolicy: (data: PolicyCreateRequest) =>
        apiFetch<Policy>("/api/policies/", {
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
        return apiFetch<LogEntry[]>(`/api/logs/${qs ? `?${qs}` : ""}`);
    },
    getLogStats: () => apiFetch<LogStats>("/api/logs/stats"),
    getLogsByTraceId: (traceId: string) =>
        apiFetch<LogEntry[]>(`/api/logs/${traceId}`),
    replayLog: (logId: number) =>
        apiFetch<ChatResponse>(`/api/logs/${logId}/replay`, {
            method: "POST",
        }),
    exportLogs: (params?: { event_type?: string; limit?: number }) => {
        const searchParams = new URLSearchParams();
        if (params?.event_type) searchParams.set("event_type", params.event_type);
        if (params?.limit) searchParams.set("limit", String(params.limit));
        const qs = searchParams.toString();
        return `${API_BASE}/api/logs/export${qs ? `?${qs}` : ""}`;
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
};

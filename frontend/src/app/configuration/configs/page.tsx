"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogDescription,
} from "@/components/ui/dialog";
import {
    FileCode,
    Plus,
    Pencil,
    Trash2,
    Loader2,
    AlertTriangle,
    Eye,
    Power,
    RefreshCw,
    Shield,
    Plug,
    Copy,
    Check,
    RotateCcw,
    Database,
    Clock,
    Zap,
    ChevronDown,
    ChevronRight,
    Code,
    Layers,
} from "lucide-react";
import {
    api,
    ApiError,
    type PortkeyConfig,
    type PortkeyConfigDetail,
    type PortkeyIntegration,
    type PortkeyGuardrail,
} from "@/lib/api-client";

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

// ── Config builder types ────────────────────────────────────────────────

type CacheMode = "" | "simple" | "semantic";
type StrategyMode = "" | "fallback" | "loadbalance";

interface ConfigBuilderState {
    // Targets
    selectedIntegration: string;
    // Guardrails (Portkey recommended: simple ID arrays)
    inputGuardrails: string[];
    outputGuardrails: string[];
    // Override params (model & hyperparameters)
    overrideModel: string;
    overrideTemperature: string;
    overrideMaxTokens: string;
    // Retry
    retryEnabled: boolean;
    retryAttempts: number;
    retryStatusCodes: string; // comma separated
    // Cache
    cacheMode: CacheMode;
    cacheMaxAge: string;
    // Strategy
    strategyMode: StrategyMode;
    // Timeout
    requestTimeout: string;
    // Metadata
    customMetadata: string; // JSON string for extra fields
}

const defaultBuilderState: ConfigBuilderState = {
    selectedIntegration: "",
    inputGuardrails: [],
    outputGuardrails: [],
    overrideModel: "",
    overrideTemperature: "",
    overrideMaxTokens: "",
    retryEnabled: false,
    retryAttempts: 3,
    retryStatusCodes: "",
    cacheMode: "",
    cacheMaxAge: "",
    strategyMode: "",
    requestTimeout: "",
    customMetadata: "",
};

function builderToConfigBody(state: ConfigBuilderState): Record<string, unknown> {
    const config: Record<string, unknown> = {};

    // Single provider: virtual_key at root. Multi-target: use targets array with strategy.
    if (state.selectedIntegration) {
        if (state.strategyMode) {
            config.targets = [{ virtual_key: state.selectedIntegration }];
        } else {
            config.virtual_key = state.selectedIntegration;
        }
    }

    // Override params (model & hyperparameters)
    const overrideParams: Record<string, unknown> = {};
    if (state.overrideModel.trim()) {
        overrideParams.model = state.overrideModel.trim();
    }
    if (state.overrideTemperature.trim()) {
        const temp = parseFloat(state.overrideTemperature.trim());
        if (!isNaN(temp)) overrideParams.temperature = temp;
    }
    if (state.overrideMaxTokens.trim()) {
        const mt = parseInt(state.overrideMaxTokens.trim(), 10);
        if (!isNaN(mt) && mt > 0) overrideParams.max_tokens = mt;
    }
    if (Object.keys(overrideParams).length > 0) {
        config.override_params = overrideParams;
    }

    // Input guardrails (recommended Portkey format: simple ID arrays)
    if (state.inputGuardrails.length > 0) {
        config.input_guardrails = [...state.inputGuardrails];
    }

    // Output guardrails
    if (state.outputGuardrails.length > 0) {
        config.output_guardrails = [...state.outputGuardrails];
    }

    // Retry
    if (state.retryEnabled && state.retryAttempts > 0) {
        const retry: Record<string, unknown> = { attempts: state.retryAttempts };
        if (state.retryStatusCodes.trim()) {
            retry.on_status_codes = state.retryStatusCodes
                .split(",")
                .map((s) => parseInt(s.trim(), 10))
                .filter((n) => !isNaN(n));
        }
        config.retry = retry;
    }

    // Cache
    if (state.cacheMode) {
        const cache: Record<string, unknown> = { mode: state.cacheMode };
        if (state.cacheMaxAge.trim()) {
            const maxAge = parseInt(state.cacheMaxAge.trim(), 10);
            if (!isNaN(maxAge) && maxAge > 0) cache.max_age = maxAge;
        }
        config.cache = cache;
    }

    // Strategy
    if (state.strategyMode) {
        config.strategy = { mode: state.strategyMode };
    }

    // Timeout
    if (state.requestTimeout.trim()) {
        const timeout = parseInt(state.requestTimeout.trim(), 10);
        if (!isNaN(timeout) && timeout > 0) config.request_timeout = timeout;
    }

    // Custom metadata (merge)
    if (state.customMetadata.trim()) {
        try {
            const extra = JSON.parse(state.customMetadata);
            if (typeof extra === "object" && extra !== null) {
                Object.assign(config, extra);
            }
        } catch { /* ignore invalid JSON */ }
    }

    return config;
}

function configBodyToBuilder(body: Record<string, unknown>): ConfigBuilderState {
    const state = { ...defaultBuilderState };

    // Targets — handle both top-level virtual_key and targets array
    if (typeof body.virtual_key === "string") {
        state.selectedIntegration = body.virtual_key;
    } else {
        const targets = body.targets as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(targets) && targets.length > 0 && typeof targets[0].virtual_key === "string") {
            state.selectedIntegration = targets[0].virtual_key;
        }
    }

    // Override params
    const op = body.override_params as Record<string, unknown> | undefined;
    if (op && typeof op === "object") {
        if (typeof op.model === "string") state.overrideModel = op.model;
        if (typeof op.temperature === "number") state.overrideTemperature = String(op.temperature);
        if (typeof op.max_tokens === "number") state.overrideMaxTokens = String(op.max_tokens);
    }

    // Guardrails — handle both new (input_guardrails) and legacy (before_request_hooks) formats
    const inputGr = body.input_guardrails as string[] | undefined;
    if (Array.isArray(inputGr)) {
        state.inputGuardrails = inputGr.filter((id) => typeof id === "string");
    } else {
        const beforeHooks = body.before_request_hooks as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(beforeHooks)) {
            state.inputGuardrails = beforeHooks
                .filter((h) => h.id)
                .map((h) => String(h.id));
        }
    }

    const outputGr = body.output_guardrails as string[] | undefined;
    if (Array.isArray(outputGr)) {
        state.outputGuardrails = outputGr.filter((id) => typeof id === "string");
    } else {
        const afterHooks = body.after_request_hooks as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(afterHooks)) {
            state.outputGuardrails = afterHooks
                .filter((h) => h.id)
                .map((h) => String(h.id));
        }
    }

    // Retry
    const retry = body.retry as Record<string, unknown> | undefined;
    if (retry && typeof retry === "object") {
        state.retryEnabled = true;
        state.retryAttempts = typeof retry.attempts === "number" ? retry.attempts : 3;
        if (Array.isArray(retry.on_status_codes)) {
            state.retryStatusCodes = retry.on_status_codes.join(", ");
        }
    }

    // Cache
    const cache = body.cache as Record<string, unknown> | undefined;
    if (cache && typeof cache === "object") {
        state.cacheMode = (cache.mode as CacheMode) || "";
        if (typeof cache.max_age === "number") {
            state.cacheMaxAge = String(cache.max_age);
        }
    }

    // Strategy
    const strategy = body.strategy as Record<string, unknown> | undefined;
    if (strategy && typeof strategy === "object") {
        state.strategyMode = (strategy.mode as StrategyMode) || "";
    }

    // Timeout
    if (typeof body.request_timeout === "number") {
        state.requestTimeout = String(body.request_timeout);
    }

    // Collect remaining fields as custom metadata
    const knownKeys = new Set([
        "targets", "virtual_key", "before_request_hooks", "after_request_hooks",
        "input_guardrails", "output_guardrails", "override_params",
        "retry", "cache", "strategy", "request_timeout",
    ]);
    const extra: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(body)) {
        if (!knownKeys.has(k)) extra[k] = v;
    }
    if (Object.keys(extra).length > 0) {
        state.customMetadata = JSON.stringify(extra, null, 2);
    }

    return state;
}

// ── Collapsible section helper ──────────────────────────────────────────

function Section({
    title,
    icon: Icon,
    badge,
    children,
    defaultOpen = false,
}: {
    title: string;
    icon: React.ComponentType<{ className?: string }>;
    badge?: string;
    children: React.ReactNode;
    defaultOpen?: boolean;
}) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="border border-border/60 rounded-lg overflow-hidden">
            <button
                type="button"
                onClick={() => setOpen(!open)}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium hover:bg-secondary/40 transition-colors text-left"
            >
                {open ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
                <Icon className="w-3.5 h-3.5 text-primary" />
                <span>{title}</span>
                {badge && <Badge variant="secondary" className="text-[10px] ml-auto">{badge}</Badge>}
            </button>
            {open && <div className="px-3 pb-3 space-y-3 border-t border-border/40 pt-3">{children}</div>}
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════════════════

export default function ConfigsPage() {
    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Configs</h1>
                <p className="text-muted-foreground">
                    Manage Portkey configs — attach guardrails, integrations, retry and cache settings
                </p>
            </div>

            <Tabs defaultValue="configs" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="configs" className="gap-2">
                        <FileCode className="w-4 h-4" />
                        Configs
                    </TabsTrigger>
                    <TabsTrigger value="guardrails" className="gap-2">
                        <Shield className="w-4 h-4" />
                        Guardrails
                    </TabsTrigger>
                    <TabsTrigger value="integrations" className="gap-2">
                        <Plug className="w-4 h-4" />
                        Integrations
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="configs">
                    <ConfigsTab />
                </TabsContent>
                <TabsContent value="guardrails">
                    <GuardrailsTab />
                </TabsContent>
                <TabsContent value="integrations">
                    <IntegrationsTab />
                </TabsContent>
            </Tabs>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════
// Configs Tab
// ═══════════════════════════════════════════════════════════════════════

function ConfigsTab() {
    const [configs, setConfigs] = useState<PortkeyConfig[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [actionLoading, setActionLoading] = useState<string | null>(null);

    // Dialog state
    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
    const [dialogView, setDialogView] = useState<"builder" | "json">("builder");
    const [editSlug, setEditSlug] = useState<string | null>(null);

    // View dialog
    const [viewOpen, setViewOpen] = useState(false);
    const [viewDetail, setViewDetail] = useState<PortkeyConfigDetail | null>(null);
    const [viewName, setViewName] = useState("");
    const [viewLoading, setViewLoading] = useState(false);

    // Delete confirm
    const [deleteSlug, setDeleteSlug] = useState<string | null>(null);
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

    // Available guardrails & integrations for create/edit dialog
    const [guardrails, setGuardrails] = useState<PortkeyGuardrail[]>([]);
    const [integrations, setIntegrations] = useState<PortkeyIntegration[]>([]);

    // Form state
    const [formName, setFormName] = useState("");
    const [builder, setBuilder] = useState<ConfigBuilderState>(defaultBuilderState);
    const [formConfigJson, setFormConfigJson] = useState("{}");
    const [formError, setFormError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    // Sync builder → JSON when switching to JSON view
    const syncBuilderToJson = useCallback((b: ConfigBuilderState) => {
        setFormConfigJson(JSON.stringify(builderToConfigBody(b), null, 2));
    }, []);

    const fetchConfigs = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await api.listConfigs();
            setConfigs(Array.isArray(data) ? data : []);
        } catch (err) {
            setConfigs([]);
            setError(humanError(err));
        } finally {
            setLoading(false);
        }
    }, []);

    const fetchSelectionData = useCallback(async () => {
        try {
            const [gr, intg] = await Promise.all([
                api.listConfigGuardrails().catch(() => []),
                api.listIntegrations().catch(() => []),
            ]);
            setGuardrails(Array.isArray(gr) ? gr : []);
            setIntegrations(Array.isArray(intg) ? intg : []);
        } catch {
            // Silently fail — these are optional
        }
    }, []);

    useEffect(() => {
        fetchConfigs();
        fetchSelectionData();
    }, [fetchConfigs, fetchSelectionData]);

    // Handle create
    const openCreateDialog = () => {
        setDialogMode("create");
        setDialogView("builder");
        setEditSlug(null);
        setFormName("");
        setBuilder({ ...defaultBuilderState });
        setFormConfigJson("{}");
        setFormError(null);
        setDialogOpen(true);
    };

    // Handle edit
    const openEditDialog = async (cfg: PortkeyConfig) => {
        setDialogMode("edit");
        setDialogView("builder");
        setEditSlug(cfg.slug);
        setFormName(cfg.name);
        setFormError(null);
        setBuilder({ ...defaultBuilderState });
        setDialogOpen(true);

        try {
            const detail = await api.retrieveConfig(cfg.slug);
            const configBody = (detail?.config || {}) as Record<string, unknown>;
            const parsed = configBodyToBuilder(configBody);
            setBuilder(parsed);
            setFormConfigJson(JSON.stringify(configBody, null, 2));
        } catch {
            setFormConfigJson("{}");
        }
    };

    // Handle save
    const handleSave = async () => {
        setFormError(null);

        if (!formName.trim()) {
            setFormError("Name is required");
            return;
        }

        let configBody: Record<string, unknown>;
        if (dialogView === "builder") {
            configBody = builderToConfigBody(builder);
        } else {
            try {
                configBody = JSON.parse(formConfigJson);
            } catch {
                setFormError("Invalid JSON in config body");
                return;
            }
        }

        setSaving(true);
        try {
            if (dialogMode === "create") {
                await api.createConfig({
                    name: formName.trim(),
                    config: configBody,
                });
            } else if (editSlug) {
                await api.updateConfig(editSlug, {
                    name: formName.trim(),
                    config: configBody,
                });
            }
            setDialogOpen(false);
            await fetchConfigs();
        } catch (err) {
            setFormError(humanError(err));
        } finally {
            setSaving(false);
        }
    };

    // Builder mutators
    const updateBuilder = (partial: Partial<ConfigBuilderState>) => {
        setBuilder((prev) => ({ ...prev, ...partial }));
    };

    const toggleGuardrail = (id: string, hook: "input" | "output") => {
        setBuilder((prev) => {
            const key = hook === "input" ? "inputGuardrails" : "outputGuardrails";
            const current = prev[key];
            const updated = current.includes(id)
                ? current.filter((g) => g !== id)
                : [...current, id];
            return { ...prev, [key]: updated };
        });
    };

    // Handle view
    const handleView = async (cfg: PortkeyConfig) => {
        setViewName(cfg.name);
        setViewDetail(null);
        setViewOpen(true);
        setViewLoading(true);
        try {
            const detail = await api.retrieveConfig(cfg.slug);
            setViewDetail(detail);
        } catch {
            setViewDetail({ config: { error: "Failed to load config details" } });
        } finally {
            setViewLoading(false);
        }
    };

    // Handle toggle
    const handleToggle = async (cfg: PortkeyConfig) => {
        setActionLoading(cfg.slug);
        try {
            await api.toggleConfig(cfg.slug);
            await fetchConfigs();
        } catch (err) {
            setError(humanError(err));
        } finally {
            setActionLoading(null);
        }
    };

    // Handle delete
    const handleDelete = async () => {
        if (!deleteSlug) return;
        setActionLoading(deleteSlug);
        try {
            await api.deleteConfig(deleteSlug);
            setDeleteConfirmOpen(false);
            setDeleteSlug(null);
            await fetchConfigs();
        } catch (err) {
            setError(humanError(err));
        } finally {
            setActionLoading(null);
        }
    };

    return (
        <>
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Badge variant="secondary">{configs.length} config{configs.length !== 1 ? "s" : ""}</Badge>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchConfigs} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={openCreateDialog}>
                        <Plus className="w-4 h-4 mr-2" />
                        Create Config
                    </Button>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="mb-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {/* Loading */}
            {loading && configs.length === 0 && (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
            )}

            {/* Empty state */}
            {!loading && configs.length === 0 && !error && (
                <Card>
                    <CardContent className="flex flex-col items-center justify-center py-12">
                        <FileCode className="w-12 h-12 text-muted-foreground/30 mb-4" />
                        <p className="text-sm font-medium text-muted-foreground">No configs found</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Create a config to attach guardrails, integrations, retry and cache settings
                        </p>
                        <Button size="sm" className="mt-4" onClick={openCreateDialog}>
                            <Plus className="w-4 h-4 mr-2" />
                            Create Config
                        </Button>
                    </CardContent>
                </Card>
            )}

            {/* Config list */}
            {configs.length > 0 && (
                <div className="grid gap-3">
                    {configs.map((cfg) => (
                        <Card key={cfg.id || cfg.slug} className="group hover:border-primary/30 transition-colors">
                            <CardContent className="flex items-center justify-between py-4 px-5">
                                <div className="flex items-center gap-3 min-w-0">
                                    <FileCode className="w-5 h-5 text-primary shrink-0" />
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium text-sm truncate">
                                                {cfg.name}
                                            </span>
                                            <Badge variant={cfg.status === "active" ? "success" : "secondary"} className="text-[10px]">
                                                {cfg.status}
                                            </Badge>
                                            {cfg.is_default === 1 && (
                                                <Badge variant="outline" className="text-[10px]">default</Badge>
                                            )}
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-0.5">
                                            {cfg.slug && <span className="font-mono">{cfg.slug}</span>}
                                            {cfg.created_at && (
                                                <span className="ml-2">
                                                    Created {new Date(cfg.created_at).toLocaleDateString()}
                                                </span>
                                            )}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button variant="ghost" size="sm" onClick={() => handleView(cfg)} title="View config">
                                        <Eye className="w-4 h-4" />
                                    </Button>
                                    <Button variant="ghost" size="sm" onClick={() => openEditDialog(cfg)} title="Edit config">
                                        <Pencil className="w-4 h-4" />
                                    </Button>
                                    <Button
                                        variant="ghost" size="sm"
                                        onClick={() => handleToggle(cfg)}
                                        disabled={actionLoading === cfg.slug}
                                        title={cfg.status === "active" ? "Deactivate" : "Activate"}
                                    >
                                        {actionLoading === cfg.slug ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Power className={`w-4 h-4 ${cfg.status === "active" ? "text-success" : "text-muted-foreground"}`} />
                                        )}
                                    </Button>
                                    <Button
                                        variant="ghost" size="sm"
                                        onClick={() => { setDeleteSlug(cfg.slug); setDeleteConfirmOpen(true); }}
                                        title="Delete config"
                                        className="text-destructive hover:text-destructive"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            {/* ═══ Create / Edit Dialog — Config Builder ═══ */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
                    <DialogHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <DialogTitle>
                                    {dialogMode === "create" ? "Create Config" : "Edit Config"}
                                </DialogTitle>
                                <DialogDescription>
                                    {dialogMode === "create"
                                        ? "Build a Portkey config with guardrails, routing, retry and cache settings"
                                        : "Update the config settings"}
                                </DialogDescription>
                            </div>
                            {/* Builder / JSON toggle */}
                            <div className="flex rounded-lg border border-border/60 overflow-hidden">
                                <button
                                    type="button"
                                    onClick={() => {
                                        if (dialogView === "json") {
                                            // Try to sync JSON back to builder
                                            try {
                                                const parsed = JSON.parse(formConfigJson);
                                                setBuilder(configBodyToBuilder(parsed));
                                            } catch { /* keep builder state */ }
                                        }
                                        setDialogView("builder");
                                    }}
                                    className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-colors ${
                                        dialogView === "builder" ? "bg-primary text-primary-foreground" : "hover:bg-secondary/60"
                                    }`}
                                >
                                    <Layers className="w-3 h-3" />
                                    Builder
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        syncBuilderToJson(builder);
                                        setDialogView("json");
                                    }}
                                    className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-colors ${
                                        dialogView === "json" ? "bg-primary text-primary-foreground" : "hover:bg-secondary/60"
                                    }`}
                                >
                                    <Code className="w-3 h-3" />
                                    JSON
                                </button>
                            </div>
                        </div>
                    </DialogHeader>

                    <div className="flex-1 overflow-hidden space-y-4 py-2 pr-1">
                        {/* Name (always visible) */}
                        <div className="space-y-1.5">
                            <label className="text-sm font-medium">Config Name</label>
                            <Input
                                value={formName}
                                onChange={(e) => setFormName(e.target.value)}
                                placeholder="e.g., Production with Guardrails"
                            />
                        </div>

                        {dialogView === "builder" ? (
                            /* ─── VISUAL BUILDER ─── */
                            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4 h-[calc(90vh-16rem)] min-h-115">
                                <div className="min-w-0 overflow-y-auto pr-1 space-y-3">
                                {/* Target / Integration */}
                                <Section title="Target Integration" icon={Plug} badge={builder.selectedIntegration ? "1 selected" : undefined} defaultOpen>
                                    <p className="text-xs text-muted-foreground">
                                        Select a virtual key (LLM integration) to route requests through
                                    </p>
                                    {integrations.length > 0 ? (
                                        <div className="flex flex-wrap gap-2">
                                            <button
                                                type="button"
                                                onClick={() => updateBuilder({ selectedIntegration: "" })}
                                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                                                    !builder.selectedIntegration
                                                        ? "bg-primary/10 border-primary/40 text-primary shadow-sm"
                                                        : "bg-secondary/30 border-border/60 text-muted-foreground hover:border-primary/20 hover:bg-secondary/50"
                                                }`}
                                            >
                                                None
                                            </button>
                                            {integrations.map((intg) => (
                                                <button
                                                    key={intg.id}
                                                    type="button"
                                                    onClick={() => updateBuilder({ selectedIntegration: intg.slug })}
                                                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                                                        builder.selectedIntegration === intg.slug
                                                            ? "bg-primary/10 border-primary/40 text-primary shadow-sm"
                                                            : "bg-secondary/30 border-border/60 text-muted-foreground hover:border-primary/20 hover:bg-secondary/50"
                                                    }`}
                                                >
                                                    <Plug className="w-3 h-3" />
                                                    {intg.name}
                                                    <span className="opacity-60">({intg.ai_provider_id})</span>
                                                </button>
                                            ))}
                                        </div>
                                    ) : (
                                        <p className="text-xs text-muted-foreground italic">
                                            No integrations available. Add LLM integrations in your Portkey dashboard.
                                        </p>
                                    )}
                                </Section>

                                {/* Model & Hyperparameters */}
                                <Section
                                    title="Model & Hyperparameters"
                                    icon={Zap}
                                    badge={builder.overrideModel ? builder.overrideModel : undefined}
                                    defaultOpen={!!builder.overrideModel || !!builder.overrideTemperature || !!builder.overrideMaxTokens}
                                >
                                    <p className="text-xs text-muted-foreground">
                                        Override the model and set custom parameters (override_params)
                                    </p>
                                    <div className="space-y-3">
                                        <div className="space-y-1">
                                            <label className="text-xs text-muted-foreground">Model Name</label>
                                            <Input
                                                value={builder.overrideModel}
                                                onChange={(e) => updateBuilder({ overrideModel: e.target.value })}
                                                placeholder="e.g., gpt-4o, claude-sonnet-4-20250514"
                                                className="h-8 text-xs"
                                            />
                                        </div>
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="space-y-1">
                                                <label className="text-xs text-muted-foreground">Temperature</label>
                                                <Input
                                                    value={builder.overrideTemperature}
                                                    onChange={(e) => updateBuilder({ overrideTemperature: e.target.value })}
                                                    placeholder="e.g., 0.7"
                                                    className="h-8 text-xs"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-xs text-muted-foreground">Max Tokens</label>
                                                <Input
                                                    value={builder.overrideMaxTokens}
                                                    onChange={(e) => updateBuilder({ overrideMaxTokens: e.target.value })}
                                                    placeholder="e.g., 1024"
                                                    className="h-8 text-xs"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </Section>

                                {/* Input Guardrails */}
                                <Section
                                    title="Input Guardrails"
                                    icon={Shield}
                                    badge={builder.inputGuardrails.length > 0 ? `${builder.inputGuardrails.length} active` : undefined}
                                    defaultOpen={builder.inputGuardrails.length > 0}
                                >
                                    <p className="text-xs text-muted-foreground">
                                        Guardrails to evaluate <strong>before</strong> sending the request to the LLM
                                    </p>
                                    {guardrails.length > 0 ? (
                                        <div className="flex flex-wrap gap-2">
                                            {guardrails.map((gr) => {
                                                const selected = builder.inputGuardrails.includes(gr.remote_id);
                                                return (
                                                    <button
                                                        key={gr.remote_id}
                                                        type="button"
                                                        onClick={() => toggleGuardrail(gr.remote_id, "input")}
                                                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                                                            selected
                                                                ? "bg-primary/10 border-primary/40 text-primary shadow-sm"
                                                                : "bg-secondary/30 border-border/60 text-muted-foreground hover:border-primary/20 hover:bg-secondary/50"
                                                        }`}
                                                    >
                                                        <Shield className="w-3 h-3" />
                                                        {gr.name || gr.remote_id}
                                                        {selected && <Check className="w-3 h-3" />}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <p className="text-xs text-muted-foreground italic">
                                            No guardrails available. Create guardrails in the Policies page or Portkey dashboard.
                                        </p>
                                    )}
                                </Section>

                                {/* Output Guardrails */}
                                <Section
                                    title="Output Guardrails"
                                    icon={Shield}
                                    badge={builder.outputGuardrails.length > 0 ? `${builder.outputGuardrails.length} active` : undefined}
                                    defaultOpen={builder.outputGuardrails.length > 0}
                                >
                                    <p className="text-xs text-muted-foreground">
                                        Guardrails to evaluate <strong>after</strong> receiving the LLM response
                                    </p>
                                    {guardrails.length > 0 ? (
                                        <div className="flex flex-wrap gap-2">
                                            {guardrails.map((gr) => {
                                                const selected = builder.outputGuardrails.includes(gr.remote_id);
                                                return (
                                                    <button
                                                        key={gr.remote_id}
                                                        type="button"
                                                        onClick={() => toggleGuardrail(gr.remote_id, "output")}
                                                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                                                            selected
                                                                ? "bg-primary/10 border-primary/40 text-primary shadow-sm"
                                                                : "bg-secondary/30 border-border/60 text-muted-foreground hover:border-primary/20 hover:bg-secondary/50"
                                                        }`}
                                                    >
                                                        <Shield className="w-3 h-3" />
                                                        {gr.name || gr.remote_id}
                                                        {selected && <Check className="w-3 h-3" />}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <p className="text-xs text-muted-foreground italic">
                                            No guardrails available.
                                        </p>
                                    )}
                                </Section>

                                {/* Retry */}
                                <Section
                                    title="Retry"
                                    icon={RotateCcw}
                                    badge={builder.retryEnabled ? `${builder.retryAttempts} attempts` : undefined}
                                    defaultOpen={builder.retryEnabled}
                                >
                                    <div className="flex items-center gap-3">
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={builder.retryEnabled}
                                                onChange={(e) => updateBuilder({ retryEnabled: e.target.checked })}
                                                className="rounded border-border"
                                            />
                                            <span className="text-xs">Enable automatic retries</span>
                                        </label>
                                    </div>
                                    {builder.retryEnabled && (
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="space-y-1">
                                                <label className="text-xs text-muted-foreground">Max Attempts</label>
                                                <Input
                                                    type="number"
                                                    min={1}
                                                    max={10}
                                                    value={builder.retryAttempts}
                                                    onChange={(e) => updateBuilder({ retryAttempts: parseInt(e.target.value, 10) || 3 })}
                                                    className="h-8 text-xs"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-xs text-muted-foreground">Status Codes (optional)</label>
                                                <Input
                                                    value={builder.retryStatusCodes}
                                                    onChange={(e) => updateBuilder({ retryStatusCodes: e.target.value })}
                                                    placeholder="429, 500, 502"
                                                    className="h-8 text-xs"
                                                />
                                            </div>
                                        </div>
                                    )}
                                </Section>

                                {/* Cache */}
                                <Section
                                    title="Cache"
                                    icon={Database}
                                    badge={builder.cacheMode || undefined}
                                    defaultOpen={!!builder.cacheMode}
                                >
                                    <p className="text-xs text-muted-foreground">
                                        Cache LLM responses to reduce latency and cost
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {(["", "simple", "semantic"] as CacheMode[]).map((mode) => (
                                            <button
                                                key={mode || "off"}
                                                type="button"
                                                onClick={() => updateBuilder({ cacheMode: mode })}
                                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                                                    builder.cacheMode === mode
                                                        ? "bg-primary/10 border-primary/40 text-primary shadow-sm"
                                                        : "bg-secondary/30 border-border/60 text-muted-foreground hover:border-primary/20 hover:bg-secondary/50"
                                                }`}
                                            >
                                                <Database className="w-3 h-3" />
                                                {mode === "" ? "Off" : mode === "simple" ? "Simple" : "Semantic"}
                                            </button>
                                        ))}
                                    </div>
                                    {builder.cacheMode && (
                                        <div className="space-y-1">
                                            <label className="text-xs text-muted-foreground">Max Age (seconds, optional)</label>
                                            <Input
                                                value={builder.cacheMaxAge}
                                                onChange={(e) => updateBuilder({ cacheMaxAge: e.target.value })}
                                                placeholder="e.g., 3600"
                                                className="h-8 text-xs max-w-48"
                                            />
                                        </div>
                                    )}
                                </Section>

                                {/* Strategy */}
                                <Section
                                    title="Routing Strategy"
                                    icon={Zap}
                                    badge={builder.strategyMode || undefined}
                                    defaultOpen={!!builder.strategyMode}
                                >
                                    <p className="text-xs text-muted-foreground">
                                        How requests are routed across targets (requires multiple targets)
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {(["", "fallback", "loadbalance"] as StrategyMode[]).map((mode) => (
                                            <button
                                                key={mode || "none"}
                                                type="button"
                                                onClick={() => updateBuilder({ strategyMode: mode })}
                                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                                                    builder.strategyMode === mode
                                                        ? "bg-primary/10 border-primary/40 text-primary shadow-sm"
                                                        : "bg-secondary/30 border-border/60 text-muted-foreground hover:border-primary/20 hover:bg-secondary/50"
                                                }`}
                                            >
                                                <Zap className="w-3 h-3" />
                                                {mode === "" ? "None" : mode === "fallback" ? "Fallback" : "Load Balance"}
                                            </button>
                                        ))}
                                    </div>
                                </Section>

                                {/* Timeout */}
                                <Section title="Request Timeout" icon={Clock} defaultOpen={!!builder.requestTimeout}>
                                    <div className="space-y-1">
                                        <label className="text-xs text-muted-foreground">Timeout in milliseconds</label>
                                        <Input
                                            value={builder.requestTimeout}
                                            onChange={(e) => updateBuilder({ requestTimeout: e.target.value })}
                                            placeholder="e.g., 30000"
                                            className="h-8 text-xs max-w-48"
                                        />
                                    </div>
                                </Section>

                                {/* Advanced / Custom JSON */}
                                <Section title="Advanced Settings" icon={Code} defaultOpen={!!builder.customMetadata}>
                                    <p className="text-xs text-muted-foreground">
                                        Additional config fields as JSON (merged into the final config)
                                    </p>
                                    <Textarea
                                        value={builder.customMetadata}
                                        onChange={(e) => updateBuilder({ customMetadata: e.target.value })}
                                        className="font-mono text-xs h-24 resize-none"
                                        spellCheck={false}
                                        placeholder='{"weight": 1, "custom_field": "value"}'
                                    />
                                </Section>
                                </div>

                                <div className="min-w-0 border border-border/40 rounded-lg bg-secondary/20 overflow-hidden flex flex-col">
                                    <div className="px-3 py-2 border-b border-border/40 bg-background/80">
                                        <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                                            <Code className="w-3 h-3" />
                                            Config JSON Preview
                                        </p>
                                        <p className="text-[11px] text-muted-foreground mt-1">
                                            Live JSON generated from the builder fields.
                                        </p>
                                    </div>
                                    <div className="flex-1 overflow-y-auto p-3">
                                        <pre className="text-[11px] font-mono text-foreground/80 whitespace-pre-wrap break-all">
                                            {JSON.stringify(builderToConfigBody(builder), null, 2)}
                                        </pre>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            /* ─── JSON EDITOR ─── */
                            <div className="space-y-1.5">
                                <p className="text-xs text-muted-foreground">
                                    Edit the raw config JSON directly. Switch to Builder view to use the visual editor.
                                </p>
                                <Textarea
                                    value={formConfigJson}
                                    onChange={(e) => setFormConfigJson(e.target.value)}
                                    className="font-mono text-xs h-[calc(90vh-20rem)] min-h-105 resize-none"
                                    spellCheck={false}
                                />
                            </div>
                        )}
                    </div>

                    {formError && (
                        <div className="p-2.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs flex items-start gap-2">
                            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                            <span>{formError}</span>
                        </div>
                    )}

                    <DialogFooter className="pt-3">
                        <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
                            Cancel
                        </Button>
                        <Button onClick={handleSave} disabled={saving}>
                            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            {dialogMode === "create" ? "Create" : "Update"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* View Dialog */}
            <Dialog open={viewOpen} onOpenChange={setViewOpen}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
                    <DialogHeader>
                        <DialogTitle>Config: {viewName}</DialogTitle>
                        <DialogDescription>Full config details retrieved from Portkey</DialogDescription>
                    </DialogHeader>
                    <div className="flex-1 overflow-y-auto py-2">
                        {viewLoading ? (
                            <div className="flex items-center justify-center py-12">
                                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : (
                            <pre className="text-xs font-mono bg-secondary/50 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap break-all">
                                {JSON.stringify(viewDetail, null, 2)}
                            </pre>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setViewOpen(false)}>Close</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirm Dialog */}
            <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Delete Config</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete this config? This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="pt-3">
                        <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)} disabled={!!actionLoading}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={handleDelete} disabled={!!actionLoading}>
                            {actionLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

// ═══════════════════════════════════════════════════════════════════════
// Guardrails Tab (read-only listing from Portkey cloud)
// ═══════════════════════════════════════════════════════════════════════

function GuardrailsTab() {
    const [guardrails, setGuardrails] = useState<PortkeyGuardrail[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState<string | null>(null);

    const fetchGuardrails = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await api.listConfigGuardrails();
            setGuardrails(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(humanError(err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchGuardrails(); }, [fetchGuardrails]);

    const copyId = (id: string) => {
        navigator.clipboard.writeText(id);
        setCopied(id);
        setTimeout(() => setCopied(null), 2000);
    };

    return (
        <>
            <div className="flex items-center justify-between mb-4">
                <div>
                    <p className="text-sm text-muted-foreground">
                        Cloud guardrails from Portkey — use their IDs when creating configs
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchGuardrails} disabled={loading}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            {error && (
                <div className="mb-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {loading && guardrails.length === 0 && (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
            )}

            {!loading && guardrails.length === 0 && !error && (
                <Card>
                    <CardContent className="flex flex-col items-center justify-center py-12">
                        <Shield className="w-12 h-12 text-muted-foreground/30 mb-4" />
                        <p className="text-sm font-medium text-muted-foreground">No guardrails found</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Create guardrails in the Policies page or directly on Portkey
                        </p>
                    </CardContent>
                </Card>
            )}

            {guardrails.length > 0 && (
                <div className="grid gap-3">
                    {guardrails.map((gr) => (
                        <Card key={gr.remote_id} className="group hover:border-primary/30 transition-colors">
                            <CardContent className="flex items-center justify-between py-4 px-5">
                                <div className="flex items-center gap-3 min-w-0">
                                    <Shield className="w-5 h-5 text-primary shrink-0" />
                                    <div className="min-w-0">
                                        <span className="font-medium text-sm">{gr.name || "Unnamed"}</span>
                                        <p className="text-xs text-muted-foreground mt-0.5 font-mono">
                                            {gr.remote_id}
                                        </p>
                                    </div>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => copyId(gr.remote_id)}
                                    title="Copy guardrail ID"
                                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                    {copied === gr.remote_id ? (
                                        <Check className="w-4 h-4 text-success" />
                                    ) : (
                                        <Copy className="w-4 h-4" />
                                    )}
                                </Button>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </>
    );
}

// ═══════════════════════════════════════════════════════════════════════
// Integrations Tab (read-only listing from Portkey cloud)
// ═══════════════════════════════════════════════════════════════════════

function IntegrationsTab() {
    const [integrations, setIntegrations] = useState<PortkeyIntegration[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState<string | null>(null);

    const fetchIntegrations = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await api.listIntegrations();
            setIntegrations(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(humanError(err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchIntegrations(); }, [fetchIntegrations]);

    const copySlug = (slug: string) => {
        navigator.clipboard.writeText(slug);
        setCopied(slug);
        setTimeout(() => setCopied(null), 2000);
    };

    return (
        <>
            <div className="flex items-center justify-between mb-4">
                <div>
                    <p className="text-sm text-muted-foreground">
                        LLM integrations from Portkey — use their slugs as virtual keys in configs
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchIntegrations} disabled={loading}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            {error && (
                <div className="mb-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {loading && integrations.length === 0 && (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
            )}

            {!loading && integrations.length === 0 && !error && (
                <Card>
                    <CardContent className="flex flex-col items-center justify-center py-12">
                        <Plug className="w-12 h-12 text-muted-foreground/30 mb-4" />
                        <p className="text-sm font-medium text-muted-foreground">No integrations found</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Add LLM integrations on your Portkey dashboard
                        </p>
                    </CardContent>
                </Card>
            )}

            {integrations.length > 0 && (
                <div className="grid gap-3">
                    {integrations.map((intg) => (
                        <Card key={intg.id} className="group hover:border-primary/30 transition-colors">
                            <CardContent className="flex items-center justify-between py-4 px-5">
                                <div className="flex items-center gap-3 min-w-0">
                                    <Plug className="w-5 h-5 text-primary shrink-0" />
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium text-sm">{intg.name}</span>
                                            <Badge variant={intg.status === "active" ? "success" : "secondary"} className="text-[10px]">
                                                {intg.status}
                                            </Badge>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-0.5">
                                            <span className="font-mono">{intg.slug}</span>
                                            <span className="mx-1.5">·</span>
                                            <span>{intg.ai_provider_id}</span>
                                            {intg.created_at && (
                                                <>
                                                    <span className="mx-1.5">·</span>
                                                    <span>Created {new Date(intg.created_at).toLocaleDateString()}</span>
                                                </>
                                            )}
                                        </p>
                                    </div>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => copySlug(intg.slug)}
                                    title="Copy integration slug"
                                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                    {copied === intg.slug ? (
                                        <Check className="w-4 h-4 text-success" />
                                    ) : (
                                        <Copy className="w-4 h-4" />
                                    )}
                                </Button>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </>
    );
}

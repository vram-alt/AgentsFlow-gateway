"use client";

import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
    Zap,
    Plus,
    Pencil,
    Trash2,
    RefreshCw,
    Loader2,
    Server,
    Globe,
    Key,
    AlertTriangle,
    Power,
    Cloud,
    HardDrive,
    Info,
    Lightbulb,
} from "lucide-react";
import { api, type Provider, type ProviderCreateRequest } from "@/lib/api-client";

type ConnectionType = "cloud" | "selfhosted";

export default function ProvidersPage() {
    const [providers, setProviders] = useState<Provider[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
    const [connectionType, setConnectionType] = useState<ConnectionType>("cloud");
    const [formData, setFormData] = useState({
        name: "",
        portkey_api_key: "",
        vk_google: "",
        vk_openai: "",
        vk_anthropic: "",
        provider_api_key: "",
        base_url: "",
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchProviders = async () => {
        setLoading(true);
        try {
            const data = await api.listProviders();
            setProviders(Array.isArray(data) ? data : []);
        } catch {
            setProviders([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProviders();
    }, []);

    const openCreate = () => {
        setEditingProvider(null);
        setConnectionType("cloud");
        setFormData({
            name: "portkey",
            portkey_api_key: "",
            vk_google: "",
            vk_openai: "",
            vk_anthropic: "",
            provider_api_key: "",
            base_url: "https://api.portkey.ai/v1",
        });
        setError(null);
        setDialogOpen(true);
    };

    const openEdit = (provider: Provider) => {
        setEditingProvider(provider);
        // Detect connection type from existing api_key
        const hasVirtualKey = provider.api_key?.includes("::");
        const isCloud = provider.base_url?.includes("portkey.ai");

        if (isCloud || hasVirtualKey) {
            setConnectionType("cloud");
            const parts = (provider.api_key || "").split("::");
            const vkPart = parts[1] || "";
            let vkGoogle = "", vkOpenai = "", vkAnthropic = "";
            if (vkPart.includes("=")) {
                for (const pair of vkPart.split(",")) {
                    const [k, v] = pair.split("=", 2);
                    if (k?.trim() === "google") vkGoogle = v?.trim() || "";
                    if (k?.trim() === "openai") vkOpenai = v?.trim() || "";
                    if (k?.trim() === "anthropic") vkAnthropic = v?.trim() || "";
                }
            }
            setFormData({
                name: "portkey",
                portkey_api_key: "",
                vk_google: vkGoogle,
                vk_openai: vkOpenai,
                vk_anthropic: vkAnthropic,
                provider_api_key: "",
                base_url: provider.base_url,
            });
        } else {
            setConnectionType("selfhosted");
            setFormData({
                name: "portkey",
                portkey_api_key: "",
                vk_google: "",
                vk_openai: "",
                vk_anthropic: "",
                provider_api_key: "",
                base_url: provider.base_url,
            });
        }
        setError(null);
        setDialogOpen(true);
    };

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            let finalApiKey: string;
            let finalBaseUrl: string;

            if (connectionType === "cloud") {
                // Cloud mode: combine portkey_api_key and virtual keys per LLM provider
                if (!editingProvider && !formData.portkey_api_key) {
                    setError("Portkey API Key is required");
                    setSaving(false);
                    return;
                }
                finalApiKey = formData.portkey_api_key;
                const vkParts: string[] = [];
                if (formData.vk_google.trim()) vkParts.push(`google=${formData.vk_google.trim()}`);
                if (formData.vk_openai.trim()) vkParts.push(`openai=${formData.vk_openai.trim()}`);
                if (formData.vk_anthropic.trim()) vkParts.push(`anthropic=${formData.vk_anthropic.trim()}`);
                if (vkParts.length > 0) {
                    finalApiKey = `${formData.portkey_api_key}::${vkParts.join(",")}`;
                }
                finalBaseUrl = formData.base_url || "https://api.portkey.ai/v1";
            } else {
                // Self-hosted mode: use provider API key directly
                if (!editingProvider && !formData.provider_api_key) {
                    setError("Provider API Key is required");
                    setSaving(false);
                    return;
                }
                finalApiKey = formData.provider_api_key;
                finalBaseUrl = formData.base_url || "http://localhost:8787/v1";
            }

            if (editingProvider) {
                await api.updateProvider(editingProvider.id, {
                    name: "portkey",
                    api_key: finalApiKey || null,
                    base_url: finalBaseUrl || null,
                });
            } else {
                await api.createProvider({
                    name: "portkey",
                    api_key: finalApiKey,
                    base_url: finalBaseUrl,
                });
            }
            setDialogOpen(false);
            fetchProviders();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to save");
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await api.deleteProvider(id);
            setDeleteConfirm(null);
            setProviders((prev) => prev.filter((p) => p.id !== id));
        } catch {
            // silently fail
        }
    };

    const handleToggle = async (id: number) => {
        try {
            await api.toggleProvider(id);
            fetchProviders();
        } catch {
            // silently fail
        }
    };

    /** Detect if a provider uses cloud or self-hosted mode */
    const getProviderType = (provider: Provider): "cloud" | "selfhosted" => {
        if (provider.base_url?.includes("portkey.ai")) return "cloud";
        if (provider.api_key?.includes("::")) return "cloud";
        return "selfhosted";
    };

    /** Extract virtual key info from api_key if present */
    const getVirtualKeys = (provider: Provider): Record<string, string> => {
        if (!provider.api_key?.includes("::")) return {};
        const vkPart = provider.api_key.split("::")[1] || "";
        if (vkPart.includes("=")) {
            const result: Record<string, string> = {};
            for (const pair of vkPart.split(",")) {
                const [k, v] = pair.split("=", 2);
                if (k && v) result[k.trim()] = v.trim();
            }
            return result;
        }
        return { _default: vkPart };
    };

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Providers</h1>
                    <p className="text-muted-foreground">Manage LLM provider connections</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchProviders} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={openCreate}>
                        <Plus className="w-4 h-4 mr-2" />
                        Add Provider
                    </Button>
                </div>
            </div>

            {/* Provider Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {loading && (
                    <div className="col-span-full flex justify-center py-12">
                        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                    </div>
                )}
                {!loading && providers.length === 0 && (
                    <div className="col-span-full text-center py-12">
                        <Server className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-30" />
                        <p className="text-muted-foreground">No providers configured</p>
                        <Button size="sm" className="mt-4" onClick={openCreate}>
                            <Plus className="w-4 h-4 mr-2" />
                            Add your first provider
                        </Button>
                    </div>
                )}
                {!loading &&
                    providers.map((provider) => {
                        const provType = getProviderType(provider);
                        const vks = getVirtualKeys(provider);
                        return (
                            <Card
                                key={provider.id}
                                className={`transition-colors group ${provider.is_active
                                        ? "hover:border-primary/30"
                                        : "opacity-60 border-dashed"
                                    }`}
                            >
                                <CardHeader className="pb-3">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className={`p-2 rounded-lg ${provider.is_active ? "bg-primary/10" : "bg-muted"}`}>
                                                <Zap className={`w-5 h-5 ${provider.is_active ? "text-primary" : "text-muted-foreground"}`} />
                                            </div>
                                            <div>
                                                <CardTitle className={`text-base ${!provider.is_active ? "text-muted-foreground" : ""}`}>
                                                    {provider.name}
                                                </CardTitle>
                                                <div className="flex items-center gap-1.5 mt-1">
                                                    <Badge
                                                        variant={provider.is_active ? "success" : "secondary"}
                                                    >
                                                        {provider.is_active ? "Active" : "Inactive"}
                                                    </Badge>
                                                    <Badge variant="outline" className="text-[10px]">
                                                        {provType === "cloud" ? (
                                                            <><Cloud className="w-3 h-3 mr-1" />Cloud</>
                                                        ) : (
                                                            <><HardDrive className="w-3 h-3 mr-1" />Self-hosted</>
                                                        )}
                                                    </Badge>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex gap-1">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className={`h-8 w-8 ${provider.is_active
                                                        ? "text-green-600 hover:text-red-600"
                                                        : "text-muted-foreground hover:text-green-600"
                                                    }`}
                                                onClick={() => handleToggle(provider.id)}
                                                title={provider.is_active ? "Deactivate provider" : "Activate provider"}
                                            >
                                                <Power className="w-4 h-4" />
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                                                onClick={() => openEdit(provider)}
                                            >
                                                <Pencil className="w-3.5 h-3.5" />
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                                                onClick={() => setDeleteConfirm(provider.id)}
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </Button>
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                        <Globe className="w-3.5 h-3.5" />
                                        <span className="truncate">{provider.base_url}</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                        <Key className="w-3.5 h-3.5" />
                                        <span>••••••••{provider.api_key?.split("::")[0]?.slice(-4) || "••••"}</span>
                                    </div>
                                    {Object.keys(vks).length > 0 && (
                                        <div className="space-y-1">
                                            {Object.entries(vks).map(([prov, slug]) => (
                                                <div key={prov} className="flex items-center gap-2 text-sm text-muted-foreground">
                                                    <Cloud className="w-3.5 h-3.5" />
                                                    <span>
                                                        {prov === "_default" ? "Virtual Key" : prov}:{" "}
                                                        <code className="text-xs bg-secondary px-1 py-0.5 rounded">{slug}</code>
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    <div className="text-xs text-muted-foreground pt-2">
                                        Created {new Date(provider.created_at).toLocaleDateString()}
                                    </div>
                                </CardContent>
                            </Card>
                        );
                    })}
            </div>

            {/* Create/Edit Dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>
                            {editingProvider ? "Edit Provider" : "Add Provider"}
                        </DialogTitle>
                        <DialogDescription>
                            {editingProvider
                                ? "Update the provider configuration"
                                : "Configure a new LLM provider connection"}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        {error && (
                            <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
                                <AlertTriangle className="w-4 h-4" />
                                {error}
                            </div>
                        )}

                        {/* Connection Type Selector */}
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Connection Type</label>
                            <div className="grid grid-cols-2 gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setConnectionType("cloud");
                                        setFormData(prev => ({
                                            ...prev,
                                            base_url: "https://api.portkey.ai/v1",
                                        }));
                                    }}
                                    className={`flex items-center gap-2 p-3 rounded-lg border text-left transition-colors cursor-pointer ${connectionType === "cloud"
                                            ? "border-primary bg-primary/5 text-primary"
                                            : "border-border hover:border-primary/30"
                                        }`}
                                >
                                    <Cloud className="w-5 h-5 shrink-0" />
                                    <div>
                                        <div className="text-sm font-medium">Portkey Cloud</div>
                                        <div className="text-[10px] text-muted-foreground">SaaS — api.portkey.ai</div>
                                    </div>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setConnectionType("selfhosted");
                                        setFormData(prev => ({
                                            ...prev,
                                            base_url: prev.base_url === "https://api.portkey.ai/v1"
                                                ? "http://localhost:8787/v1"
                                                : prev.base_url,
                                        }));
                                    }}
                                    className={`flex items-center gap-2 p-3 rounded-lg border text-left transition-colors cursor-pointer ${connectionType === "selfhosted"
                                            ? "border-primary bg-primary/5 text-primary"
                                            : "border-border hover:border-primary/30"
                                        }`}
                                >
                                    <HardDrive className="w-5 h-5 shrink-0" />
                                    <div>
                                        <div className="text-sm font-medium">Self-hosted</div>
                                        <div className="text-[10px] text-muted-foreground">Docker / Local gateway</div>
                                    </div>
                                </button>
                            </div>
                        </div>

                        {/* Name */}
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Name</label>
                            <Input
                                value="portkey"
                                readOnly
                                className="bg-muted"
                            />
                            <p className="text-[11px] text-muted-foreground">
                                The provider name is fixed to <code className="bg-secondary px-1 rounded">portkey</code>.
                            </p>
                        </div>

                        {/* Cloud Mode Fields */}
                        {connectionType === "cloud" && (
                            <>
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Portkey API Key</label>
                                    <Input
                                        type="password"
                                        value={formData.portkey_api_key}
                                        onChange={(e) => setFormData({ ...formData, portkey_api_key: e.target.value })}
                                        placeholder={editingProvider ? "Leave empty to keep current" : "Your Portkey API key"}
                                    />
                                    <p className="text-[11px] text-muted-foreground flex items-start gap-1">
                                        <Info className="w-3 h-3 mt-0.5 shrink-0" />
                                        Found in your Portkey dashboard under API Keys.
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Virtual Key Slugs</label>
                                    <p className="text-[11px] text-muted-foreground flex items-start gap-1">
                                        <Info className="w-3 h-3 mt-0.5 shrink-0" />
                                        Enter the slug for each LLM provider from your Portkey AI Providers dashboard.
                                    </p>
                                    <div className="grid gap-2">
                                        <div className="flex items-center gap-2">
                                            <label className="text-xs text-muted-foreground w-20 shrink-0">Google</label>
                                            <Input
                                                value={formData.vk_google}
                                                onChange={(e) => setFormData({ ...formData, vk_google: e.target.value })}
                                                placeholder="e.g. dev"
                                                className="h-8 text-sm"
                                            />
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <label className="text-xs text-muted-foreground w-20 shrink-0">OpenAI</label>
                                            <Input
                                                value={formData.vk_openai}
                                                onChange={(e) => setFormData({ ...formData, vk_openai: e.target.value })}
                                                placeholder="e.g. dev-openai"
                                                className="h-8 text-sm"
                                            />
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <label className="text-xs text-muted-foreground w-20 shrink-0">Anthropic</label>
                                            <Input
                                                value={formData.vk_anthropic}
                                                onChange={(e) => setFormData({ ...formData, vk_anthropic: e.target.value })}
                                                placeholder="e.g. dev-anthropic"
                                                className="h-8 text-sm"
                                            />
                                        </div>
                                    </div>
                                </div>
                            </>
                        )}

                        {/* Self-hosted Mode Fields */}
                        {connectionType === "selfhosted" && (
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Provider API Key</label>
                                <Input
                                    type="password"
                                    value={formData.provider_api_key}
                                    onChange={(e) => setFormData({ ...formData, provider_api_key: e.target.value })}
                                    placeholder={editingProvider ? "Leave empty to keep current" : "Direct LLM provider API key"}
                                />
                                <p className="text-[11px] text-muted-foreground flex items-start gap-1">
                                    <Info className="w-3 h-3 mt-0.5 shrink-0" />
                                    The actual API key for your LLM provider (e.g. OpenAI, Google). Virtual keys are not needed for self-hosted Portkey Gateway.
                                </p>
                            </div>
                        )}

                        {/* Base URL */}
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Base URL</label>
                            <Input
                                value={formData.base_url}
                                onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                                placeholder={connectionType === "cloud" ? "https://api.portkey.ai/v1" : "http://localhost:8787/v1"}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSave} disabled={saving}>
                            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            {editingProvider ? "Update" : "Create"}
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
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div className="flex items-start gap-2">
                        <Cloud className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p>Portkey Cloud requires a Portkey API Key and a Virtual Key slug from your Portkey dashboard.</p>
                    </div>
                    <div className="flex items-start gap-2">
                        <HardDrive className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p>Self-hosted mode uses the LLM provider API key directly (no Virtual Key needed).</p>
                    </div>
                    <div className="flex items-start gap-2">
                        <Power className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p>Toggle the power icon to activate or deactivate a provider without deleting it.</p>
                    </div>
                    <div className="flex items-start gap-2">
                        <Key className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p>The provider name is used in Sandbox to select which LLM service to route requests through.</p>
                    </div>
                </div>
            </div>

            {/* Delete Confirmation */}
            <Dialog open={deleteConfirm !== null} onOpenChange={() => setDeleteConfirm(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Provider</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete this provider? This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => deleteConfirm !== null && handleDelete(deleteConfirm)}
                        >
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

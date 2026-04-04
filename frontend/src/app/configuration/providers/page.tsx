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
} from "lucide-react";
import { api, type Provider, type ProviderCreateRequest } from "@/lib/api-client";

export default function ProvidersPage() {
    const [providers, setProviders] = useState<Provider[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
    const [formData, setFormData] = useState({ name: "", api_key: "", base_url: "" });
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
        setFormData({ name: "", api_key: "", base_url: "" });
        setError(null);
        setDialogOpen(true);
    };

    const openEdit = (provider: Provider) => {
        setEditingProvider(provider);
        setFormData({
            name: provider.name,
            api_key: "",
            base_url: provider.base_url,
        });
        setError(null);
        setDialogOpen(true);
    };

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            if (editingProvider) {
                await api.updateProvider(editingProvider.id, {
                    name: formData.name || null,
                    api_key: formData.api_key || null,
                    base_url: formData.base_url || null,
                });
            } else {
                await api.createProvider({
                    name: formData.name,
                    api_key: formData.api_key,
                    base_url: formData.base_url,
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
            fetchProviders();
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
                    providers.map((provider) => (
                        <Card
                            key={provider.id}
                            className={`transition-colors group ${
                                provider.is_active
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
                                            <Badge
                                                variant={provider.is_active ? "success" : "secondary"}
                                                className="mt-1"
                                            >
                                                {provider.is_active ? "Active" : "Inactive"}
                                            </Badge>
                                        </div>
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className={`h-8 w-8 ${
                                                provider.is_active
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
                                    <span>••••••••{provider.api_key?.slice(-4) || "••••"}</span>
                                </div>
                                <div className="text-xs text-muted-foreground pt-2">
                                    Created {new Date(provider.created_at).toLocaleDateString()}
                                </div>
                            </CardContent>
                        </Card>
                    ))}
            </div>

            {/* Create/Edit Dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent>
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
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Name</label>
                            <Input
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                placeholder="e.g. portkey"
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">API Key</label>
                            <Input
                                type="password"
                                value={formData.api_key}
                                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                                placeholder={editingProvider ? "Leave empty to keep current" : "sk-..."}
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Base URL</label>
                            <Input
                                value={formData.base_url}
                                onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                                placeholder="https://api.portkey.ai/v1"
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

"use client";

import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    FileJson,
} from "lucide-react";
import { api, type Policy } from "@/lib/api-client";

export default function PoliciesPage() {
    const [policies, setPolicies] = useState<Policy[]>([]);
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

    const fetchPolicies = async () => {
        setLoading(true);
        try {
            const data = await api.listPolicies();
            setPolicies(Array.isArray(data) ? data : []);
        } catch {
            setPolicies([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPolicies();
    }, []);

    const openCreate = () => {
        setEditingPolicy(null);
        setFormData({ name: "", body: "{}", provider_name: "portkey" });
        setError(null);
        setDialogOpen(true);
    };

    const openEdit = (policy: Policy) => {
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
        try {
            await api.deletePolicy(id);
            setDeleteConfirm(null);
            fetchPolicies();
        } catch {
            // silently fail
        }
    };

    const handleSync = async () => {
        setSyncLoading(true);
        try {
            await api.syncPolicies("portkey");
            fetchPolicies();
        } catch {
            // silently fail
        } finally {
            setSyncLoading(false);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Policies</h1>
                    <p className="text-muted-foreground">Manage guardrail and security policies</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={handleSync} disabled={syncLoading}>
                        {syncLoading ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <CloudDownload className="w-4 h-4 mr-2" />
                        )}
                        Sync from Cloud
                    </Button>
                    <Button variant="outline" size="sm" onClick={fetchPolicies} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={openCreate}>
                        <Plus className="w-4 h-4 mr-2" />
                        Add Policy
                    </Button>
                </div>
            </div>

            {/* Policies Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {loading && (
                    <div className="col-span-full flex justify-center py-12">
                        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                    </div>
                )}
                {!loading && policies.length === 0 && (
                    <div className="col-span-full text-center py-12">
                        <Shield className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-30" />
                        <p className="text-muted-foreground">No policies configured</p>
                        <div className="flex gap-2 justify-center mt-4">
                            <Button size="sm" onClick={openCreate}>
                                <Plus className="w-4 h-4 mr-2" />
                                Create policy
                            </Button>
                            <Button size="sm" variant="outline" onClick={handleSync}>
                                <CloudDownload className="w-4 h-4 mr-2" />
                                Sync from cloud
                            </Button>
                        </div>
                    </div>
                )}
                {!loading &&
                    policies.map((policy) => (
                        <Card
                            key={policy.id}
                            className="hover:border-primary/30 transition-colors group"
                        >
                            <CardHeader className="pb-3">
                                <div className="flex items-start justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 rounded-lg bg-accent/10">
                                            <Shield className="w-5 h-5 text-accent" />
                                        </div>
                                        <div>
                                            <CardTitle className="text-base">{policy.name}</CardTitle>
                                            <div className="flex gap-1 mt-1">
                                                <Badge
                                                    variant={policy.is_active ? "success" : "secondary"}
                                                >
                                                    {policy.is_active ? "Active" : "Inactive"}
                                                </Badge>
                                                <Badge variant="outline" className="text-xs">
                                                    {policy.provider_name}
                                                </Badge>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-8 w-8"
                                            onClick={() => openEdit(policy)}
                                        >
                                            <Pencil className="w-3.5 h-3.5" />
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-8 w-8 text-destructive"
                                            onClick={() => setDeleteConfirm(policy.id)}
                                        >
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </Button>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                                    <FileJson className="w-3.5 h-3.5" />
                                    <span>{Object.keys(policy.body).length} rules</span>
                                </div>
                                <pre className="p-2 rounded bg-secondary text-xs font-mono overflow-hidden max-h-20 text-muted-foreground">
                                    {JSON.stringify(policy.body, null, 2)}
                                </pre>
                                <div className="text-xs text-muted-foreground pt-2">
                                    Updated {new Date(policy.updated_at).toLocaleDateString()}
                                </div>
                            </CardContent>
                        </Card>
                    ))}
            </div>

            {/* Create/Edit Dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>
                            {editingPolicy ? "Edit Policy" : "Create Policy"}
                        </DialogTitle>
                        <DialogDescription>
                            {editingPolicy
                                ? "Update the policy configuration"
                                : "Define a new guardrail policy"}
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
                                    <option value="portkey">Portkey</option>
                                </Select>
                            </div>
                        )}
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Policy Body (JSON)</label>
                            <Textarea
                                value={formData.body}
                                onChange={(e) => setFormData({ ...formData, body: e.target.value })}
                                className="font-mono text-xs h-48"
                                placeholder='{"rules": [...]}'
                            />
                        </div>
                    </div>
                    <DialogFooter>
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
                        >
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

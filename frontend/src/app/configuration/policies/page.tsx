"use client";

import React, { useEffect, useState } from "react";
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
} from "lucide-react";
import { api, ApiError, type Policy } from "@/lib/api-client";

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
    const [pageError, setPageError] = useState<string | null>(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);

    const fetchPolicies = async () => {
        setLoading(true);
        setPageError(null);
        try {
            const data = await api.listPolicies();
            setPolicies(Array.isArray(data) ? data : []);
        } catch (err: unknown) {
            setPolicies([]);
            setPageError(humanError(err));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPolicies();
    }, []);

    const openCreate = () => {
        setEditingPolicy(null);
        setFormData({ name: "", body: '{\n  "checks": [],\n  "actions": [\n    {\n      "type": "block",\n      "message": "Request blocked by guardrail"\n    }\n  ]\n}', provider_name: "portkey" });
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
        setDeleteLoading(true);
        setPageError(null);
        try {
            await api.deletePolicy(id);
            setDeleteConfirm(null);
            fetchPolicies();
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
            await api.togglePolicy(id);
            fetchPolicies();
        } catch (err: unknown) {
            setPageError(`Failed to toggle policy: ${humanError(err)}`);
        }
    };

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
                                {!loading && policies.length === 0 && (
                                    <tr>
                                        <td colSpan={6} className="p-8 text-center text-muted-foreground">
                                            <Shield className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                            <p>No policies configured</p>
                                            <Button size="sm" className="mt-3" onClick={openCreate}>
                                                <Plus className="w-4 h-4 mr-2" />
                                                Create policy
                                            </Button>
                                        </td>
                                    </tr>
                                )}
                                {!loading &&
                                    policies.map((policy) => (
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
                                                <Badge variant="outline" className="text-xs">
                                                    {policy.provider_name}
                                                </Badge>
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
                                placeholder='{"checks": [...], "actions": [{"type": "block", "message": "Blocked"}]}'
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
                                <pre className="mt-2 p-5 rounded-lg bg-secondary text-xs font-mono overflow-auto max-h-[50vh] leading-relaxed whitespace-pre-wrap break-words">
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

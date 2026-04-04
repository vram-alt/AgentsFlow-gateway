"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
    Activity,
    RefreshCw,
    Download,
    Search,
    ChevronLeft,
    ChevronRight,
    Play,
    Eye,
    X,
    Loader2,
    FileText,
    AlertTriangle,
} from "lucide-react";
import { api, ApiError, type LogEntry } from "@/lib/api-client";

const EVENT_TYPES = [
    { value: "", label: "All Events" },
    { value: "chat_request", label: "Chat Request" },
    { value: "chat_response", label: "Chat Response" },
    { value: "chat_error", label: "Chat Error" },
    { value: "policy_violation", label: "Policy Violation" },
    { value: "webhook_received", label: "Webhook" },
];

const eventTypeColor: Record<string, string> = {
    chat_request: "bg-accent/20 text-accent",
    chat_response: "bg-success/20 text-success",
    chat_error: "bg-destructive/20 text-destructive",
    policy_violation: "bg-warning/20 text-warning",
    webhook_received: "bg-primary/20 text-primary",
};

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

export default function ObservabilityPage() {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [page, setPage] = useState(0);
    const [eventType, setEventType] = useState("");
    const [traceIdFilter, setTraceIdFilter] = useState("");
    const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
    const [replayLoading, setReplayLoading] = useState<number | null>(null);
    const [replayError, setReplayError] = useState<string | null>(null);
    const pageSize = 8;

    const fetchLogs = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await api.getLogs({
                limit: pageSize,
                offset: page * pageSize,
                event_type: eventType || undefined,
                trace_id: traceIdFilter || undefined,
            });
            setLogs(Array.isArray(data) ? data : []);
        } catch (err: unknown) {
            setLogs([]);
            setError(humanError(err));
        } finally {
            setLoading(false);
        }
    }, [page, eventType, traceIdFilter]);

    useEffect(() => {
        fetchLogs();
    }, [fetchLogs]);

    const handleReplay = async (logId: number) => {
        setReplayLoading(logId);
        setReplayError(null);
        try {
            await api.replayLog(logId);
        } catch (err: unknown) {
            setReplayError(humanError(err));
        } finally {
            setReplayLoading(null);
        }
    };

    const [exportLoading, setExportLoading] = useState(false);

    const handleExport = async () => {
        setExportLoading(true);
        setError(null);
        try {
            await api.downloadExportCsv({ event_type: eventType || undefined });
        } catch (err: unknown) {
            setError(humanError(err));
        } finally {
            setExportLoading(false);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Observability</h1>
                    <p className="text-muted-foreground">Request logs and event tracing</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={handleExport} disabled={exportLoading}>
                        {exportLoading ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Download className="w-4 h-4 mr-2" />
                        )}
                        Export CSV
                    </Button>
                    <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                        Refresh
                    </Button>
                </div>
            </div>

            {/* Error Banner */}
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-lg border border-destructive/50 bg-destructive/10 text-destructive">
                    <AlertTriangle className="w-5 h-5 shrink-0" />
                    <p className="text-sm font-medium">{error}</p>
                    <button
                        onClick={() => setError(null)}
                        className="ml-auto p-1 rounded hover:bg-destructive/20 cursor-pointer"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}

            {/* Replay Error Banner */}
            {replayError && (
                <div className="flex items-center gap-3 p-4 rounded-lg border border-warning/50 bg-warning/10 text-warning">
                    <AlertTriangle className="w-5 h-5 shrink-0" />
                    <p className="text-sm font-medium">Replay failed: {replayError}</p>
                    <button
                        onClick={() => setReplayError(null)}
                        className="ml-auto p-1 rounded hover:bg-warning/20 cursor-pointer"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}

            {/* Filters */}
            <Card>
                <CardContent className="p-4">
                    <div className="flex flex-wrap gap-3">
                        <div className="flex-1 min-w-[200px]">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                <Input
                                    placeholder="Filter by trace ID..."
                                    value={traceIdFilter}
                                    onChange={(e) => {
                                        setTraceIdFilter(e.target.value);
                                        setPage(0);
                                    }}
                                    className="pl-9"
                                />
                            </div>
                        </div>
                        <Select
                            value={eventType}
                            onChange={(e) => {
                                setEventType(e.target.value);
                                setPage(0);
                            }}
                            className="w-48"
                        >
                            {EVENT_TYPES.map((t) => (
                                <option key={t.value} value={t.value}>
                                    {t.label}
                                </option>
                            ))}
                        </Select>
                    </div>
                </CardContent>
            </Card>

            {/* Logs Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border">
                                    <th className="text-left p-4 text-muted-foreground font-medium">ID</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Event Type</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Trace ID</th>
                                    <th className="text-left p-4 text-muted-foreground font-medium">Timestamp</th>
                                    <th className="text-right p-4 text-muted-foreground font-medium">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading && (
                                    <tr>
                                        <td colSpan={5} className="p-8 text-center">
                                            <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
                                        </td>
                                    </tr>
                                )}
                                {!loading && logs.length === 0 && (
                                    <tr>
                                        <td colSpan={5} className="p-8 text-center text-muted-foreground">
                                            <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                            No logs found
                                        </td>
                                    </tr>
                                )}
                                {!loading &&
                                    logs.map((log) => (
                                        <tr
                                            key={log.id}
                                            className="border-b border-border/50 hover:bg-secondary/30 transition-colors"
                                        >
                                            <td className="p-4 font-mono text-xs">{log.id}</td>
                                            <td className="p-4">
                                                <span
                                                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${eventTypeColor[log.event_type] || "bg-secondary text-foreground"
                                                        }`}
                                                >
                                                    {log.event_type}
                                                </span>
                                            </td>
                                            <td className="p-4">
                                                <code className="text-xs font-mono text-muted-foreground">
                                                    {log.trace_id?.slice(0, 12)}...
                                                </code>
                                            </td>
                                            <td className="p-4 text-xs text-muted-foreground">
                                                {new Date(log.created_at).toLocaleString()}
                                            </td>
                                            <td className="p-4 text-right">
                                                <div className="flex items-center justify-end gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => setSelectedLog(log)}
                                                        title="View details"
                                                    >
                                                        <Eye className="w-3.5 h-3.5" />
                                                    </Button>
                                                    {log.event_type === "chat_request" && (
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8"
                                                            onClick={() => handleReplay(log.id)}
                                                            disabled={replayLoading === log.id}
                                                            title="Replay"
                                                        >
                                                            {replayLoading === log.id ? (
                                                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                            ) : (
                                                                <Play className="w-3.5 h-3.5" />
                                                            )}
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    <div className="flex items-center justify-between p-4 border-t border-border">
                        <span className="text-xs text-muted-foreground">
                            Page {page + 1} · {logs.length} results
                        </span>
                        <div className="flex gap-1">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setPage((p) => Math.max(0, p - 1))}
                                disabled={page === 0}
                            >
                                <ChevronLeft className="w-4 h-4" />
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setPage((p) => p + 1)}
                                disabled={logs.length < pageSize}
                            >
                                <ChevronRight className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Detail Modal */}
            {selectedLog && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
                    <div className="bg-card border border-border rounded-xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
                        <div className="flex items-center justify-between p-4 border-b border-border">
                            <h3 className="font-semibold">Log Entry #{selectedLog.id}</h3>
                            <button
                                onClick={() => setSelectedLog(null)}
                                className="p-1 rounded hover:bg-secondary cursor-pointer"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <div className="p-4 overflow-y-auto max-h-[calc(80vh-4rem)] space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs text-muted-foreground">Event Type</label>
                                    <p className="text-sm font-medium">{selectedLog.event_type}</p>
                                </div>
                                <div>
                                    <label className="text-xs text-muted-foreground">Trace ID</label>
                                    <p className="text-sm font-mono">{selectedLog.trace_id}</p>
                                </div>
                                <div>
                                    <label className="text-xs text-muted-foreground">Created At</label>
                                    <p className="text-sm">{new Date(selectedLog.created_at).toLocaleString()}</p>
                                </div>
                            </div>
                            <div>
                                <label className="text-xs text-muted-foreground">Payload</label>
                                <pre className="mt-1 p-4 rounded-lg bg-secondary text-xs font-mono overflow-auto max-h-96">
                                    {JSON.stringify(selectedLog.payload, null, 2)}
                                </pre>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

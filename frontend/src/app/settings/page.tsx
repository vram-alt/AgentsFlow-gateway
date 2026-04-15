"use client";

import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Heart,
    RefreshCw,
    Server,
    CheckCircle2,
    XCircle,
    Loader2,
    Info,
    FlaskConical,
    ExternalLink,
    MessageSquare,
    Shield,
    Plug,
    BarChart3,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api-client";

export default function SettingsPage() {
    const [healthStatus, setHealthStatus] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [demoMode, setDemoMode] = useState<boolean | null>(null);
    const [demoLoading, setDemoLoading] = useState(false);
    const [demoMessage, setDemoMessage] = useState<string | null>(null);

    const checkHealth = async () => {
        setLoading(true);
        try {
            const data = await api.health();
            setHealthStatus(data.status);
        } catch {
            setHealthStatus("error");
        } finally {
            setLoading(false);
        }
    };

    const fetchDemoMode = async () => {
        try {
            const data = await api.getDemoMode();
            setDemoMode(data.enabled);
        } catch {
            setDemoMode(null);
        }
    };

    const toggleDemoMode = async () => {
        if (demoMode === null) return;
        setDemoLoading(true);
        setDemoMessage(null);
        try {
            const newValue = !demoMode;
            const data = await api.setDemoMode(newValue);
            setDemoMode(data.enabled);
            setDemoMessage(
                newValue
                    ? "Demo mode enabled — chat will return simulated responses"
                    : "Demo mode disabled — chat requires a valid LLM API key"
            );
            setTimeout(() => setDemoMessage(null), 5000);
        } catch (err) {
            setDemoMessage(
                err instanceof Error ? err.message : "Failed to update demo mode"
            );
        } finally {
            setDemoLoading(false);
        }
    };

    useEffect(() => {
        checkHealth();
        fetchDemoMode();
    }, []);

    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
                <p className="text-muted-foreground">System configuration and health</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Gateway Health */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <Heart className="w-4 h-4 text-primary" />
                            Gateway Health
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center justify-between p-4 rounded-lg bg-secondary/50">
                            <div className="flex items-center gap-3">
                                <Server className="w-5 h-5 text-muted-foreground" />
                                <div>
                                    <p className="text-sm font-medium">Backend API</p>
                                    <p className="text-xs text-muted-foreground">
                                        {process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                {healthStatus === "ok" && (
                                    <>
                                        <CheckCircle2 className="w-4 h-4 text-success" />
                                        <Badge variant="success">Healthy</Badge>
                                    </>
                                )}
                                {healthStatus === "error" && (
                                    <>
                                        <XCircle className="w-4 h-4 text-destructive" />
                                        <Badge variant="destructive">Unreachable</Badge>
                                    </>
                                )}
                                {healthStatus === null && (
                                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                                )}
                            </div>
                        </div>
                        <Button variant="outline" size="sm" onClick={checkHealth} disabled={loading}>
                            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                            Check Health
                        </Button>
                    </CardContent>
                </Card>

                {/* Demo Mode */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <FlaskConical className="w-4 h-4 text-accent" />
                            Demo Mode
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <p className="text-sm text-muted-foreground">
                            When enabled, the chat API returns simulated responses without
                            requiring a real LLM API key. Useful for testing and demos.
                        </p>
                        <div className="flex items-center justify-between p-4 rounded-lg bg-secondary/50">
                            <div className="flex items-center gap-3">
                                <div>
                                    <p className="text-sm font-medium">Demo Mode</p>
                                    <p className="text-xs text-muted-foreground">
                                        Simulated AI responses
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                {demoMode !== null && (
                                    <Badge variant={demoMode ? "success" : "outline"}>
                                        {demoMode ? "ON" : "OFF"}
                                    </Badge>
                                )}
                                {demoMode === null && (
                                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                                )}
                                <button
                                    onClick={toggleDemoMode}
                                    disabled={demoLoading || demoMode === null}
                                    className={`
                                        relative inline-flex h-6 w-11 items-center rounded-full
                                        transition-colors focus-visible:outline-none focus-visible:ring-2
                                        focus-visible:ring-ring focus-visible:ring-offset-2
                                        disabled:cursor-not-allowed disabled:opacity-50
                                        ${demoMode ? "bg-primary" : "bg-input"}
                                    `}
                                    role="switch"
                                    aria-checked={demoMode ?? false}
                                    aria-label="Toggle demo mode"
                                >
                                    <span
                                        className={`
                                            pointer-events-none inline-block h-5 w-5 transform rounded-full
                                            bg-background shadow-lg ring-0 transition-transform
                                            ${demoMode ? "translate-x-5" : "translate-x-0.5"}
                                        `}
                                    />
                                </button>
                            </div>
                        </div>
                        {demoMessage && (
                            <p className={`text-xs ${demoMessage.includes("Failed") ? "text-destructive" : "text-success"}`}>
                                {demoMessage}
                            </p>
                        )}
                    </CardContent>
                </Card>

                {/* About */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <Info className="w-4 h-4 text-accent" />
                            About
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="space-y-2">
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Application</span>
                                <span className="font-medium">AgentsFlow AI Gateway</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Version</span>
                                <Badge variant="outline">0.1.0</Badge>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Frontend</span>
                                <span className="font-medium">Next.js + shadcn/ui</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Backend</span>
                                <span className="font-medium">FastAPI + SQLAlchemy</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Architecture</span>
                                <span className="font-medium">Hexagonal / Clean</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">LLM Orchestration</span>
                                <span className="font-medium">Portkey AI Gateway</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Routing Engine</span>
                                <span className="font-medium">Policy-based Multi-LLM</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Observability</span>
                                <span className="font-medium">Structured Logging + Traces</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Database</span>
                                <span className="font-medium">SQLite + Alembic Migrations</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Auth</span>
                                <span className="font-medium">API Key / Bearer Token</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Deployment</span>
                                <span className="font-medium">Docker Compose / K8s-ready</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">License</span>
                                <span className="font-medium">Proprietary</span>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Quick Links */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <ExternalLink className="w-4 h-4 text-accent" />
                            Quick Links
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <Link
                            href="/sandbox"
                            className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors"
                        >
                            <MessageSquare className="w-4 h-4 text-muted-foreground" />
                            <div>
                                <p className="text-sm font-medium">Sandbox</p>
                                <p className="text-xs text-muted-foreground">Test chat completions</p>
                            </div>
                        </Link>
                        <Link
                            href="/configuration/providers"
                            className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors"
                        >
                            <Plug className="w-4 h-4 text-muted-foreground" />
                            <div>
                                <p className="text-sm font-medium">Providers</p>
                                <p className="text-xs text-muted-foreground">Manage LLM providers</p>
                            </div>
                        </Link>
                        <Link
                            href="/configuration/policies"
                            className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors"
                        >
                            <Shield className="w-4 h-4 text-muted-foreground" />
                            <div>
                                <p className="text-sm font-medium">Policies</p>
                                <p className="text-xs text-muted-foreground">Configure routing rules</p>
                            </div>
                        </Link>
                        <Link
                            href="/observability"
                            className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors"
                        >
                            <BarChart3 className="w-4 h-4 text-muted-foreground" />
                            <div>
                                <p className="text-sm font-medium">Observability</p>
                                <p className="text-xs text-muted-foreground">View logs and metrics</p>
                            </div>
                        </Link>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

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
} from "lucide-react";
import { api } from "@/lib/api-client";

export default function SettingsPage() {
    const [healthStatus, setHealthStatus] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

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

    useEffect(() => {
        checkHealth();
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
                                        {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
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
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

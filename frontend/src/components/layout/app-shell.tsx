"use client";

import React from "react";
import { Sidebar } from "./sidebar";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { LoginPage } from "@/components/auth/login-page";
import { Loader2 } from "lucide-react";

function AuthGate({ children }: { children: React.ReactNode }) {
    const { isAuthenticated, isLoading } = useAuth();

    if (isLoading) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground">Loading...</span>
                </div>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <LoginPage />;
    }

    return (
        <div className="flex min-h-screen bg-background">
            <Sidebar />
            <main className="flex-1 overflow-auto">
                <div className="p-6 max-w-7xl mx-auto">{children}</div>
            </main>
        </div>
    );
}

export function AppShell({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <AuthGate>{children}</AuthGate>
        </AuthProvider>
    );
}

"use client";

import React from "react";
import { Sidebar } from "./sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex min-h-screen bg-background">
            <Sidebar />
            <main className="flex-1 overflow-auto">
                <div className="p-6 max-w-7xl mx-auto">{children}</div>
            </main>
        </div>
    );
}

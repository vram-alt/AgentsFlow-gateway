"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import {
    LayoutDashboard,
    MessageSquare,
    Activity,
    Settings,
    Zap,
    Shield,
    FileCode,
    ChevronLeft,
    ChevronRight,
    LogOut,
} from "lucide-react";

const navItems = [
    {
        title: "Dashboard",
        href: "/",
        icon: LayoutDashboard,
    },
    {
        title: "Sandbox",
        href: "/sandbox",
        icon: MessageSquare,
    },
    {
        title: "Observability",
        href: "/observability",
        icon: Activity,
    },
    {
        title: "Providers",
        href: "/configuration/providers",
        icon: Zap,
    },
    {
        title: "Policies",
        href: "/configuration/policies",
        icon: Shield,
    },
    {
        title: "Configs",
        href: "/configuration/configs",
        icon: FileCode,
    },
    {
        title: "Settings",
        href: "/settings",
        icon: Settings,
    },
];

export function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = React.useState(false);
    const { username, logout } = useAuth();

    return (
        <aside
            className={cn(
                "flex flex-col h-screen bg-sidebar border-r border-border transition-all duration-300 sticky top-0",
                collapsed ? "w-16" : "w-64"
            )}
        >
            {/* Logo */}
            <div className="flex items-center h-16 px-4 border-b border-border">
                {!collapsed && (
                    <Link href="/" className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
                            <Zap className="w-5 h-5 text-white" />
                        </div>
                        <div className="flex flex-col">
                            <span className="text-sm font-bold text-foreground tracking-tight">
                                <span className="text-primary">A</span>gentsFlow
                            </span>
                            <span className="text-[10px] text-muted-foreground leading-none">
                                AI Gateway
                            </span>
                        </div>
                    </Link>
                )}
                {collapsed && (
                    <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center mx-auto">
                        <Zap className="w-5 h-5 text-white" />
                    </div>
                )}
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
                {navItems.map((item) => {
                    const isActive =
                        pathname === item.href ||
                        (item.href !== "/" && pathname.startsWith(item.href));
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                                isActive
                                    ? "bg-primary/10 text-primary border border-primary/20"
                                    : "text-sidebar-foreground hover:bg-secondary hover:text-foreground",
                                collapsed && "justify-center px-2"
                            )}
                            title={collapsed ? item.title : undefined}
                        >
                            <item.icon className={cn("w-5 h-5 shrink-0", isActive && "text-primary")} />
                            {!collapsed && <span>{item.title}</span>}
                        </Link>
                    );
                })}
            </nav>

            {/* User & Logout */}
            <div className="p-2 border-t border-border space-y-1">
                {!collapsed && username && (
                    <div className="px-3 py-2">
                        <p className="text-xs text-muted-foreground truncate">Signed in as</p>
                        <p className="text-sm font-medium text-foreground truncate">{username}</p>
                    </div>
                )}
                <button
                    onClick={logout}
                    className={cn(
                        "flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer",
                        collapsed && "justify-center px-2"
                    )}
                    title={collapsed ? "Sign Out" : undefined}
                >
                    <LogOut className="w-5 h-5 shrink-0" />
                    {!collapsed && <span>Sign Out</span>}
                </button>

                {/* Collapse toggle */}
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className="flex items-center justify-center w-full py-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors cursor-pointer"
                >
                    {collapsed ? (
                        <ChevronRight className="w-4 h-4" />
                    ) : (
                        <ChevronLeft className="w-4 h-4" />
                    )}
                </button>
            </div>
        </aside>
    );
}

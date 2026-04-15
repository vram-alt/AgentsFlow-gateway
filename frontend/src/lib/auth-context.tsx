"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

interface AuthState {
    isAuthenticated: boolean;
    username: string | null;
    isLoading: boolean;
}

interface AuthContextType extends AuthState {
    login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
    logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

const AUTH_STORAGE_KEY = "agentsflow_auth";
const SERVER_API_BASE =
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000";
const API_BASE = typeof window === "undefined" ? SERVER_API_BASE : "";

function encodeCredentials(username: string, password: string): string {
    return typeof btoa === "function"
        ? btoa(`${username}:${password}`)
        : Buffer.from(`${username}:${password}`).toString("base64");
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [state, setState] = useState<AuthState>({
        isAuthenticated: false,
        username: null,
        isLoading: true,
    });

    // Check saved credentials on mount
    useEffect(() => {
        const saved = sessionStorage.getItem(AUTH_STORAGE_KEY);
        if (saved) {
            try {
                const { username, token } = JSON.parse(saved);
                // Verify saved credentials are still valid
                fetch(`${API_BASE}/health`, {
                    headers: { Authorization: `Basic ${token}` },
                })
                    .then((res) => {
                        if (res.ok) {
                            setState({ isAuthenticated: true, username, isLoading: false });
                        } else {
                            sessionStorage.removeItem(AUTH_STORAGE_KEY);
                            setState({ isAuthenticated: false, username: null, isLoading: false });
                        }
                    })
                    .catch(() => {
                        sessionStorage.removeItem(AUTH_STORAGE_KEY);
                        setState({ isAuthenticated: false, username: null, isLoading: false });
                    });
            } catch {
                sessionStorage.removeItem(AUTH_STORAGE_KEY);
                setState({ isAuthenticated: false, username: null, isLoading: false });
            }
        } else {
            setState({ isAuthenticated: false, username: null, isLoading: false });
        }
    }, []);

    const login = useCallback(async (username: string, password: string) => {
        const token = encodeCredentials(username, password);
        try {
            const res = await fetch(`${API_BASE}/api/stats/summary`, {
                headers: {
                    Authorization: `Basic ${token}`,
                    "Content-Type": "application/json",
                },
            });

            if (res.ok) {
                sessionStorage.setItem(
                    AUTH_STORAGE_KEY,
                    JSON.stringify({ username, token })
                );
                setState({ isAuthenticated: true, username, isLoading: false });
                return { success: true };
            }

            if (res.status === 401) {
                return { success: false, error: "Invalid username or password" };
            }
            if (res.status === 429) {
                return { success: false, error: "Too many failed attempts. Try again later." };
            }

            return { success: false, error: `Authentication failed (${res.status})` };
        } catch {
            return { success: false, error: "Cannot connect to server" };
        }
    }, []);

    const logout = useCallback(() => {
        sessionStorage.removeItem(AUTH_STORAGE_KEY);
        setState({ isAuthenticated: false, username: null, isLoading: false });
    }, []);

    return (
        <AuthContext.Provider value={{ ...state, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth(): AuthContextType {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}

/**
 * Get the stored auth token for API requests.
 * Returns the Basic auth token string or null if not authenticated.
 */
export function getStoredAuthToken(): string | null {
    if (typeof window === "undefined") return null;
    const saved = sessionStorage.getItem(AUTH_STORAGE_KEY);
    if (!saved) return null;
    try {
        const { token } = JSON.parse(saved);
        return token || null;
    } catch {
        return null;
    }
}

"use client";

import React, { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Send,
    Play,
    Loader2,
    Bot,
    User,
    Copy,
    Check,
    Terminal,
    MessageSquare,
    Trash2,
    X,
    Info,
    Lightbulb,
    Shield,
    Cloud,
    HardDrive,
} from "lucide-react";
import { api, type MessageItem, type ChatResponse, type TesterProxyResponse, type Provider, type Policy, type GuardrailDetails } from "@/lib/api-client";

interface ChatMessage {
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: Date;
    usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
    trace_id?: string;
    guardrail_blocked?: boolean;
    guardrail_details?: GuardrailDetails | null;
}

function getPrimaryProvider(providers: Provider[]): Provider | null {
    return (
        providers.find((provider) => provider.name.toLowerCase() === "portkey") ??
        providers[0] ??
        null
    );
}

function getSuggestedProviderName(_model: string, providers: Provider[]): string | null {
    return getPrimaryProvider(providers)?.name ?? null;
}

const PORTKEY_MODEL_GROUPS = [
    {
        label: "Google",
        options: [
            { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
            { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite" },
            { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
        ],
    },
    {
        label: "OpenAI",
        options: [
            { value: "gpt-4o", label: "GPT-4o" },
            { value: "gpt-4.1", label: "GPT-4.1" },
            { value: "gpt-4o-mini", label: "GPT-4o Mini" },
            { value: "ada-v2", label: "Ada v2 (Embeddings)" },
        ],
    },
    {
        label: "Anthropic",
        options: [
            { value: "claude-sonnet-4-5-20250929", label: "Claude Sonnet 4.5" },
            { value: "claude-3-7-sonnet-latest", label: "Claude 3.7 Sonnet" },
            { value: "claude-haiku-4-5-20250929", label: "Claude Haiku 4.5" },
        ],
    },
    {
        label: "OpenRouter",
        options: [
            { value: "@openrouter/openai/gpt-4o", label: "OpenRouter · GPT-4o" },
            { value: "@openrouter/anthropic/claude-3.5-sonnet", label: "OpenRouter · Claude 3.5 Sonnet" },
            { value: "@openrouter/meta-llama/llama-3.1-8b-instruct", label: "OpenRouter · Llama 3.1 8B" },
        ],
    },
] as const;

export default function SandboxPage() {
    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Sandbox</h1>
                <p className="text-muted-foreground">Test your AI Gateway with chat or raw JSON requests</p>
            </div>

            <Tabs defaultValue="chat" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="chat" className="gap-2">
                        <MessageSquare className="w-4 h-4" />
                        Chat
                    </TabsTrigger>
                    <TabsTrigger value="json" className="gap-2">
                        <Terminal className="w-4 h-4" />
                        JSON Tester
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="chat">
                    <ChatTab />
                </TabsContent>
                <TabsContent value="json">
                    <JsonTesterTab />
                </TabsContent>
            </Tabs>
        </div>
    );
}

// ─── Chat Tab ───────────────────────────────────────────────────────────

function ChatTab() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [model, setModel] = useState("gemini-2.5-flash");
    const [provider, setProvider] = useState("portkey");
    const [temperature, setTemperature] = useState("0.7");
    const [maxTokens, setMaxTokens] = useState("1024");
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Dynamic providers and policies
    const [providers, setProviders] = useState<Provider[]>([]);
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [selectedGuardrails, setSelectedGuardrails] = useState<string[]>([]);
    const [guardrailMode, setGuardrailMode] = useState<"cloud" | "local">("cloud");

    useEffect(() => {
        api.listProviders()
            .then((data) => {
                const active = (Array.isArray(data) ? data : []).filter((p) => p.is_active);
                const primaryProvider = getPrimaryProvider(active);
                setProviders(primaryProvider ? [primaryProvider] : []);
                setProvider(primaryProvider?.name ?? "portkey");
            })
            .catch(() => {
                setProviders([]);
                setProvider("portkey");
            });

        // Load all active policies (both cloud and local)
        api.listPolicies()
            .then((data) => {
                const active = (Array.isArray(data) ? data : []).filter(
                    (p) => p.is_active
                );
                setPolicies(active);
            })
            .catch(() => setPolicies([]));
    }, []);

    useEffect(() => {
        if (messages.length > 0) {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages]);

    const toggleGuardrail = (remoteId: string) => {
        setSelectedGuardrails((prev) =>
            prev.includes(remoteId)
                ? prev.filter((id) => id !== remoteId)
                : [...prev, remoteId]
        );
    };

    const sendMessage = async () => {
        if (!input.trim() || loading) return;

        const userMsg: ChatMessage = {
            role: "user",
            content: input.trim(),
            timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setInput("");
        setLoading(true);

        try {
            const allMessages: MessageItem[] = [
                ...messages.map((m) => ({ role: m.role, content: m.content })),
                { role: "user", content: userMsg.content },
            ];

            const response: ChatResponse = await api.sendChat({
                model,
                messages: allMessages,
                provider_name: provider,
                temperature: parseFloat(temperature) || null,
                max_tokens: parseInt(maxTokens) || null,
                guardrail_ids: selectedGuardrails.length > 0 ? selectedGuardrails : undefined,
            });

            // Build blocked message with guardrail details from backend
            let blockedContent = "";
            if (response.guardrail_blocked) {
                const details = response.guardrail_details;

                // Resolve guardrail UUIDs to human-readable policy names
                const resolveHookName = (hookId: string): string => {
                    const policy = policies.find(p => p.remote_id === hookId);
                    return policy?.name || hookId;
                };

                if (details?.hooks && details.hooks.length > 0) {
                    // Find which hooks actually failed (verdict=false)
                    const failedHooks = details.hooks.filter(h => !h.verdict || (h.checks && h.checks.some(c => !c.verdict)));
                    const blockedByNames = failedHooks.length > 0
                        ? failedHooks.map(h => resolveHookName(h.id))
                        : details.hooks.map(h => resolveHookName(h.id));

                    blockedContent = `Blocked by: ${blockedByNames.join(", ")}`;

                    // Add specific failed check explanations
                    if (details.failed_checks && details.failed_checks.length > 0) {
                        const reasons = details.failed_checks
                            .filter(c => c.explanation)
                            .map(c => {
                                // Clean up technical explanation for user
                                const exp = c.explanation
                                    .replace(/The regex pattern '[^']*' matched the text\.?/i, "Prohibited content detected in your message.")
                                    .replace(/The regex pattern '[^']*' did not match the text\.?/i, "Message content did not pass the security check.")
                                    .replace(/An error occurred while processing the regex:.*/, "Security check encountered an error.");
                                return `• ${exp}`;
                            })
                            .join("\n");
                        if (reasons) {
                            blockedContent += "\n\nReason:\n" + reasons;
                        }
                    }
                } else if (details?.summary) {
                    blockedContent = details.summary;
                } else {
                    // Fallback to policy names from selected guardrails
                    const appliedNames = selectedGuardrails
                        .map(id => policies.find(p => p.remote_id === id)?.name || id)
                        .join(", ");
                    blockedContent = `Blocked by: ${appliedNames || "Unknown policy"}\n\nYour message did not pass the security checks.`;
                }
            }

            const assistantMsg: ChatMessage = {
                role: "assistant",
                content: response.guardrail_blocked
                    ? blockedContent
                    : response.content,
                timestamp: new Date(),
                usage: response.usage as ChatMessage["usage"],
                trace_id: response.trace_id,
                guardrail_blocked: response.guardrail_blocked,
                guardrail_details: response.guardrail_details,
            };
            setMessages((prev) => [...prev, assistantMsg]);
        } catch (err) {
            const errMessage = err instanceof Error ? err.message : "Unknown error";

            // Detect guardrail validation errors (local policies sent to Portkey)
            const isGuardrailError = errMessage.includes("guardrails are not valid") ||
                errMessage.includes("not valid") ||
                errMessage.includes("guardrail");

            if (isGuardrailError && selectedGuardrails.length > 0) {
                // Show as a guardrail-blocked message with policy names
                const appliedNames = selectedGuardrails
                    .map(id => {
                        const p = policies.find(pol => (pol.remote_id || pol.name) === id);
                        return p?.name || id;
                    })
                    .join(", ");

                const blockedMsg: ChatMessage = {
                    role: "assistant",
                    content: `Blocked by: ${appliedNames}\n\nThe selected guardrail policy is not available on the cloud provider. Local policies cannot enforce real-time checks — use Cloud policies for active protection.`,
                    timestamp: new Date(),
                    guardrail_blocked: true,
                };
                setMessages((prev) => [...prev, blockedMsg]);
            } else {
                const errorMsg: ChatMessage = {
                    role: "assistant",
                    content: `Error: ${errMessage}`,
                    timestamp: new Date(),
                };
                setMessages((prev) => [...prev, errorMsg]);
            }
        } finally {
            setLoading(false);
        }
    };

    const copyToClipboard = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopied(id);
        setTimeout(() => setCopied(null), 2000);
    };

    return (
        <>
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                {/* Settings Panel */}
                <Card className="lg:col-span-1">
                    <CardHeader>
                        <CardTitle className="text-base">Settings</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-sm text-muted-foreground">Provider</label>
                            <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
                                {providers.length === 0 && (
                                    <option value="portkey">Portkey</option>
                                )}
                                {providers.map((p) => (
                                    <option key={p.id} value={p.name}>
                                        Portkey
                                    </option>
                                ))}
                            </Select>

                        </div>
                        <div className="space-y-2">
                            <label className="text-sm text-muted-foreground">Model</label>
                            <Select
                                value={model}
                                onChange={(e) => {
                                    const nextModel = e.target.value;
                                    setModel(nextModel);
                                    const suggestedProvider = getSuggestedProviderName(nextModel, providers);
                                    if (suggestedProvider) {
                                        setProvider(suggestedProvider);
                                    }
                                }}
                            >
                                {PORTKEY_MODEL_GROUPS.map((group) => (
                                    <optgroup key={group.label} label={group.label}>
                                        {group.options.map((option) => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </optgroup>
                                ))}
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm text-muted-foreground">Temperature</label>
                            <Input
                                type="number"
                                step="0.1"
                                min="0"
                                max="2"
                                value={temperature}
                                onChange={(e) => setTemperature(e.target.value)}
                            />

                        </div>
                        <div className="space-y-2">
                            <label className="text-sm text-muted-foreground">Max Tokens</label>
                            <Input
                                type="number"
                                min="1"
                                max="128000"
                                value={maxTokens}
                                onChange={(e) => setMaxTokens(e.target.value)}
                            />

                        </div>

                        {/* Guardrail Policies */}
                        {policies.length > 0 && (() => {
                            const cloudPolicies = policies.filter(p => !!p.remote_id);
                            const localPolicies = policies.filter(p => !p.remote_id);
                            const filteredPolicies = guardrailMode === "cloud" ? cloudPolicies : localPolicies;
                            const availablePolicies = filteredPolicies.filter(
                                p => !selectedGuardrails.includes(p.remote_id || p.name)
                            );

                            return (
                                <div className="space-y-3">
                                    <label className="text-sm text-muted-foreground flex justify-between items-center">
                                        <span className="flex items-center gap-1.5">
                                            <Shield className="w-3.5 h-3.5" />
                                            Guardrails
                                        </span>
                                        {selectedGuardrails.length > 0 && (
                                            <span className="text-xs text-primary">{selectedGuardrails.length} active</span>
                                        )}
                                    </label>

                                    {/* Compact Cloud / Local toggle */}
                                    <div className="relative flex items-center w-full rounded-lg bg-secondary/60 p-0.5 text-[11px]">
                                        {/* Sliding highlight */}
                                        <div
                                            className="absolute top-0.5 bottom-0.5 w-[calc(50%-2px)] rounded-md bg-primary shadow-sm transition-transform duration-200 ease-in-out"
                                            style={{ transform: guardrailMode === "local" ? "translateX(calc(100% + 4px))" : "translateX(0)" }}
                                        />
                                        <button
                                            onClick={() => setGuardrailMode("cloud")}
                                            className={`relative z-10 flex items-center justify-center gap-1 w-1/2 py-1 rounded-md font-medium transition-colors duration-200 cursor-pointer ${guardrailMode === "cloud"
                                                ? "text-primary-foreground"
                                                : "text-muted-foreground hover:text-foreground"
                                                }`}
                                        >
                                            <Cloud className="w-3 h-3" />
                                            Cloud
                                            {cloudPolicies.length > 0 && (
                                                <span className="opacity-60">({cloudPolicies.length})</span>
                                            )}
                                        </button>
                                        <button
                                            onClick={() => setGuardrailMode("local")}
                                            className={`relative z-10 flex items-center justify-center gap-1 w-1/2 py-1 rounded-md font-medium transition-colors duration-200 cursor-pointer ${guardrailMode === "local"
                                                ? "text-primary-foreground"
                                                : "text-muted-foreground hover:text-foreground"
                                                }`}
                                        >
                                            <HardDrive className="w-3 h-3" />
                                            Local
                                            {localPolicies.length > 0 && (
                                                <span className="opacity-60">({localPolicies.length})</span>
                                            )}
                                        </button>
                                    </div>

                                    <p className="text-[10px] text-muted-foreground/70 leading-tight">
                                        {guardrailMode === "cloud"
                                            ? "Cloud guardrails are enforced by Portkey — requests are validated before reaching the LLM."
                                            : "Local policies are informational only — they are not enforced by Portkey Cloud."}
                                    </p>

                                    <Select
                                        value=""
                                        onChange={(e) => {
                                            if (e.target.value) {
                                                if (!selectedGuardrails.includes(e.target.value)) {
                                                    toggleGuardrail(e.target.value);
                                                }
                                            }
                                        }}
                                    >
                                        <option value="" disabled>Add a guardrail...</option>
                                        {availablePolicies.map(p => (
                                            <option key={p.id} value={p.remote_id || p.name}>{p.name}</option>
                                        ))}
                                    </Select>

                                    {selectedGuardrails.length > 0 && (
                                        <div className="space-y-1.5 mt-1">
                                            <div className="flex flex-wrap gap-1.5">
                                                {selectedGuardrails.map(id => {
                                                    const policy = policies.find(p => (p.remote_id || p.name) === id);
                                                    if (!policy) return null;
                                                    const isCloud = !!policy.remote_id;
                                                    return (
                                                        <Badge
                                                            key={id}
                                                            variant="secondary"
                                                            className={`flex items-center gap-1 cursor-pointer hover:bg-destructive/10 hover:text-destructive transition-colors py-0.5 px-2 text-[11px] ${isCloud ? "border-blue-500/20" : "border-orange-500/20"}`}
                                                            onClick={() => toggleGuardrail(id)}
                                                            title="Click to remove"
                                                        >
                                                            {isCloud ? <Cloud className="w-2.5 h-2.5 opacity-50" /> : <HardDrive className="w-2.5 h-2.5 opacity-50" />}
                                                            {policy.name}
                                                            <X className="w-2.5 h-2.5 ml-0.5 opacity-40" />
                                                        </Badge>
                                                    );
                                                })}
                                            </div>
                                            <button
                                                onClick={() => setSelectedGuardrails([])}
                                                className="text-[10px] text-muted-foreground hover:text-destructive transition-colors cursor-pointer flex items-center gap-1"
                                            >
                                                <Trash2 className="w-2.5 h-2.5" />
                                                Clear all guardrails
                                            </button>
                                        </div>
                                    )}
                                </div>
                            );
                        })()}

                        <Button
                            variant="outline"
                            size="sm"
                            className="w-full"
                            onClick={() => setMessages([])}
                        >
                            <Trash2 className="w-4 h-4 mr-2" />
                            Clear Chat
                        </Button>

                    </CardContent>
                </Card>

                {/* Chat Area */}
                <Card className="lg:col-span-3 flex flex-col h-[calc(100vh-14rem)]">
                    <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
                        {messages.length === 0 && (
                            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                <Bot className="w-12 h-12 mb-4 opacity-30" />
                                <p className="text-sm font-medium">Send a message to start the conversation</p>
                                <p className="text-xs mt-2 max-w-md text-center">
                                    Your messages are sent through the AI Gateway to the selected LLM provider.
                                    Each response includes a trace ID for debugging in the Observability tab.
                                </p>
                            </div>
                        )}
                        {messages.map((msg, i) => (
                            <div
                                key={i}
                                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                            >
                                {msg.role !== "user" && (
                                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                                        <Bot className="w-4 h-4 text-primary" />
                                    </div>
                                )}
                                <div
                                    className={`max-w-[80%] rounded-xl p-4 ${msg.role === "user"
                                        ? "bg-primary text-primary-foreground"
                                        : msg.guardrail_blocked
                                            ? "bg-destructive/10 border border-destructive/30"
                                            : "bg-secondary"
                                        }`}
                                >
                                    {msg.guardrail_blocked && (
                                        <div className="flex items-center gap-2 mb-2 pb-2 border-b border-destructive/30">
                                            <div className="w-5 h-5 rounded-full bg-destructive/20 flex items-center justify-center">
                                                <X className="w-3 h-3 text-destructive" />
                                            </div>
                                            <span className="text-xs font-semibold uppercase tracking-wider text-destructive">Guardrail Blocked</span>
                                        </div>
                                    )}
                                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                                    <div className="flex items-center gap-2 mt-2">
                                        <span className="text-[10px] opacity-60">
                                            {msg.timestamp.toLocaleTimeString()}
                                        </span>
                                        {msg.trace_id && (
                                            <Badge variant="outline" className="text-[10px] h-4">
                                                {msg.trace_id.slice(0, 8)}
                                            </Badge>
                                        )}
                                        {msg.usage && (
                                            <span className="text-[10px] opacity-60">
                                                {msg.usage.total_tokens} tokens
                                            </span>
                                        )}
                                        <button
                                            onClick={() => copyToClipboard(msg.content, `msg-${i}`)}
                                            className="opacity-40 hover:opacity-100 transition-opacity cursor-pointer"
                                        >
                                            {copied === `msg-${i}` ? (
                                                <Check className="w-3 h-3" />
                                            ) : (
                                                <Copy className="w-3 h-3" />
                                            )}
                                        </button>
                                    </div>
                                </div>
                                {msg.role === "user" && (
                                    <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center shrink-0">
                                        <User className="w-4 h-4 text-accent" />
                                    </div>
                                )}
                            </div>
                        ))}
                        {loading && (
                            <div className="flex gap-3">
                                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                                    <Bot className="w-4 h-4 text-primary" />
                                </div>
                                <div className="bg-secondary rounded-xl p-4">
                                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </CardContent>

                    {/* Input */}
                    <div className="p-4 border-t border-border">
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                sendMessage();
                            }}
                            className="flex gap-2"
                        >
                            <Input
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder="Type your message..."
                                disabled={loading}
                                className="flex-1"
                            />
                            <Button type="submit" disabled={loading || !input.trim()}>
                                {loading ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                    <Send className="w-4 h-4" />
                                )}
                            </Button>
                        </form>
                    </div>
                </Card>
            </div>

            {/* Quick Tips — visible when scrolling below the chat area */}
            <div className="mt-6 p-4 rounded-lg border border-primary/20 bg-primary/5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2 mb-3">
                    <Lightbulb className="w-4 h-4 text-primary" />
                    <span className="font-medium text-sm text-primary">Quick Tips</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-3">
                        <div className="flex items-start gap-2">
                            <Bot className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                            <p><strong>Provider</strong> — select which LLM service to use. Configure in <a href="/configuration/providers" className="text-primary underline">Providers</a></p>
                        </div>
                        <div className="flex items-start gap-2">
                            <Terminal className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                            <p><strong>Model</strong> — choose a supported Portkey model such as <code className="bg-secondary px-1 rounded">gemini-2.5-flash</code> or <code className="bg-secondary px-1 rounded">@openrouter/openai/gpt-4o</code></p>
                        </div>
                    </div>
                    <div className="space-y-3">
                        <div className="flex items-start gap-2">
                            <Send className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                            <p><strong>Temperature</strong> — randomness: 0 = precise, 1 = creative, 2 = random</p>
                        </div>
                        <div className="flex items-start gap-2">
                            <MessageSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                            <p><strong>Max Tokens</strong> — limits response length. Higher = longer but costlier</p>
                        </div>
                    </div>
                    <div className="space-y-3">
                        <div className="flex items-start gap-2">
                            <X className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                            <p><strong>Guardrails</strong> — filter harmful content. Manage in <a href="/configuration/policies" className="text-primary underline">Policies</a></p>
                        </div>
                        <div className="flex items-start gap-2">
                            <Copy className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                            <p><strong>Trace ID</strong> — unique ID per response, find in <a href="/observability" className="text-primary underline">Observability</a></p>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}

// ─── JSON Tester Tab ────────────────────────────────────────────────────

function JsonTesterTab() {
    const [providers, setProviders] = useState<Provider[]>([]);
    const [provider, setProvider] = useState("portkey");
    const [method, setMethod] = useState("POST");
    const [path, setPath] = useState("/chat/completions");
    const [body, setBody] = useState(
        JSON.stringify(
            {
                model: "gemini-2.5-flash",
                messages: [{ role: "user", content: "Hello!" }],
                temperature: 0.7,
            },
            null,
            2
        )
    );
    const [headers, setHeaders] = useState("{}");
    const [response, setResponse] = useState<TesterProxyResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        api.listProviders()
            .then((data) => {
                const active = (Array.isArray(data) ? data : []).filter((p) => p.is_active);
                const primaryProvider = getPrimaryProvider(active);
                setProviders(primaryProvider ? [primaryProvider] : []);
                setProvider(primaryProvider?.name ?? "portkey");
            })
            .catch(() => {
                setProviders([]);
                setProvider("portkey");
            });
    }, []);

    const sendRequest = async () => {
        setLoading(true);
        setError(null);
        setResponse(null);

        try {
            let parsedBody = null;
            if (body.trim()) {
                parsedBody = JSON.parse(body);
            }
            let parsedHeaders = null;
            if (headers.trim() && headers.trim() !== "{}") {
                parsedHeaders = JSON.parse(headers);
            }

            const result = await api.testerProxy({
                provider_name: provider,
                method,
                path,
                body: parsedBody,
                headers: parsedHeaders,
            });
            setResponse(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Request failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Request Panel */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        <Terminal className="w-4 h-4 text-primary" />
                        Request
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="p-3 rounded-lg bg-secondary/50 text-xs text-muted-foreground flex items-start gap-2">
                        <Info className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>
                            Send raw HTTP requests to the LLM provider through the gateway.
                            The request is proxied through your selected provider&apos;s base URL.
                            Use this to test any API endpoint supported by the provider.
                        </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                        <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">Provider</label>
                            <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
                                {providers.length === 0 && (
                                    <option value="portkey">Portkey</option>
                                )}
                                {providers.map((p) => (
                                    <option key={p.id} value={p.name}>
                                        Portkey
                                    </option>
                                ))}
                            </Select>
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">Method</label>
                            <Select value={method} onChange={(e) => setMethod(e.target.value)}>
                                <option value="GET">GET</option>
                                <option value="POST">POST</option>
                                <option value="PUT">PUT</option>
                                <option value="DELETE">DELETE</option>
                            </Select>
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">Path</label>
                            <Input value={path} onChange={(e) => setPath(e.target.value)} />
                        </div>
                    </div>

                    <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Headers (JSON) — optional extra headers</label>
                        <Textarea
                            value={headers}
                            onChange={(e) => setHeaders(e.target.value)}
                            className="font-mono text-xs h-20"
                            placeholder="{}"
                        />
                    </div>

                    <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Body (JSON) — the request payload</label>
                        <Textarea
                            value={body}
                            onChange={(e) => setBody(e.target.value)}
                            className="font-mono text-xs h-48"
                        />
                    </div>

                    <Button onClick={sendRequest} disabled={loading} className="w-full">
                        {loading ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Play className="w-4 h-4 mr-2" />
                        )}
                        Send Request
                    </Button>
                </CardContent>
            </Card>

            {/* Response Panel */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        Response
                        {response && (
                            <Badge
                                variant={response.status_code < 400 ? "success" : "destructive"}
                                className="ml-2"
                            >
                                {response.status_code}
                            </Badge>
                        )}
                        {response?.latency_ms && (
                            <span className="text-xs text-muted-foreground font-normal ml-auto">
                                {response.latency_ms.toFixed(0)}ms
                            </span>
                        )}
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    {!response && !error && (
                        <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
                            <Terminal className="w-8 h-8 mb-2 opacity-30" />
                            <p className="text-sm">Send a request to see the response</p>
                            <p className="text-xs mt-1">Status code, headers, and body will appear here</p>
                        </div>
                    )}
                    {error && (
                        <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                            {error}
                        </div>
                    )}
                    {response && (
                        <div className="space-y-4">
                            <div className="space-y-1">
                                <label className="text-xs text-muted-foreground">Response Headers</label>
                                <pre className="p-3 rounded-lg bg-secondary text-xs font-mono overflow-auto max-h-32">
                                    {JSON.stringify(response.headers, null, 2)}
                                </pre>
                            </div>
                            <div className="space-y-1">
                                <label className="text-xs text-muted-foreground">Response Body</label>
                                <pre className="p-3 rounded-lg bg-secondary text-xs font-mono overflow-auto max-h-96">
                                    {typeof response.body === "string"
                                        ? response.body
                                        : JSON.stringify(response.body, null, 2)}
                                </pre>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Quick Tips */}
            <div className="col-span-full p-4 rounded-lg border border-primary/20 bg-primary/5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2 mb-3">
                    <Lightbulb className="w-4 h-4 text-primary" />
                    <span className="font-medium text-sm text-primary">Quick Tips</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="flex items-start gap-2">
                        <Terminal className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p><strong>Provider:</strong> Select which LLM service to send the request through. Must be configured in Providers.</p>
                    </div>
                    <div className="flex items-start gap-2">
                        <Send className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p><strong>Method + Path:</strong> POST /chat/completions is the standard chat endpoint. Try GET /models to list available models.</p>
                    </div>
                    <div className="flex items-start gap-2">
                        <Play className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p><strong>Body:</strong> JSON payload sent to the provider. Must include <code className="bg-secondary px-1 rounded">model</code> and <code className="bg-secondary px-1 rounded">messages</code> for chat requests.</p>
                    </div>
                    <div className="flex items-start gap-2">
                        <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
                        <p><strong>Response:</strong> Shows HTTP status code, response headers, and the full response body from the provider.</p>
                    </div>
                </div>
            </div>
        </div>
    );
}

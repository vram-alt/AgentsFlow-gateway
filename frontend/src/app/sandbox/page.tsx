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
} from "lucide-react";
import { api, type MessageItem, type ChatResponse, type TesterProxyResponse } from "@/lib/api-client";

interface ChatMessage {
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: Date;
    usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
    trace_id?: string;
}

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
    const [model, setModel] = useState("gpt-4o-mini");
    const [provider, setProvider] = useState("portkey");
    const [temperature, setTemperature] = useState("0.7");
    const [maxTokens, setMaxTokens] = useState("1024");
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

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
            });

            const assistantMsg: ChatMessage = {
                role: "assistant",
                content: response.content,
                timestamp: new Date(),
                usage: response.usage as ChatMessage["usage"],
                trace_id: response.trace_id,
            };
            setMessages((prev) => [...prev, assistantMsg]);
        } catch (err) {
            const errorMsg: ChatMessage = {
                role: "assistant",
                content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMsg]);
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
                            <option value="portkey">Portkey</option>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Model</label>
                        <Input
                            value={model}
                            onChange={(e) => setModel(e.target.value)}
                            placeholder="gpt-4o-mini"
                        />
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
            <Card className="lg:col-span-3 flex flex-col h-[calc(100vh-16rem)]">
                <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
                    {messages.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                            <Bot className="w-12 h-12 mb-4 opacity-30" />
                            <p className="text-sm">Send a message to start the conversation</p>
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
                                        : "bg-secondary"
                                    }`}
                            >
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
    );
}

// ─── JSON Tester Tab ────────────────────────────────────────────────────

function JsonTesterTab() {
    const [provider, setProvider] = useState("portkey");
    const [method, setMethod] = useState("POST");
    const [path, setPath] = useState("/chat/completions");
    const [body, setBody] = useState(
        JSON.stringify(
            {
                model: "gpt-4o-mini",
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
                    <div className="grid grid-cols-3 gap-2">
                        <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">Provider</label>
                            <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
                                <option value="portkey">Portkey</option>
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
                        <label className="text-xs text-muted-foreground">Headers (JSON)</label>
                        <Textarea
                            value={headers}
                            onChange={(e) => setHeaders(e.target.value)}
                            className="font-mono text-xs h-20"
                            placeholder="{}"
                        />
                    </div>

                    <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Body (JSON)</label>
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
        </div>
    );
}

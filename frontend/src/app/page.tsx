"use client";

import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Activity,
  AlertTriangle,
  Clock,
  TrendingUp,
  Zap,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
  Server,
  Lightbulb,
} from "lucide-react";
import { api, type StatsSummary, type ChartData, type ProviderHealth } from "@/lib/api-client";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
}

function StatCard({ title, value, subtitle, icon, trend, trendValue }: StatCardProps) {
  return (
    <Card className="hover:border-primary/30 transition-colors">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold tracking-tight">{value}</p>
            {subtitle && (
              <div className="flex items-center gap-1">
                {trend === "up" && <ArrowUpRight className="w-3 h-3 text-success" />}
                {trend === "down" && <ArrowDownRight className="w-3 h-3 text-destructive" />}
                <span
                  className={`text-xs ${trend === "up"
                    ? "text-success"
                    : trend === "down"
                      ? "text-destructive"
                      : "text-muted-foreground"
                    }`}
                >
                  {trendValue && `${trendValue} `}
                  {subtitle}
                </span>
              </div>
            )}
          </div>
          <div className="p-3 rounded-lg bg-primary/10 text-primary">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function SimpleBarChart({ data }: { data: Array<{ hour: string; count: number }> }) {
  if (!data || data.length === 0) return <div className="text-muted-foreground text-sm">No data</div>;
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="flex items-end gap-1 h-32">
      {data.slice(-24).map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1">
          <div
            className="w-full bg-primary/80 rounded-t-sm min-h-[2px] transition-all hover:bg-primary"
            style={{ height: `${(d.count / max) * 100}%` }}
            title={`${d.hour}: ${d.count}`}
          />
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [charts, setCharts] = useState<ChartData | null>(null);
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, chartsData, healthData] = await Promise.allSettled([
        api.getStatsSummary(),
        api.getStatsCharts(24),
        api.getProvidersHealth(),
      ]);

      if (summaryData.status === "fulfilled") setSummary(summaryData.value);
      if (chartsData.status === "fulfilled") setCharts(chartsData.value);
      if (healthData.status === "fulfilled") setHealth(healthData.value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">AI Gateway overview and metrics</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="p-4 flex items-center gap-2 text-destructive">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-sm">{error}</span>
          </CardContent>
        </Card>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Requests"
          value={summary?.total_requests?.toLocaleString() ?? "—"}
          subtitle="all time"
          icon={<Activity className="w-5 h-5" />}
        />
        <StatCard
          title="Today's Requests"
          value={summary?.requests_today?.toLocaleString() ?? "—"}
          subtitle="since midnight"
          icon={<TrendingUp className="w-5 h-5" />}
          trend="up"
        />
        <StatCard
          title="Error Rate"
          value={summary ? `${(summary.error_rate * 100).toFixed(1)}%` : "—"}
          subtitle="of total requests"
          icon={<AlertTriangle className="w-5 h-5" />}
          trend={summary && summary.error_rate > 0.05 ? "down" : "neutral"}
        />
        <StatCard
          title="Avg Latency"
          value={summary ? `${summary.avg_latency_ms.toFixed(0)}ms` : "—"}
          subtitle="response time"
          icon={<Clock className="w-5 h-5" />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="w-4 h-4 text-primary" />
              Requests (24h)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <SimpleBarChart data={charts ?? []} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="w-4 h-4 text-destructive" />
              Errors (24h)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <SimpleBarChart data={[]} />
          </CardContent>
        </Card>
      </div>

      {/* Bottom Row: Providers Health + Top Models */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Provider Health */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="w-4 h-4 text-accent" />
              Provider Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {health.length === 0 && (
                <p className="text-sm text-muted-foreground">No providers configured</p>
              )}
              {health.map((p, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-3 rounded-lg bg-secondary/50"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-2 h-2 rounded-full ${p.status === "healthy"
                        ? "bg-success animate-pulse-dot"
                        : "bg-destructive"
                        }`}
                    />
                    <span className="text-sm font-medium">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {p.latency_ms && (
                      <span className="text-xs text-muted-foreground">
                        {p.latency_ms.toFixed(0)}ms
                      </span>
                    )}
                    <Badge variant={p.status === "healthy" ? "success" : "destructive"}>
                      {p.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Top Models */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Zap className="w-4 h-4 text-primary" />
              Top Models
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {(!summary?.top_models || summary.top_models.length === 0) && (
                <p className="text-sm text-muted-foreground">No data yet</p>
              )}
              {summary?.top_models?.map((m, i) => {
                const maxCount = summary.top_models[0]?.count ?? 1;
                return (
                  <div key={i} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium truncate">{m.model}</span>
                      <span className="text-muted-foreground">{m.count}</span>
                    </div>
                    <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${(m.count / maxCount) * 100}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Tips */}
      <div className="p-4 rounded-lg border border-primary/20 bg-primary/5 text-xs text-muted-foreground">
        <div className="flex items-center gap-2 mb-3">
          <Lightbulb className="w-4 h-4 text-primary" />
          <span className="font-medium text-sm text-primary">Quick Tips</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <div className="flex items-start gap-2">
            <Activity className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
            <p>Total Requests and Error Rate show all-time statistics from the audit log.</p>
          </div>
          <div className="flex items-start gap-2">
            <Server className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
            <p>Provider Health checks if your LLM providers are reachable.</p>
          </div>
          <div className="flex items-start gap-2">
            <Zap className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
            <p>Top Models shows which AI models are used most frequently.</p>
          </div>
          <div className="flex items-start gap-2">
            <RefreshCw className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary/60" />
            <p>Data refreshes automatically every 60 seconds, or click Refresh manually.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

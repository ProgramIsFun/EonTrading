import type { BacktestParams } from "../types/backtest";
import { API_BASE } from "../constants";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchBacktest(params: BacktestParams): Promise<any> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  return apiGet(`/api/backtest?${query}`);
}

export async function fetchPriceBacktest(params: Record<string, string>): Promise<any> {
  const query = new URLSearchParams(params);
  return apiGet(`/api/price-backtest?${query}`);
}

export async function fetchLiveBacktest(
  params: Record<string, number | string>,
  onProgress?: (pct: number, log: string[]) => void,
): Promise<any> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  const { job_id: jobId } = await apiPost<{ job_id: string }>(`/api/live-backtest?${query}`);

  while (true) {
    await new Promise((r) => setTimeout(r, 1000));
    const data = await apiGet<any>(`/api/live-backtest/${jobId}`);
    if (data.status === "done") return data;
    if (data.status === "error") throw new Error(data.error || "Backtest failed");
    if (data.status === "not_found") throw new Error("Job not found");
    if (onProgress) onProgress(data.progress || 0, data.log || []);
  }
}

export async function fetchNews(): Promise<any[]> {
  return apiGet<any[]>("/api/news");
}

export async function getNewsCount(): Promise<number> {
  const data = await apiGet<{ count: number }>("/api/news/count");
  return data.count;
}

export async function fetchLogs(
  loggerName?: string, level?: string, limit = 100
): Promise<{ logs: any[] }> {
  const params = new URLSearchParams();
  if (loggerName) params.set("logger_name", loggerName);
  if (level) params.set("level", level);
  params.set("limit", String(limit));
  return apiGet(`/api/logs?${params}`);
}

export async function getCollectorStatus(): Promise<boolean> {
  const data = await apiGet<{ collecting: boolean }>("/api/news/collector/status");
  return data.collecting;
}

export async function toggleCollector(enable: boolean): Promise<void> {
  await apiPost("/api/news/collector/toggle", { enable });
}

export async function fetchHealth(): Promise<any> {
  return apiGet("/api/health");
}

export async function fetchDockerStatus(): Promise<{ containers: any[] }> {
  return apiGet("/api/docker/status");
}

export async function fetchQueues(): Promise<{ queues: Record<string, number> }> {
  return apiGet("/api/queues");
}

export async function fetchDockerLogs(name: string, lines = 50): Promise<any> {
  return apiGet(`/api/docker/logs/${name}?lines=${lines}`);
}

export async function dockerAction(action: string, name: string, params?: Record<string, string>): Promise<any> {
  let url = `/api/docker/${action}/${name}`;
  if (params) {
    const qs = new URLSearchParams(params);
    url += `?${qs}`;
  }
  return apiPost(url);
}

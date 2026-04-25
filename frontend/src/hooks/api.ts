const API_BASE = import.meta.env.VITE_API_BASE || "";

export async function fetchBacktest(params: Record<string, number>): Promise<any> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  const res = await fetch(`${API_BASE}/api/backtest?${query}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchLiveBacktest(
  params: Record<string, number | string>,
  onProgress?: (pct: number) => void,
): Promise<any> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  // Start the job
  const startRes = await fetch(`${API_BASE}/api/live-backtest?${query}`, { method: "POST" });
  if (!startRes.ok) throw new Error(`API error: ${startRes.status}`);
  const { job_id } = await startRes.json();

  // Poll until done
  while (true) {
    await new Promise((r) => setTimeout(r, 1000));
    const pollRes = await fetch(`${API_BASE}/api/live-backtest/${job_id}`);
    const data = await pollRes.json();
    if (data.status === "done") return data;
    if (data.status === "error") throw new Error(data.error || "Backtest failed");
    if (data.status === "not_found") throw new Error("Job not found");
    if (onProgress) onProgress(data.progress || 0);
  }
}

export async function fetchNews(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/api/news`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getNewsCount(): Promise<number> {
  const res = await fetch(`${API_BASE}/api/news/count`);
  const data = await res.json();
  return data.count;
}

export async function getCollectorStatus(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/collector/status`);
  const data = await res.json();
  return data.running;
}

export async function toggleCollector(start: boolean): Promise<void> {
  await fetch(`${API_BASE}/api/collector/${start ? "start" : "stop"}`, { method: "POST" });
}

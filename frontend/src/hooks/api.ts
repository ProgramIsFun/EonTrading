const API_BASE = "http://localhost:8000";

export async function fetchBacktest(params: Record<string, number>): Promise<any> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  const res = await fetch(`${API_BASE}/api/backtest?${query}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchNews(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/api/news`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

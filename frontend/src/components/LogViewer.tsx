import { useEffect, useState } from "react";
import { fetchLogs } from "../hooks/api";

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "#888",
  INFO: "#22c55e",
  WARNING: "#f59e0b",
  ERROR: "#ef4444",
  CRITICAL: "#dc2626",
};

const PANELS = [
  { label: "Watcher", prefix: "src.live.runners.run_watcher,src.live.news_watcher,src.data.news", color: "#22c55e" },
  { label: "Trader", prefix: "src.live.runners.run_trader,src.live.sentiment_trader", color: "#818cf8" },
  { label: "Analyzer", prefix: "src.live.runners.run_analyzer,src.live.analyzer_service", color: "#f59e0b" },
  { label: "Executor", prefix: "src.live.runners.run_executor,src.live.brokers", color: "#ef4444" },
  { label: "Monitor", prefix: "src.live.runners.run_monitor,src.live.price_monitor", color: "#ec4899" },
  { label: "Others", prefix: "src.common,httpx,__main__", color: "#888" },
];

export default function LogViewer() {
  const [allLogs, setAllLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [level, setLevel] = useState("");

  const load = () => {
    setLoading(true);
    fetchLogs(undefined, undefined, 500)
      .then((r) => setAllLogs(r.logs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  const matches = (l: LogEntry, prefixes: string) => {
    if (level && l.level !== level) return false;
    return prefixes.split(",").some((p) => l.logger.startsWith(p));
  };

  const renderLogLines = (logs: LogEntry[]) =>
    logs.slice(0, 50).map((l, i) => {
      const ts = l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : "";
      return (
        <div key={i} style={{
          display: "flex", gap: 4, padding: "2px 0",
          fontFamily: "monospace", fontSize: 10, borderBottom: "1px solid #1a1a2e", lineHeight: "14px",
        }}>
          <span style={{ color: "#555", flexShrink: 0 }}>{ts}</span>
          <span style={{ color: LEVEL_COLORS[l.level] || "#888", flexShrink: 0, width: 50 }}>{l.level}</span>
          <span style={{ color: "#bbb", wordBreak: "break-word" }}>{l.message}</span>
        </div>
      );
    });

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
        <span style={{ fontSize: 13, color: "#888" }}>Component Logs</span>
        <select value={level} onChange={(e) => setLevel(e.target.value)} style={{
          padding: "4px 8px", background: "#2a2a3e", color: "#888",
          border: "none", borderRadius: 4, fontSize: 12, cursor: "pointer",
        }}>
          <option value="">All levels</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
        <button onClick={load} style={{
          padding: "4px 12px", background: "#2a2a3e", color: "#888",
          border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12,
        }}>Refresh</button>
        {loading && <span style={{ fontSize: 11, color: "#555" }}>Loading...</span>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {PANELS.map((p) => {
          const panelLogs = allLogs.filter((l) => matches(l, p.prefix));
          return (
            <div key={p.label} style={{ background: "#1e1e2e", borderRadius: 8, padding: 10, display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: p.color, marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
                <span>{p.label}</span>
                <span style={{ color: "#555", fontWeight: 400 }}>{panelLogs.length}</span>
              </div>
              <div style={{ maxHeight: 400, overflowY: "auto" }}>
                {panelLogs.length === 0
                  ? <div style={{ fontSize: 10, color: "#444", padding: 4 }}>No logs</div>
                  : renderLogLines(panelLogs)
                }
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

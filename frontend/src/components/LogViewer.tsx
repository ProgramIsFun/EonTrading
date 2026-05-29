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

export default function LogViewer() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [level, setLevel] = useState("");

  const load = () => {
    setLoading(true);
    fetchLogs(undefined, level || undefined, 100)
      .then((r) => setLogs(r.logs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [level]);

  const logLines = logs.map((l, i) => {
    const ts = l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : "";
    return (
      <div key={i} style={{
        display: "flex", gap: 8, padding: "3px 0",
        fontFamily: "monospace", fontSize: 11, borderBottom: "1px solid #1a1a2e",
      }}>
        <span style={{ color: "#555", flexShrink: 0 }}>{ts}</span>
        <span style={{
          color: LEVEL_COLORS[l.level] || "#888", fontWeight: 600, flexShrink: 0, width: 60,
        }}>{l.level}</span>
        <span style={{ color: "#666", flexShrink: 0, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {l.logger}
        </span>
        <span style={{ color: "#bbb", wordBreak: "break-word" }}>{l.message}</span>
      </div>
    );
  });

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 14, color: "#888" }}>
          Component Logs ({logs.length} entries)
        </div>
        <div style={{ display: "flex", gap: 8 }}>
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
        </div>
      </div>
      <div style={{ maxHeight: 600, overflowY: "auto" }}>
        {loading ? <div style={{ color: "#888" }}>Loading...</div> : logLines}
      </div>
    </div>
  );
}

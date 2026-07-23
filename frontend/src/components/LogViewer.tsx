import { useEffect, useState, useRef, useCallback } from "react";

interface LogEntry {
  timestamp: string;
  level: string;
  component: string;
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
  { label: "Watcher", component: "watcher", color: "#22c55e" },
  { label: "Trader", component: "trader", color: "#818cf8" },
  { label: "Analyzer", component: "analyzer", color: "#f59e0b" },
  { label: "Executor", component: "executor", color: "#ef4444" },
  { label: "Monitor", component: "monitor", color: "#ec4899" },
  { label: "Others", component: "", color: "#888" },
];

const MAX_BUFFER = 200;

export default function LogViewer() {
  const [allLogs, setAllLogs] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState("");
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const esRef = useRef<EventSource | null>(null);
  const bufferRef = useRef<LogEntry[]>([]);

  const connect = useCallback(() => {
    const API_BASE = import.meta.env.VITE_API_BASE || "";
    const url = `${API_BASE}/api/logs/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setStatus("connected");

    es.addEventListener("log", (e) => {
      try {
        const log: LogEntry = JSON.parse(e.data);
        bufferRef.current = [...bufferRef.current.slice(-(MAX_BUFFER - 1)), log];
        setAllLogs([...bufferRef.current]);
      } catch {}
    });

    es.onerror = () => {
      setStatus("disconnected");
      es.close();
      setTimeout(connect, 3000);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => esRef.current?.close();
  }, [connect]);

  const matches = (l: LogEntry, component: string) => {
    if (level && l.level !== level) return false;
    if (!component) {
      const known = PANELS.filter((p) => p.component).map((p) => p.component);
      return !known.includes(l.component);
    }
    return l.component === component;
  };

  const renderLogLines = (logs: LogEntry[]) =>
    logs.slice(-50).map((l, i) => {
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

  const statusColor = status === "connected" ? "#22c55e" : status === "connecting" ? "#f59e0b" : "#ef4444";
  const statusLabel = status === "connected" ? "Live" : status === "connecting" ? "Connecting..." : "Disconnected";

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
        <span style={{ fontSize: 13, color: "#888" }}>Component Logs</span>
        <span style={{
          fontSize: 10, color: statusColor, display: "flex", alignItems: "center", gap: 4,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%", background: statusColor,
            display: "inline-block",
          }} />
          {statusLabel}
        </span>
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
        <span style={{ fontSize: 11, color: "#555" }}>{allLogs.length} logs</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {PANELS.map((p) => {
          const panelLogs = allLogs.filter((l) => matches(l, p.component));
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

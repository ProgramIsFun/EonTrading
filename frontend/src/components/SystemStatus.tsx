import { useState, useEffect } from "react";

interface Component {
  component: string;
  status: string;
  lastBeat: string | null;
  ageSec: number;
  host?: string;
  pid?: number;
  [key: string]: unknown;
}

interface HealthData {
  components: Component[];
  open_positions: number;
  collector_running: boolean;
}

export default function SystemStatus() {
  const [health, setHealth] = useState<HealthData | null>(null);

  useEffect(() => {
    const poll = () =>
      fetch("/api/health")
        .then((r) => r.json())
        .then(setHealth)
        .catch(() => setHealth(null));
    poll();
    const id = setInterval(poll, 10000);
    return () => clearInterval(id);
  }, []);

  const order = ["watcher", "analyzer", "trader", "executor"];

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <div style={{ fontSize: 13, color: "#888", marginBottom: 10, fontWeight: 600 }}>
        Live Pipeline Status
        <span style={{ fontSize: 10, color: "#555", marginLeft: 8 }}>polls every 10s</span>
      </div>
      {!health ? (
        <div style={{ fontSize: 12, color: "#555" }}>API not reachable</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {order.map((name) => {
              const c = health.components.find((h) => h.component === name);
              return (
                <div
                  key={name}
                  style={{
                    background: "#1a1a2e",
                    borderRadius: 6,
                    padding: "8px 14px",
                    border: `1px solid ${c ? (c.ageSec < 60 ? "#22c55e33" : c.ageSec < 300 ? "#f59e0b33" : "#55555533") : "#33333333"}`,
                    minWidth: 120,
                  }}
                >
                  <div style={{ fontSize: 12, color: "#ccc", fontWeight: 600 }}>{name}</div>
                  <div style={{ fontSize: 11, color: c ? "#888" : "#555", marginTop: 2 }}>
                    {c ? c.status : "⚫ not started"}
                  </div>
                  {c && (
                    <div style={{ fontSize: 9, color: "#555", marginTop: 2 }}>
                      {c.ageSec}s ago · {c.host} · pid {c.pid}
                    </div>
                  )}
                  {c && Object.entries(c).filter(([k]) => !["component", "status", "lastBeat", "ageSec", "host", "pid"].includes(k)).map(([k, v]) => (
                    <div key={k} style={{ fontSize: 9, color: "#666", marginTop: 1 }}>
                      {k}: {String(v)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: 10, color: "#666", marginTop: 8 }}>
            Open positions: {health.open_positions} · Collector: {health.collector_running ? "🟢" : "⚫"}
          </div>
        </>
      )}
    </div>
  );
}

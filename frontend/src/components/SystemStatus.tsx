import { useState, useEffect, useCallback } from "react";

interface Component {
  component: string;
  timestamp?: string;
  [key: string]: unknown;
}

interface HealthData {
  components: { component: string; status: string; ageSec: number; host?: string; pid?: number; [key: string]: unknown }[];
  open_positions: number;
  collector_running: boolean;
}

interface PingData {
  components: Component[];
  count: number;
}

const ALL = ["watcher", "analyzer", "trader", "executor"];

export default function SystemStatus() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [ping, setPing] = useState<PingData | null>(null);
  const [pinging, setPinging] = useState(false);

  useEffect(() => {
    const poll = () =>
      fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, []);

  const doPing = useCallback(() => {
    setPinging(true);
    fetch("/api/ping").then((r) => r.json()).then((d) => { setPing(d); setPinging(false); }).catch(() => setPinging(false));
  }, []);

  const getStatus = (name: string) => {
    if (ping) {
      const found = ping.components.find((c) => c.component === name);
      return found ? "🟢 alive" : "⚫ no response";
    }
    const hb = health?.components.find((c) => c.component === name);
    if (!hb) return "⚫ not started";
    return hb.status;
  };

  const getMode = (name: string): string | null => {
    if (ping) {
      const found = ping.components.find((c) => c.component === name);
      return found?.mode as string || null;
    }
    const hb = health?.components.find((c) => c.component === name);
    return hb?.mode as string || null;
  };

  const getMeta = (name: string) => {
    if (ping) {
      const found = ping.components.find((c) => c.component === name);
      if (found) return Object.entries(found).filter(([k]) => !["component", "timestamp", "mode"].includes(k));
    }
    const hb = health?.components.find((c) => c.component === name);
    if (hb) return Object.entries(hb).filter(([k]) => !["component", "status", "lastBeat", "ageSec", "host", "pid", "mode"].includes(k));
    return [];
  };

  const statusColor = (name: string) => {
    const s = getStatus(name);
    if (s.includes("alive") || s.includes("running")) return "#22c55e33";
    if (s.includes("stale")) return "#f59e0b33";
    return "#33333333";
  };

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 13, color: "#888", fontWeight: 600 }}>Live Pipeline Status</span>
        <button
          onClick={doPing}
          disabled={pinging}
          style={{
            fontSize: 10, padding: "3px 10px", borderRadius: 4, cursor: "pointer",
            background: "#818cf822", color: "#818cf8", border: "1px solid #818cf844",
          }}
        >
          {pinging ? "pinging..." : "🏓 Ping"}
        </button>
        <span style={{ fontSize: 9, color: "#555" }}>
          {ping ? `${ping.count}/4 responded` : "DB heartbeat · auto-refreshes"}
        </span>
      </div>
      {!health && !ping ? (
        <div style={{ fontSize: 12, color: "#555" }}>API not reachable</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {ALL.map((name) => (
              <div
                key={name}
                style={{
                  background: "#1a1a2e", borderRadius: 6, padding: "8px 14px",
                  border: `1px solid ${statusColor(name)}`, minWidth: 120,
                }}
              >
                <div style={{ fontSize: 12, color: "#ccc", fontWeight: 600 }}>
                  {name}
                  {getMode(name) && (
                    <span style={{
                      fontSize: 8, marginLeft: 6, padding: "1px 5px", borderRadius: 3,
                      background: getMode(name) === "distributed" ? "#818cf822" : "#22c55e22",
                      color: getMode(name) === "distributed" ? "#818cf8" : "#22c55e",
                    }}>
                      {getMode(name)}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>{getStatus(name)}</div>
                {getMeta(name).map(([k, v]) => (
                  <div key={k} style={{ fontSize: 9, color: "#666", marginTop: 1 }}>{k}: {String(v)}</div>
                ))}
              </div>
            ))}
          </div>
          {health && (
            <div style={{ fontSize: 10, color: "#666", marginTop: 8 }}>
              Open positions: {health.open_positions} · Collector: {health.collector_running ? "🟢" : "⚫"}
            </div>
          )}
        </>
      )}
    </div>
  );
}

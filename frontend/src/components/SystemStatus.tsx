import { useState, useEffect, useCallback } from "react";

interface Component {
  component: string;
  timestamp?: string;
  mode?: string;
  [key: string]: unknown;
}

interface HealthData {
  components: { component: string; status: string; ageSec: number; host?: string; pid?: number; mode?: string; [key: string]: unknown }[];
  open_positions: number;
}

interface PingData {
  components: Component[];
  count: number;
}

interface DockerContainer {
  name: string;
  state: string;
  status: string;
}

const ALL = ["watcher", "analyzer", "trader", "executor"];

export default function SystemStatus() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [ping, setPing] = useState<PingData | null>(null);
  const [pinging, setPinging] = useState(false);
  const [docker, setDocker] = useState<DockerContainer[]>([]);
  const [actionMsg, setActionMsg] = useState("");

  useEffect(() => {
    const poll = () => {
      fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
      fetch("/api/docker/status").then((r) => r.json()).then((d) => setDocker(d.containers || [])).catch(() => {});
    };
    poll();
    const id = setInterval(poll, 10000);
    return () => clearInterval(id);
  }, []);

  const doPing = useCallback(() => {
    setPinging(true);
    fetch("/api/ping").then((r) => r.json()).then((d) => { setPing(d); setPinging(false); }).catch(() => setPinging(false));
  }, []);

  const doAction = useCallback((action: string, name: string) => {
    setActionMsg(`${action}ing ${name}...`);
    fetch(`/api/docker/${action}/${name}`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        setActionMsg(d.ok ? `${name} ${action}ed ✅` : `${name} failed: ${d.stderr}`);
        setTimeout(() => setActionMsg(""), 3000);
      })
      .catch(() => setActionMsg("API error"));
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

  const getDocker = (name: string) => docker.find((c) => c.name === name);

  const statusColor = (name: string) => {
    const s = getStatus(name);
    if (s.includes("alive") || s.includes("running")) return "#22c55e33";
    if (s.includes("stale")) return "#f59e0b33";
    return "#33333333";
  };

  const btnStyle = {
    fontSize: 9, padding: "2px 6px", borderRadius: 3, cursor: "pointer",
    border: "1px solid #333", background: "#1a1a2e", color: "#888",
    marginRight: 3,
  };

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 13, color: "#888", fontWeight: 600 }}>Live Pipeline Status</span>
        <button onClick={doPing} disabled={pinging}
          style={{ fontSize: 10, padding: "3px 10px", borderRadius: 4, cursor: "pointer",
            background: "#818cf822", color: "#818cf8", border: "1px solid #818cf844" }}>
          {pinging ? "pinging..." : "🏓 Ping"}
        </button>
        <button onClick={() => doAction("start", "all")}
          style={{ ...btnStyle, color: "#22c55e", borderColor: "#22c55e44" }}>▶ Start All</button>
        <button onClick={() => doAction("stop", "all")}
          style={{ ...btnStyle, color: "#ef4444", borderColor: "#ef444444" }}>⏹ Stop All</button>
        {actionMsg && <span style={{ fontSize: 10, color: "#f59e0b" }}>{actionMsg}</span>}
      </div>
      {!health && !ping ? (
        <div style={{ fontSize: 12, color: "#555" }}>API not reachable</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {ALL.map((name) => {
              const dc = getDocker(name);
              return (
                <div key={name} style={{
                  background: "#1a1a2e", borderRadius: 6, padding: "8px 14px",
                  border: `1px solid ${statusColor(name)}`, minWidth: 130,
                }}>
                  <div style={{ fontSize: 12, color: "#ccc", fontWeight: 600 }}>
                    {name}
                    {getMode(name) && (
                      <span style={{
                        fontSize: 8, marginLeft: 6, padding: "1px 5px", borderRadius: 3,
                        background: getMode(name) === "distributed" ? "#818cf822" : "#22c55e22",
                        color: getMode(name) === "distributed" ? "#818cf8" : "#22c55e",
                      }}>{getMode(name)}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>{getStatus(name)}</div>
                  {dc && (
                    <div style={{ fontSize: 9, color: "#555", marginTop: 1 }}>
                      container: {dc.state} {dc.status && `(${dc.status})`}
                    </div>
                  )}
                  {getMeta(name).map(([k, v]) => (
                    <div key={k} style={{ fontSize: 9, color: "#666", marginTop: 1 }}>{k}: {String(v)}</div>
                  ))}
                  <div style={{ marginTop: 4, display: "flex" }}>
                    <button onClick={() => doAction("start", name)} style={{ ...btnStyle, color: "#22c55e" }}>▶</button>
                    <button onClick={() => doAction("stop", name)} style={{ ...btnStyle, color: "#ef4444" }}>⏹</button>
                    <button onClick={() => doAction("restart", name)} style={{ ...btnStyle, color: "#f59e0b" }}>↻</button>
                  </div>
                </div>
              );
            })}
          </div>
          {health && (
            <div style={{ fontSize: 10, color: "#666", marginTop: 8 }}>
              Open positions: {health.open_positions}
            </div>
          )}
        </>
      )}
    </div>
  );
}

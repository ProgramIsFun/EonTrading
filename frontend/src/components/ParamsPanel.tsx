import type { BacktestParams } from "../types/backtest";

interface Props {
  params: BacktestParams;
  onChange: (params: BacktestParams) => void;
  onRun: () => void;
  loading: boolean;
}

const fields: { key: keyof BacktestParams; label: string; min: number; max: number; step: number }[] = [
  { key: "capital", label: "Capital ($)", min: 1000, max: 1000000, step: 1000 },
  { key: "threshold", label: "Sentiment Threshold", min: 0.1, max: 1.0, step: 0.05 },
  { key: "max_allocation", label: "Max Allocation (%)", min: 0.05, max: 1.0, step: 0.05 },
  { key: "stop_loss", label: "Stop Loss (%)", min: 0.01, max: 0.20, step: 0.01 },
  { key: "take_profit", label: "Take Profit (%)", min: 0.01, max: 0.50, step: 0.01 },
  { key: "max_hold_days", label: "Max Hold (days)", min: 1, max: 90, step: 1 },
];

export default function ParamsPanel({ params, onChange, onRun, loading }: Props) {
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 12 }}>Backtest Parameters</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {fields.map((f) => (
          <div key={f.key}>
            <label style={{ fontSize: 11, color: "#888" }}>
              {f.label}: <strong style={{ color: "#e0e0e0" }}>
                {f.key === "capital" ? `$${params[f.key].toLocaleString()}` :
                 f.key === "max_hold_days" ? params[f.key] :
                 `${(params[f.key] * 100).toFixed(0)}%`}
              </strong>
            </label>
            <input
              type="range"
              min={f.min} max={f.max} step={f.step}
              value={params[f.key]}
              onChange={(e) => onChange({ ...params, [f.key]: Number(e.target.value) })}
              style={{ width: "100%", accentColor: "#818cf8" }}
            />
          </div>
        ))}
      </div>
      <button
        onClick={onRun}
        disabled={loading}
        style={{
          marginTop: 12, padding: "8px 24px", background: loading ? "#555" : "#818cf8",
          color: "#fff", border: "none", borderRadius: 6, cursor: loading ? "wait" : "pointer",
          fontSize: 14, fontWeight: 600,
        }}
      >
        {loading ? "Running..." : "Run Backtest"}
      </button>
    </div>
  );
}

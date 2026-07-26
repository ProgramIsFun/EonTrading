import type { BacktestParams } from "../types/backtest";
import { SHARED_SLIDER_FIELDS, formatSliderValue } from "../constants";
import type { SliderField } from "../constants";

interface Props {
  params: BacktestParams;
  onChange: (params: BacktestParams) => void;
  onRun: () => void;
  loading: boolean;
}

const fields: SliderField[] = SHARED_SLIDER_FIELDS;

export default function ParamsPanel({ params, onChange, onRun, loading }: Props) {
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 12 }}>Backtest Parameters</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {fields.map((f) => (
          <div key={f.key}>
            <label style={{ fontSize: 11, color: "#888" }}>
              {f.label}: <strong style={{ color: "#e0e0e0" }}>
                {formatSliderValue(f.key, params[f.key as keyof BacktestParams] as number)}
              </strong>
            </label>
            <input
              type="range"
              min={f.min} max={f.max} step={f.step}
              value={params[f.key as keyof BacktestParams] as number}
              onChange={(e) => onChange({ ...params, [f.key]: Number(e.target.value) })}
              style={{ width: "100%", accentColor: "#818cf8" }}
            />
          </div>
        ))}
      </div>
      <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 16 }}>
        <label style={{ fontSize: 13, color: "#ccc", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={params.trailing_sl}
            onChange={(e) => onChange({ ...params, trailing_sl: e.target.checked })}
            style={{ accentColor: "#818cf8" }}
          />
          Trailing Stop-Loss
        </label>
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
    </div>
  );
}

import type { BacktestParams } from "./types/backtest";

export const API_BASE = import.meta.env.VITE_API_BASE || "";

export const DEFAULT_BACKTEST_PARAMS: BacktestParams = {
  capital: 70000,
  threshold: 0.4,
  max_allocation: 0.2,
  stop_loss: 0.05,
  take_profit: 0.10,
  max_hold_days: 30,
  trailing_sl: false,
};

export const DEFAULT_LIVE_PARAMS = {
  ...DEFAULT_BACKTEST_PARAMS,
  sl_check_hours: 24,
  analyzer: "keyword",
  cost_model: "us_stocks",
  news_source: "sample",
};

export interface SliderField {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
}

export const SHARED_SLIDER_FIELDS: SliderField[] = [
  { key: "capital", label: "Capital ($)", min: 1000, max: 1000000, step: 1000 },
  { key: "threshold", label: "Sentiment Threshold", min: 0.1, max: 1.0, step: 0.05 },
  { key: "max_allocation", label: "Max Allocation (%)", min: 0.05, max: 1.0, step: 0.05 },
  { key: "stop_loss", label: "Stop Loss (%)", min: 0.01, max: 0.20, step: 0.01 },
  { key: "take_profit", label: "Take Profit (%)", min: 0.01, max: 0.50, step: 0.01 },
  { key: "max_hold_days", label: "Max Hold (days)", min: 1, max: 90, step: 1 },
];

export const LIVE_EXTRA_SLIDERS: SliderField[] = [
  ...SHARED_SLIDER_FIELDS,
  { key: "sl_check_hours", label: "SL/TP Check Interval (hours)", min: 1, max: 168, step: 1 },
];

export function formatSliderValue(key: string, val: number): string {
  if (key === "capital") return `$${val.toLocaleString()}`;
  if (key === "max_hold_days" || key === "sl_check_hours") return String(val);
  return `${(val * 100).toFixed(0)}%`;
}

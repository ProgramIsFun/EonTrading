export interface Trade {
  symbol: string;
  action: string;
  date: string;
  price: number;
  shares: number;
  sentiment: number;
  pnl: number;
  headline: string;
}

export interface BacktestResult {
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  total_trades: number;
  win_rate: number;
  equity_curve: number[];
  trades: Trade[];
}

export interface BacktestParams {
  capital: number;
  threshold: number;
  max_allocation: number;
  stop_loss: number;
  take_profit: number;
  max_hold_days: number;
  trailing_sl: boolean;
}

"""Test backtest: SMA crossover on AAPL with and without costs."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from src.data.storage import ClickHouseStorage
from src.strategies import SMACrossover, RSIMeanReversion
from src.backtest import run_backtest
from src.common.costs import US_STOCKS, ZERO

storage = ClickHouseStorage()

# Get 5 years of AAPL daily data
start = datetime(2021, 1, 1)
end = datetime(2026, 4, 20)
df = storage.query_ohlcv("AAPL", "1d", start, end)
print(f"AAPL: {len(df)} rows ({df['timestamp'].min()} to {df['timestamp'].max()})\n")

# Test strategies with and without costs
for strategy in [SMACrossover(20, 50), SMACrossover(10, 30), RSIMeanReversion()]:
    print(f"{'='*50}")
    r1 = run_backtest(df, strategy, symbol="AAPL", cost_model=ZERO)
    r2 = run_backtest(df, strategy, symbol="AAPL", cost_model=US_STOCKS)
    print(f"[No costs]  {r1.summary()}\n")
    print(f"[US costs]  {r2.summary()}\n")
    print(f"  Cost impact: {r1.total_return_pct - r2.total_return_pct:.2f}% return lost to costs\n")

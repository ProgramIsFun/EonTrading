# EonTrading

Trading system: data collection, backtesting, and live execution.

## Structure

```
src/
├── data/           # Market data collection & storage
│   ├── providers/  # Data source adapters (yfinance, finnhub, etc.)
│   └── utils/      # MongoDB helpers
├── strategies/     # Strategy definitions (shared by backtest + live)
├── backtest/       # Backtesting engine
├── live/           # Live trading execution
│   └── brokers/    # Broker API integrations (Futu, Webull, etc.)
└── common/         # Shared models, config, utilities
tasks/              # Jupyter notebooks for ad-hoc tasks
docs/               # Documentation & reference material
config/             # Environment configs (gitignored)
```

## Setup

```bash
uv sync                    # core deps
uv sync --extra backtest   # + backtesting
uv sync --extra futu       # + Futu broker
uv sync --extra dev        # + jupyter/notebooks
```

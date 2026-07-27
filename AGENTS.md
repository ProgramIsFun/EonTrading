# Agents

## Environment

Always use the project venv, never the global Python:

```bash
source .venv/bin/activate
```

Then run commands like:

```bash
python -m pytest tests/ -v
```

## Symbol Format

Standard format: `TICKER.EXCHANGE` (Yahoo Finance convention).

| Market | Format | Example |
|--------|--------|---------|
| US | `TICKER` | `AAPL`, `TSLA` |
| Hong Kong | `TICKER.HK` | `0700.HK` |
| Japan | `TICKER.T` | `6758.T` |
| Shanghai | `TICKER.SS` | `600519.SS` |
| Shenzhen | `TICKER.SZ` | `000001.SZ` |

US stocks use plain tickers — no suffix. Everyone recognizes `AAPL`.

**Rules:**
- Analyzers output standard `TICKER.EXCHANGE` format in events
- Event channels (news, sentiment, trade) carry this format as-is
- Logs and API responses use this format
- Each broker maps to its native format at execution time via `SYMBOL_MAP`:
  - `FutuBroker`: `0700.HK` → `HK.00700`
  - `IBKRBroker`: `0700.HK` → `0700.HK` (pass-through)
  - `AlpacaBroker`: `0700.HK` → `0700.HK` (pass-through)
- Analyzer and event channels never care about broker specifics
- When adding a new broker, implement `SYMBOL_MAP` for its native format

## Tests

- Test framework: pytest with pytest-asyncio
- Run all unit tests: `python -m pytest tests/ -v`
- Run specific test: `python -m pytest tests/test_brokers.py -v`
- Tests requiring external services (Redis, Kafka, Futu, network) are marked and excluded by default
- **Integration tests**: marked `integration`, requires running MongoDB on localhost:27017
  - Run: `python -m pytest -m integration -v`
  - Uses separate database `EonTradingDB_test`, dropped after each test
  - Skipped by default in `pytest` run

## Type Checking

- Static analysis: mypy
- Run type check: `python -m mypy src/`
- Config in `pyproject.toml` under `[tool.mypy]`
- Current baseline: 0 errors
- New code should not introduce new mypy errors

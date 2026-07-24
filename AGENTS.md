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

No single format is universal across all markets. US tickers (`AAPL`, `TSLA`) are the only truly universal ones — same across every provider and broker.

For non-US stocks, every provider uses its own convention (Yahoo: `0700.HK`, Bloomberg: `700 HK`, Futu: `HK.00700`). Don't assume one format fits all.

**Rules:**
- US stocks: use plain ticker (`AAPL`, `TSLA`) everywhere — events, logs, APIs, prompts
- Non-US stocks: use the data source's native format internally, map to broker format at execution time
- Event channels carry the symbol as-is from the analyzer — no forced normalization
- Each broker has its own `SYMBOL_MAP` to translate from internal format to broker-native format
- When adding a new broker or data source, document its symbol convention in the broker class docstring

## Tests

- Test framework: pytest with pytest-asyncio
- Run tests: `python -m pytest tests/ -v`
- Run specific test: `python -m pytest tests/test_brokers.py -v`
- Tests requiring external services (Redis, Kafka, Futu, network) are marked and excluded by default

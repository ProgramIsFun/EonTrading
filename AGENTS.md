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

## Tests

- Test framework: pytest with pytest-asyncio
- Run tests: `python -m pytest tests/ -v`
- Run specific test: `python -m pytest tests/test_brokers.py -v`
- Tests requiring external services (Redis, Kafka, Futu, network) are marked and excluded by default

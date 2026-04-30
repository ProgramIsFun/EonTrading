FROM python:3.11-slim

WORKDIR /app

# 1. Install deps first (cached unless pyproject.toml changes)
COPY pyproject.toml .
RUN pip install --no-cache-dir yfinance pymongo[srv] python-dotenv requests \
    fastapi uvicorn redis pandas numpy tqdm clickhouse-connect finnhub-python

# 2. Copy source (only this layer rebuilds on code changes)
COPY . .
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import src.common.events; print('ok')" || exit 1

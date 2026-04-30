FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . || \
    (echo "WARNING: editable install failed, installing core deps" && \
     pip install --no-cache-dir requests pymongo[srv] redis python-dotenv yfinance fastapi uvicorn)

COPY . .
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import src.common.events; print('ok')" || exit 1

FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[redis]"

ENV PYTHONPATH=/app
COPY . .

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import src.common.events; print('ok')" || exit 1

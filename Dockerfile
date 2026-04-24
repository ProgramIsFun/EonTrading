FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir requests tweepy pymongo redis python-dotenv

COPY . .
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "from src.common.events import CHANNEL_NEWS" || exit 1

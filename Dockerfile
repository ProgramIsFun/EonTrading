FROM python:3.10-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir requests tweepy pymongo redis python-dotenv

COPY . .
ENV PYTHONPATH=/app

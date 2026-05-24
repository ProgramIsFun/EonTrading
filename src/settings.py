from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": ""}

    # MongoDB
    mongodb_uri: str = ""
    mongodb_user: str = ""
    mongodb_pass: str = ""
    mongodb_clustername: str = ""

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # ClickHouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_db: str = "eontrading"

    # News sources
    newsapi_key: str = ""
    finnhub_key: str = ""
    twitter_bearer_token: str = ""
    persist_news: bool = False
    publish_pipeline: bool = True

    # Sentiment
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    opencode_api_key: str = ""
    opencode_base_url: str = "https://opencode.ai/zen/v1"
    opencode_model: str = "big-pickle"
    openai_api_version: str = ""

    # Broker
    broker: str = "log"
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    futu_real: bool = False
    futu_confirm: str = "poll"

    # Trading params
    threshold: float = 0.4
    min_confidence: float = 0.15
    max_allocation: float = 0.2
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    sl_check_interval: int = 60

    # API
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    api_key: str = ""

    # Price
    price_source: str = "yfinance"
    price_timeout: int = 15


settings = Settings()

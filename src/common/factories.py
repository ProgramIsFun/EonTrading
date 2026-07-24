from src.live.brokers.broker import AlpacaBroker, FutuBroker, IBKRBroker, PaperBroker
from src.settings import settings
from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer


def build_analyzer() -> tuple:
    if settings.analyzer == "llm":
        analyzer = LLMSentimentAnalyzer()
        return analyzer, f"LLM ({analyzer.model})"
    return KeywordSentimentAnalyzer(), "Keyword (free)"


def build_broker():
    broker_name = settings.broker.lower()
    if broker_name == "futu":
        return FutuBroker(simulate=not settings.futu_real, confirm_mode=settings.futu_confirm)
    if broker_name == "ibkr":
        return IBKRBroker()
    if broker_name == "alpaca":
        return AlpacaBroker()
    return PaperBroker()

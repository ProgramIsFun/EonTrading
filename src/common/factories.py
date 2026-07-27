from src.settings import settings

# --- Broker registry ---
# To add a new broker: import it and add one line below.
# The factory function never needs to change.

from src.live.brokers import AlpacaBroker, FutuBroker, IBKRBroker, PaperBroker

BROKERS = {
    "paper": lambda: PaperBroker(persist_cash=True),
    "futu": lambda: FutuBroker(simulate=not settings.futu_real, confirm_mode=settings.futu_confirm),
    "ibkr": lambda: IBKRBroker(),
    "alpaca": lambda: AlpacaBroker(),
}


def build_broker():
    name = settings.broker.lower()
    factory = BROKERS.get(name)
    if factory is None:
        raise ValueError(f"Unknown broker '{name}'. Valid: {list(BROKERS)}")
    return factory()


# --- Analyzer registry ---
# To add a new analyzer: import it and add one line below.

from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer

ANALYZERS = {
    "llm": lambda: (LLMSentimentAnalyzer(), f"LLM ({LLMSentimentAnalyzer().model})"),
    "keyword": lambda: (KeywordSentimentAnalyzer(), "Keyword (free)"),
}


def build_analyzer():
    name = settings.analyzer.lower()
    factory = ANALYZERS.get(name)
    if factory is None:
        raise ValueError(f"Unknown analyzer '{name}'. Valid: {list(ANALYZERS)}")
    return factory()

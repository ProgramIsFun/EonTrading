"""AnalyzerService: subscribes to [news], queries positions, scores sentiment, publishes to [sentiment]."""
import asyncio
import logging
from datetime import datetime

from src.common.clock import utcnow
from src.common.log_handler import ComponentFilter
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS, CHANNEL_SENTIMENT, NewsEvent
from src.strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("analyzer"))

MAX_NEWS_AGE_SEC = 600  # skip news older than 10 minutes


class AnalyzerService:
    """Listens to raw news, analyzes with portfolio context, publishes sentiment."""

    def __init__(self, bus: EventBus, analyzer: BaseSentimentAnalyzer | None = None,
                 get_positions=None, portfolio_source=None, max_age_sec: int = MAX_NEWS_AGE_SEC):
        self.bus = bus
        self.analyzer = analyzer or KeywordSentimentAnalyzer()
        self.get_positions = get_positions  # legacy callable → {symbol: shares}
        self.portfolio_source = portfolio_source  # optional PortfolioSource (preferred)
        self.max_age_sec = max_age_sec

    async def start(self):
        await self.bus.subscribe(CHANNEL_NEWS, self._on_news)

    def _is_stale(self, event: NewsEvent) -> bool:
        if not event.timestamp or self.max_age_sec <= 0:
            return False
        try:
            ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
            age = (utcnow().replace(tzinfo=None) - ts).total_seconds()
            if age > self.max_age_sec:
                logger.info("Skipping stale news (%.0fs old): %s", age, event.headline[:60])
                return True
        except (ValueError, TypeError):
            pass
        return False

    async def _on_news(self, msg: dict):
        event = NewsEvent.from_dict(msg)
        if self._is_stale(event):
            return
        logger.info("Analyzing: %s", event.headline[:80])
        t0 = asyncio.get_event_loop().time()
        # Run synchronous MongoDB + LLM calls off the event loop
        positions, recent_orders = None, None
        if self.portfolio_source is not None:
            try:
                snapshot = await self.portfolio_source.get_snapshot()
                positions = {p.symbol: p.qty for p in snapshot.positions if p.qty > 0}
                recent_orders = snapshot.recent_orders
                logger.info("Portfolio snapshot (%s): %d positions, %d recent orders, cash=%.2f",
                            snapshot.source, len(positions), len(recent_orders), snapshot.cash)
            except Exception as e:
                logger.warning("Portfolio snapshot failed (%s) — analyzing without portfolio context", e, exc_info=True)
        elif self.get_positions:
            positions = await asyncio.to_thread(self.get_positions)
        t_pos = asyncio.get_event_loop().time()
        try:
            sentiment = await asyncio.to_thread(self.analyzer.analyze, event, positions, recent_orders)
        except Exception as e:
            logger.error("Analysis failed for %s: %s", event.headline[:60], e, exc_info=True)
            return
        t_done = asyncio.get_event_loop().time()
        logger.info("Done in %.1fs (positions: %.2fs, llm: %.2fs): %s",
                     t_done - t0, t_pos - t0, t_done - t_pos, event.headline[:60])
        if sentiment.confidence > 0:
            await self.bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
            logger.info("[%+.2f] %s", sentiment.sentiment, sentiment.headline[:80])

"""News source loader — registry pattern.

To add a new source: import it and add one line to NEWS_SOURCES.
The build_news_sources() function never needs to change.
"""
from collections.abc import Callable, Sequence

from src.data.news.finnhub_source import FinnhubSource
from src.data.news.newsapi_source import NewsAPISource
from src.data.news.reddit_source import RedditSource
from src.data.news.rss_source import RSSSource
from src.data.news.twitter_source import TwitterSource
from src.settings import settings

# Each entry: (name, source_class, available_check_fn)
# available_check_fn receives no args → returns True if source should be included.
NEWS_SOURCES: list[tuple[str, type, Callable[[], bool]]] = [
    ("RSS", RSSSource, lambda: True),
    ("Reddit", RedditSource, lambda: RedditSource().available),
    ("NewsAPI", NewsAPISource, lambda: bool(settings.newsapi_key)),
    ("Finnhub", FinnhubSource, lambda: bool(settings.finnhub_key)),
    ("Twitter", TwitterSource, lambda: bool(settings.twitter_bearer_token)),
]


def build_news_sources() -> tuple[list, list[str]]:
    sources: list = []
    source_names: list[str] = []

    for name, cls, is_available in NEWS_SOURCES:
        if is_available():
            sources.append(cls())
            source_names.append(name)

    return sources, source_names

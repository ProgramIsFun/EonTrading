from collections.abc import Sequence

from src.data.news.finnhub_source import FinnhubSource
from src.data.news.newsapi_source import NewsAPISource
from src.data.news.reddit_source import RedditSource
from src.data.news.rss_source import RSSSource
from src.data.news.twitter_source import TwitterSource
from src.settings import settings


def build_news_sources() -> tuple[list, list[str]]:
    sources: list = [RSSSource()]
    source_names: list[str] = ["RSS"]

    reddit = RedditSource()
    if reddit.available:
        sources.append(reddit)
        source_names.append("Reddit")

    if settings.newsapi_key:
        sources.append(NewsAPISource())
        source_names.append("NewsAPI")

    if settings.finnhub_key:
        sources.append(FinnhubSource())
        source_names.append("Finnhub")

    if settings.twitter_bearer_token:
        sources.append(TwitterSource())
        source_names.append("Twitter")

    return sources, source_names

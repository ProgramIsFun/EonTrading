"""Twitter/X news source — stub interface for custom implementation.

Plug in your own Twitter client (official API, or any library you prefer).
Must return list[NewsEvent] from fetch_latest().

Example with official API ($100/month):
  pip install tweepy
  source = TwitterSource(accounts=["elonmusk", "realDonaldTrump"], bearer_token="...")
"""
from src.common.events import NewsEvent
from .newsapi_source import NewsSource


class TwitterSource(NewsSource):
    """Fetch tweets from specified accounts. Implement with your preferred client."""

    def __init__(self, accounts: list[str] = None, bearer_token: str = None):
        self.accounts = accounts or []
        self.bearer_token = bearer_token
        self._seen: set[str] = set()

    def fetch_latest(self) -> list[NewsEvent]:
        # TODO: Implement with your preferred Twitter/X client
        # Should return list of NewsEvent with:
        #   source="twitter/{account}"
        #   headline=tweet text
        #   timestamp=tweet created_at
        #   url=tweet URL
        raise NotImplementedError(
            "TwitterSource requires a custom implementation. "
            "See docstring for setup instructions."
        )

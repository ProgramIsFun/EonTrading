"""Twitter/X news source — official API + placeholder for alternative clients.

Official API setup:
  1. Sign up at https://developer.x.com
  2. Get Bearer Token (Basic tier: $100/month)
  3. pip install tweepy
  4. Set TWITTER_BEARER_TOKEN env var

Usage:
  source = TwitterSource(accounts=["elonmusk", "realDonaldTrump"])
"""
import os
from datetime import datetime
from src.common.events import NewsEvent
from .newsapi_source import NewsSource


class TwitterSource(NewsSource):
    """Fetch tweets from specified accounts."""

    def __init__(self, accounts: list[str] = None, bearer_token: str = None, use_official: bool = True):
        super().__init__()
        self.accounts = accounts or ["elonmusk", "realDonaldTrump"]
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")
        self.use_official = use_official

    def fetch_latest(self) -> list[NewsEvent]:
        if self.use_official:
            return self._fetch_official()
        else:
            return self._fetch_alternative()

    def _fetch_official(self) -> list[NewsEvent]:
        """Fetch via official X API using tweepy."""
        if not self.bearer_token:
            return []
        try:
            import tweepy
        except ImportError:
            print("TwitterSource: pip install tweepy")
            return []

        client = tweepy.Client(bearer_token=self.bearer_token)
        events = []
        for account in self.accounts:
            try:
                user = client.get_user(username=account)
                if not user.data:
                    continue
                tweets = client.get_users_tweets(
                    user.data.id, max_results=10,
                    tweet_fields=["created_at", "text"],
                )
                if not tweets.data:
                    continue
                for tweet in tweets.data:
                    tid = str(tweet.id)
                    if self._check_seen(tid):
                        continue
                    events.append(NewsEvent(
                        source=f"twitter/{account}",
                        headline=tweet.text[:280],
                        timestamp=tweet.created_at.isoformat() if tweet.created_at else datetime.utcnow().isoformat() + "Z",
                        url=f"https://x.com/{account}/status/{tweet.id}",
                        body=tweet.text,
                    ))
            except Exception as e:
                print(f"Twitter error (@{account}): {e}")
        return events

    def _fetch_alternative(self) -> list[NewsEvent]:
        """Placeholder for alternative client (e.g. twscrape).

        Implement your own logic here. Must return list[NewsEvent].
        Example structure:

            # Your code here — fetch tweets however you prefer
            # For each tweet, return:
            events.append(NewsEvent(
                source=f"twitter/{account}",
                headline=tweet_text,
                timestamp=tweet_time_iso,
                url=tweet_url,
                body=tweet_text,
            ))
        """
        # TODO: Implement your alternative client here
        print("TwitterSource: alternative client not implemented yet")
        return []

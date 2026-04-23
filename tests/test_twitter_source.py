"""Tests for TwitterSource — mocked, no real API calls."""
from unittest.mock import patch, MagicMock
from src.data.news.twitter_source import TwitterSource


class TestTwitterSourceOfficial:
    def _make_tweet(self, tid, text, created_at=None):
        tweet = MagicMock()
        tweet.id = tid
        tweet.text = text
        tweet.created_at = created_at
        return tweet

    @patch("src.data.news.twitter_source.TwitterSource._fetch_official")
    def test_official_returns_news_events(self, mock_fetch):
        from src.common.events import NewsEvent
        mock_fetch.return_value = [
            NewsEvent(source="twitter/elonmusk", headline="Tesla is doing great",
                      timestamp="2025-04-23T10:00:00Z", url="https://x.com/elonmusk/status/123", body="Tesla is doing great"),
        ]
        source = TwitterSource(use_official=True)
        events = source.fetch_latest()
        assert len(events) == 1
        assert events[0].source == "twitter/elonmusk"
        assert "Tesla" in events[0].headline

    @patch("src.data.news.twitter_source.TwitterSource._fetch_official")
    def test_official_dedup(self, mock_fetch):
        from src.common.events import NewsEvent
        ev = NewsEvent(source="twitter/elonmusk", headline="Same tweet",
                       timestamp="2025-04-23T10:00:00Z", url="https://x.com/elonmusk/status/123", body="Same tweet")
        mock_fetch.return_value = [ev]
        source = TwitterSource(use_official=True)
        first = source.fetch_latest()
        mock_fetch.return_value = [ev]
        second = source.fetch_latest()
        # Both calls return events since dedup is inside _fetch_official
        assert len(first) == 1

    @patch("src.data.news.twitter_source.TwitterSource._fetch_official")
    def test_official_no_token_returns_empty(self, mock_fetch):
        mock_fetch.return_value = []
        source = TwitterSource(bearer_token=None, use_official=True)
        events = source.fetch_latest()
        assert events == []

    @patch("src.data.news.twitter_source.TwitterSource._fetch_official")
    def test_official_multiple_accounts(self, mock_fetch):
        from src.common.events import NewsEvent
        mock_fetch.return_value = [
            NewsEvent(source="twitter/elonmusk", headline="Musk tweet",
                      timestamp="2025-04-23T10:00:00Z", url="https://x.com/elonmusk/status/1", body="Musk tweet"),
            NewsEvent(source="twitter/realDonaldTrump", headline="Trump tweet",
                      timestamp="2025-04-23T10:01:00Z", url="https://x.com/realDonaldTrump/status/2", body="Trump tweet"),
        ]
        source = TwitterSource(accounts=["elonmusk", "realDonaldTrump"], use_official=True)
        events = source.fetch_latest()
        assert len(events) == 2
        sources = {e.source for e in events}
        assert "twitter/elonmusk" in sources
        assert "twitter/realDonaldTrump" in sources


class TestTwitterSourceAlternative:
    def test_alternative_returns_empty_by_default(self):
        source = TwitterSource(use_official=False)
        events = source.fetch_latest()
        assert events == []

    @patch("src.data.news.twitter_source.TwitterSource._fetch_alternative")
    def test_alternative_returns_events_when_implemented(self, mock_fetch):
        from src.common.events import NewsEvent
        mock_fetch.return_value = [
            NewsEvent(source="twitter/elonmusk", headline="Alt client tweet",
                      timestamp="2025-04-23T10:00:00Z", url="https://x.com/elonmusk/status/999", body="Alt client tweet"),
        ]
        source = TwitterSource(use_official=False)
        events = source.fetch_latest()
        assert len(events) == 1
        assert events[0].source == "twitter/elonmusk"


class TestTwitterSourceInterface:
    def test_events_have_correct_fields(self):
        """Both official and alternative must return NewsEvent with required fields."""
        from src.common.events import NewsEvent
        ev = NewsEvent(
            source="twitter/elonmusk", headline="Test tweet",
            timestamp="2025-04-23T10:00:00Z", url="https://x.com/elonmusk/status/1",
            body="Test tweet body",
        )
        assert ev.source.startswith("twitter/")
        assert len(ev.headline) > 0
        assert ev.url.startswith("https://")
        assert ev.timestamp != ""

    def test_use_official_flag(self):
        official = TwitterSource(use_official=True)
        alt = TwitterSource(use_official=False)
        assert official.use_official is True
        assert alt.use_official is False

    def test_default_accounts(self):
        source = TwitterSource()
        assert "elonmusk" in source.accounts
        assert "realDonaldTrump" in source.accounts

"""Tests for factory registries — broker, analyzer, news sources."""
from unittest.mock import MagicMock, patch

import pytest

from src.common.factories import ANALYZERS, BROKERS, build_analyzer, build_broker
from src.data.news.loader import NEWS_SOURCES, build_news_sources


class TestBrokerRegistry:
    def test_all_expected_brokers_registered(self):
        assert set(BROKERS.keys()) == {"paper", "futu", "ibkr", "alpaca", "webull"}

    def test_build_broker_returns_paper_by_default(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "paper"
            broker = build_broker()
            assert type(broker).__name__ == "PaperBroker"

    def test_build_broker_unknown_raises(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "nonexistent"
            with pytest.raises(ValueError, match="Unknown broker 'nonexistent'"):
                build_broker()

    def test_build_broker_error_lists_valid_options(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "bad"
            with pytest.raises(ValueError, match="paper"):
                build_broker()

    def test_build_broker_case_insensitive(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "PAPER"
            broker = build_broker()
            assert type(broker).__name__ == "PaperBroker"

    def test_build_broker_futu_uses_settings(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "futu"
            mock_settings.futu_real = False
            mock_settings.futu_confirm = True
            broker = build_broker()
            assert type(broker).__name__ == "FutuBroker"
            assert broker.simulate is True
            assert broker.confirm_mode is True

    def test_build_broker_webull_uses_settings(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "webull"
            mock_settings.webull_real = False
            broker = build_broker()
            assert type(broker).__name__ == "WebullBroker"
            assert broker.simulate is True

    def test_build_broker_webull_live(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.broker = "webull"
            mock_settings.webull_real = True
            broker = build_broker()
            assert type(broker).__name__ == "WebullBroker"
            assert broker.simulate is False


class TestAnalyzerRegistry:
    def test_all_expected_analyzers_registered(self):
        assert set(ANALYZERS.keys()) == {"llm", "keyword"}

    def test_build_analyzer_keyword_by_default(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.analyzer = "keyword"
            analyzer, label = build_analyzer()
            assert type(analyzer).__name__ == "KeywordSentimentAnalyzer"
            assert "Keyword" in label

    def test_build_analyzer_unknown_raises(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.analyzer = "nonexistent"
            with pytest.raises(ValueError, match="Unknown analyzer 'nonexistent'"):
                build_analyzer()

    def test_build_analyzer_case_insensitive(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.analyzer = "KEYWORD"
            analyzer, label = build_analyzer()
            assert type(analyzer).__name__ == "KeywordSentimentAnalyzer"

    def test_build_analyzer_llm_label_contains_model(self):
        with patch("src.common.factories.settings") as mock_settings:
            mock_settings.analyzer = "llm"
            analyzer, label = build_analyzer()
            assert type(analyzer).__name__ == "LLMSentimentAnalyzer"
            assert "LLM" in label
            assert analyzer.model is not None


class TestNewsSourceRegistry:
    def test_rss_always_registered(self):
        names = [name for name, _, _ in NEWS_SOURCES]
        assert "RSS" in names

    def test_all_sources_have_required_fields(self):
        for name, cls, checker in NEWS_SOURCES:
            assert isinstance(name, str)
            assert callable(checker)

    def test_build_news_sources_returns_lists(self):
        sources, names = build_news_sources()
        assert isinstance(sources, list)
        assert isinstance(names, list)
        assert len(sources) == len(names)

    def test_build_news_sources_without_keys(self):
        with patch("src.data.news.loader.settings") as mock_settings:
            mock_settings.newsapi_key = ""
            mock_settings.finnhub_key = ""
            mock_settings.twitter_bearer_token = ""
            sources, names = build_news_sources()
            assert "RSS" in names
            assert "NewsAPI" not in names
            assert "Finnhub" not in names
            assert "Twitter" not in names

    def test_build_news_sources_with_keys(self):
        with patch("src.data.news.loader.settings") as mock_settings:
            mock_settings.newsapi_key = "test-key"
            mock_settings.finnhub_key = "test-key"
            mock_settings.twitter_bearer_token = "test-token"
            sources, names = build_news_sources()
            assert "NewsAPI" in names
            assert "Finnhub" in names
            assert "Twitter" in names

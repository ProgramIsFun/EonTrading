"""Tests for position-aware sentiment analysis."""
import pytest
from unittest.mock import MagicMock, patch

from src.common.events import NewsEvent
from src.strategies.sentiment import (
    KeywordSentimentAnalyzer,
    LLMSentimentAnalyzer,
)

TARIFF_NEWS = NewsEvent(
    source="test", headline="Trump announces sweeping tariffs on China, Apple supply chain at risk",
    timestamp="2025-04-03T14:00:00Z",
)

HOLDINGS = {"AAPL": True, "NVDA": True}


def _mock_llm_response(content: str):
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=content))]
    mock_client.chat.completions.create.return_value = mock_resp
    return mock_client


class TestKeywordWithPositions:
    def test_ignores_positions(self):
        analyzer = KeywordSentimentAnalyzer()
        without = analyzer.analyze(TARIFF_NEWS)
        with_pos = analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)
        # Keyword analyzer doesn't use positions — same result
        assert without.sentiment == with_pos.sentiment
        assert without.confidence == with_pos.confidence
        assert without.symbols == with_pos.symbols

    def test_works_with_none_positions(self):
        analyzer = KeywordSentimentAnalyzer()
        result = analyzer.analyze(TARIFF_NEWS, positions=None)
        assert result.sentiment != 0 or result.confidence == 0


class TestLLMPromptSelection:
    @patch.object(LLMSentimentAnalyzer, "_get_client")
    def test_uses_position_prompt_when_holdings_provided(self, mock_get_client):
        mock_get_client.return_value = _mock_llm_response(
            '{"symbols":["AAPL"],"sector":"technology","sentiment":-0.8,"confidence":0.95,"urgency":"high"}'
        )

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)

        call_args = mock_get_client.return_value.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Current holdings" in prompt
        assert "AAPL" in prompt
        assert "NVDA" in prompt

    @patch.object(LLMSentimentAnalyzer, "_get_client")
    def test_uses_basic_prompt_without_holdings(self, mock_get_client):
        mock_get_client.return_value = _mock_llm_response(
            '{"symbols":["AAPL"],"sector":"technology","sentiment":-0.5,"confidence":0.7,"urgency":"normal"}'
        )

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        analyzer.analyze(TARIFF_NEWS)

        call_args = mock_get_client.return_value.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Current holdings" not in prompt

    @patch.object(LLMSentimentAnalyzer, "_get_client")
    def test_llm_returns_valid_sentiment_event(self, mock_get_client):
        mock_get_client.return_value = _mock_llm_response(
            '{"symbols":["AAPL","NVDA"],"sector":"technology","sentiment":-0.9,"confidence":0.95,"urgency":"high"}'
        )

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        result = analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)

        assert result.symbols == ["AAPL", "NVDA"]
        assert result.sentiment == -0.9
        assert result.confidence == 0.95
        assert result.urgency == "high"

    @patch.object(LLMSentimentAnalyzer, "_get_client")
    def test_llm_handles_empty_positions(self, mock_get_client):
        mock_get_client.return_value = _mock_llm_response(
            '{"symbols":["AAPL"],"sector":"","sentiment":-0.5,"confidence":0.7,"urgency":"normal"}'
        )

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        analyzer.analyze(TARIFF_NEWS, positions={})

        # Empty dict is falsy — uses basic prompt (no positions to report)
        call_args = mock_get_client.return_value.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Current holdings" not in prompt

    @patch.object(LLMSentimentAnalyzer, "_get_client")
    def test_llm_graceful_failure(self, mock_get_client):
        mock_get_client.return_value.chat.completions.create.side_effect = Exception("API down")

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        with pytest.raises(Exception, match="API down"):
            analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)

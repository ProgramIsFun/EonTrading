"""Tests for position-aware sentiment analysis."""
from unittest.mock import patch, MagicMock
from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer, LLM_PROMPT, LLM_PROMPT_WITH_POSITIONS
from src.common.events import NewsEvent


TARIFF_NEWS = NewsEvent(
    source="test", headline="Trump announces sweeping tariffs on China, Apple supply chain at risk",
    timestamp="2025-04-03T14:00:00Z",
)

HOLDINGS = {"AAPL": True, "NVDA": True}


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
    @patch("requests.post")
    def test_uses_position_prompt_when_holdings_provided(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"symbols":["AAPL"],"sector":"technology","sentiment":-0.8,"confidence":0.95,"urgency":"high"}'}}]
        }
        mock_post.return_value = mock_resp

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)

        call_args = mock_post.call_args
        messages = call_args[1]["json"]["messages"]
        prompt = messages[0]["content"]
        assert "Current holdings" in prompt
        assert "AAPL" in prompt
        assert "NVDA" in prompt

    @patch("requests.post")
    def test_uses_basic_prompt_without_holdings(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"symbols":["AAPL"],"sector":"technology","sentiment":-0.5,"confidence":0.7,"urgency":"normal"}'}}]
        }
        mock_post.return_value = mock_resp

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        analyzer.analyze(TARIFF_NEWS)

        call_args = mock_post.call_args
        messages = call_args[1]["json"]["messages"]
        prompt = messages[0]["content"]
        assert "Current holdings" not in prompt

    @patch("requests.post")
    def test_llm_returns_valid_sentiment_event(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"symbols":["AAPL","NVDA"],"sector":"technology","sentiment":-0.9,"confidence":0.95,"urgency":"high"}'}}]
        }
        mock_post.return_value = mock_resp

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        result = analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)

        assert result.symbols == ["AAPL", "NVDA"]
        assert result.sentiment == -0.9
        assert result.confidence == 0.95
        assert result.urgency == "high"

    @patch("requests.post")
    def test_llm_handles_empty_positions(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"symbols":["AAPL"],"sector":"","sentiment":-0.5,"confidence":0.7,"urgency":"normal"}'}}]
        }
        mock_post.return_value = mock_resp

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        result = analyzer.analyze(TARIFF_NEWS, positions={})

        # Empty dict is falsy — uses basic prompt (no positions to report)
        call_args = mock_post.call_args
        prompt = call_args[1]["json"]["messages"][0]["content"]
        assert "Current holdings" not in prompt

    @patch("requests.post")
    def test_llm_graceful_failure(self, mock_post):
        mock_post.side_effect = Exception("API down")

        analyzer = LLMSentimentAnalyzer(api_key="test-key")
        result = analyzer.analyze(TARIFF_NEWS, positions=HOLDINGS)

        assert result.sentiment == 0.0
        assert result.confidence == 0.0

import pandas as pd

from src.strategies import RSIMeanReversion, SMACrossover


def _make_df(prices):
    """Helper: create minimal OHLCV df from a list of close prices."""
    n = len(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [1000] * n,
    })


def test_sma_crossover_signal_values():
    s = SMACrossover(fast=3, slow=5)
    df = _make_df([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
    signals = s.generate_signals(df)
    assert set(signals.dropna().unique()).issubset({-1, 0, 1})


def test_sma_crossover_bullish():
    # Steadily rising prices -> fast > slow -> buy signal
    prices = list(range(1, 61))
    df = _make_df(prices)
    s = SMACrossover(fast=5, slow=20)
    signals = s.generate_signals(df)
    # After warmup, should be mostly buy signals
    late_signals = signals.iloc[25:]
    assert (late_signals == 1).all()


def test_sma_crossover_bearish():
    # Steadily falling prices -> fast < slow -> sell signal
    prices = list(range(60, 0, -1))
    df = _make_df(prices)
    s = SMACrossover(fast=5, slow=20)
    signals = s.generate_signals(df)
    late_signals = signals.iloc[25:]
    assert (late_signals == -1).all()


def test_sma_name():
    assert SMACrossover(10, 30).name() == "SMA(10,30)"


def test_rsi_oversold_generates_buy():
    # Sharp drop then flat -> RSI should go oversold -> buy
    prices = [100] * 20 + [100 - i * 3 for i in range(1, 16)]
    df = _make_df(prices)
    s = RSIMeanReversion(period=14, oversold=30, overbought=70)
    signals = s.generate_signals(df)
    assert 1 in signals.values


def test_rsi_overbought_generates_sell():
    # Sharp rise -> RSI should go overbought -> sell
    prices = [50] * 20 + [50 + i * 3 for i in range(1, 16)]
    df = _make_df(prices)
    s = RSIMeanReversion(period=14, oversold=30, overbought=70)
    signals = s.generate_signals(df)
    assert -1 in signals.values


def test_rsi_name():
    assert RSIMeanReversion().name() == "RSI(14,30,70)"


# --- LLM prompt symbol format ---

def test_llm_prompt_uses_yahoo_finance_format():
    """LLM prompt must show 4-digit HK tickers (Yahoo format), not 5-digit Futu format."""
    from src.strategies.sentiment import _build_llm_prompt

    prompt = _build_llm_prompt("Tencent beats earnings", "HK")

    # Correct 4-digit examples must be present
    for sym in ["0700.HK", "9988.HK", "0005.HK", "0388.HK", "0981.HK", "0883.HK"]:
        assert sym in prompt, f"Missing correct example: {sym}"

    # Wrong 5-digit examples must NOT appear (except in the explicit WRONG list)
    # Split at "WRONG" to separate correct section from wrong section
    correct_section = prompt.split("WRONG")[0]
    for bad_sym in ["00700.HK", "00005.HK", "00002.HK"]:
        assert bad_sym not in correct_section, (
            f"Wrong format {bad_sym} appears in correct examples section"
        )

    # Return example must use 4-digit format and single braces (valid JSON)
    assert '"0700.HK"' in prompt
    return_section = prompt.split("Return:")[1]
    assert "00700.HK" not in return_section
    assert "{{" not in return_section
    assert "}}" not in return_section


def test_llm_prompt_builder_includes_correct_format():
    """_build_llm_prompt should produce a prompt with valid Yahoo Finance tickers."""
    from src.strategies.sentiment import _build_llm_prompt

    prompt = _build_llm_prompt("Tencent beats earnings", "HK")
    assert "0700.HK" in prompt
    assert "WRONG" in prompt  # Wrong examples section exists
    # 00700.HK may appear in the "WRONG" section — that's fine
    # but it must NOT appear before the "WRONG" marker (i.e. not in correct examples)
    correct_section = prompt.split("WRONG")[0]
    assert "00700.HK" not in correct_section


def test_llm_prompt_for_us_market():
    """US-only prompt must not push HK symbols."""
    from src.strategies.sentiment import _build_llm_prompt

    prompt = _build_llm_prompt("Apple beats earnings", "US")
    assert "markets: US" in prompt
    assert "AAPL" in prompt
    assert "0700.HK" not in prompt
    assert "WRONG" not in prompt


def test_llm_prompt_for_hk_and_us():
    """Both markets enabled: HK and US guidance both present."""
    from src.strategies.sentiment import _build_llm_prompt

    prompt = _build_llm_prompt("Chip news", "HK, US")
    assert "markets: HK, US" in prompt
    assert "0700.HK" in prompt
    assert "AAPL" in prompt


def test_llm_prompt_empty_markets_returns_nothing():
    """No tradable markets → prompt instructs empty symbols."""
    from src.strategies.sentiment import _build_llm_prompt

    prompt = _build_llm_prompt("Some news", "")
    assert "empty symbols" in prompt
    assert "0700.HK" not in prompt

import pandas as pd
import numpy as np
import datetime as dt
import types

def test_tool_sentiment_smoke(monkeypatch):
    from agent import tools as T
    # avoid NLTK download in CI by stubbing _get_vader
    class FakeSIA:
        def polarity_scores(self, text):
            return {"compound": 0.9}
    monkeypatch.setattr(T, "_get_vader", lambda: FakeSIA())
    out = T.tool_sentiment("I love NVDA")
    assert "Sentiment:" in out

def test_portfolio_analysis_with_mocked_history(monkeypatch):
    from agent import tools as T

    def fake_download(symbols, period="6mo"):
        idx = pd.date_range(end=dt.date.today(), periods=10, freq="B")
        data = {s: np.linspace(100, 110, len(idx)) for s in symbols}
        return pd.DataFrame(data, index=idx)

    # patch yfinance.download used inside get_history
    monkeypatch.setattr(T.yf, "download", lambda syms, period="6mo", auto_adjust=True, progress=False: 
                        fake_download(syms if isinstance(syms, list) else [syms], period))

    text = T.tool_portfolio_analysis("50% NVDA, 30% TSLA, 20% bonds", risk_tolerance="moderate")
    assert "Expected annual return" in text
    assert "Sharpe" in text
    assert "HHI" in text

from __future__ import annotations
import os, re, json, logging, requests, pandas as pd, numpy as np, yfinance as yf
import datetime as dt
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional
from nltk.sentiment import SentimentIntensityAnalyzer
from agent.cache import get_cached_price, put_cached_price
from agent.portfolio import (
    parse_percent_alloc,
    expected_return,
    portfolio_volatility,
    sharpe_ratio,
    hhi_diversification,
    value_at_risk_normal,
    risk_fit_label,
)
import threading

from agent.config import FINNHUB_API_KEY, RISK_FREE_RATE 

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

def _finnhub_get(path: str, params: dict, timeout: int = 15):
    token = (FINNHUB_API_KEY or os.getenv("FINNHUB_API_KEY", ""))
    if not token:
        logging.warning("finnhub: missing FINNHUB_API_KEY")
        return None, "no-finnhub-key"

    url = f"https://finnhub.io/api/v1/{path.lstrip('/')}"
    p = dict(params or {})
    p["token"] = token

    try:
        r = requests.get(url, params=p, timeout=timeout)
        if r.status_code != 200:
            logging.warning("finnhub %s HTTP %s url=%s body=%r", path, r.status_code, r.url, r.text[:200])
            return None, f"http-{r.status_code}"
        try:
            return r.json(), "ok"
        except Exception:
            logging.warning("finnhub %s: non-JSON response", path)
            return None, "bad-json"
    except Exception as e:
        logging.exception("finnhub %s error: %s", path, e)
        return None, "exception"

def _finnhub_news_from_query(q: str, limit: int = 5):

    now = datetime.utcnow().date()
    start = now - timedelta(days=14)
    q_strip = (q or "").strip()

    if _TICKER_RE.match(q_strip.upper()):
        sym = map_symbol(q_strip.upper())  
        data, _ = _finnhub_get("company-news", {
            "symbol": sym,
            "from": start.isoformat(),
            "to": now.isoformat(),
        })
        if not isinstance(data, list) or not data:
            return []
        items = data[:max(1, int(limit))]
        return [f"- {it.get('headline','(no title)')} — {it.get('source','')}\n  {it.get('url','')}" for it in items]

    data, _ = _finnhub_get("news", {"category": "general"})
    if not isinstance(data, list) or not data:
        return []

    terms = [w.lower() for w in q_strip.split() if len(w) > 2]
    rows = []
    for it in data:
        head = (it.get("headline") or "")
        if terms and not any(t in head.lower() for t in terms):
            continue
        rows.append(f"- {head} — {it.get('source','')}\n  {it.get('url','')}")
        if len(rows) >= max(1, int(limit)):
            break

    if not rows:
        for it in data[:max(1, int(limit))]:
            rows.append(f"- {it.get('headline','(no title)')} — {it.get('source','')}\n  {it.get('url','')}")
    return rows

_vader = None
_vader_lock = threading.Lock()

def _get_vader():
    global _vader
    if _vader is not None:
        return _vader
    
    with _vader_lock:
        if _vader is not None:
            return _vader
        try:
            from nltk.sentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
        except LookupError:
            import nltk
            nltk.download("vader_lexicon", quiet=True)
            from nltk.sentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
        return _vader

try:
    import nltk
    nltk.data.find("sentiment/vader_lexicon.zip")
except LookupError:
    nltk.download("vader_lexicon", quiet=True)

RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.0425"))
BOND_MAP = {"BONDS": "BND"}

def map_symbol(sym: str) -> str:
    s = sym.strip().upper()
    return BOND_MAP.get(s, s)

def _today_str() -> str:
    return dt.date.today().isoformat()

def alpha_vantage_price(symbol: str, api_key: str, timeout: int = 15) -> Tuple[Optional[float], str]:
    url = "https://www.alphavantage.co/query"
    params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        js = r.json() or {}
        p = js.get("Global Quote", {}).get("05. price")
        if p is None:
            logging.warning("AlphaVantage: no price for %s; payload keys=%s", symbol, list(js.keys()))
            return None, "alpha_vantage:no_price"
        return float(p), "alpha_vantage"
    except Exception:
        logging.exception("AlphaVantage request failed for %s", symbol)
        return None, "alpha_vantage:error"

def get_realtime_price(symbol: str) -> Tuple[Optional[float], str]:
    """Price with cache -> AlphaVantage -> yfinance fallback."""
    sy = map_symbol(symbol)
    today = _today_str()

    # cache
    try:
        p = get_cached_price(sy, today)
        if p is not None:
            return float(p), "cache(csv)"
    except Exception:
        logging.exception("cache read failed for %s", sy)

    # alpha vantage
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if key:
        price, src = alpha_vantage_price(sy, key, timeout=15)
        if price is not None:
            try:
                put_cached_price(sy, today, price)
            except Exception:
                logging.exception("cache write failed for %s", sy)
            return price, src

    # yfinance
    try:
        t = yf.Ticker(sy)
        df = t.history(period="1d", interval="1m")
        if not df.empty:
            price = float(df["Close"].iloc[-1])
            try:
                put_cached_price(sy, today, price)
            except Exception:
                logging.exception("cache write failed for %s", sy)
            return price, "yfinance (intraday)"
    except Exception:
        logging.exception("yfinance intraday failed for %s", sy)

    return None, "unavailable"

def get_history(symbols: List[str], period: str = "6mo") -> Tuple[pd.DataFrame, str]:
    mapped = [map_symbol(s) for s in symbols]
    try:
        df = yf.download(mapped, period=period, auto_adjust=True, progress=False)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame()
        df = df.dropna(how="all")
        return df, "yfinance"
    except Exception:
        logging.exception("yfinance download failed; using synthetic history")
        dates = pd.date_range(end=dt.date.today(), periods=60, freq="B")
        data = {s: np.linspace(100, 120, num=len(dates)) + np.random.randn(len(dates)) for s in mapped}
        df = pd.DataFrame(data, index=dates)
        return df, "synthetic"

def tool_stock_query(q: str) -> str:
    try:
        import re
        m = re.search(r"([A-Za-z.\-]+)\s*$", (q or ""))
        if not m:
            return "Please provide a ticker symbol, e.g., 'price NVDA'."
        sym = map_symbol(m.group(1).upper())

        p, src = get_latest_price(sym)
        if p is None:
            return f"Could not fetch a price for {sym}.\n[source: {src}]"

        return f"{sym} ≈ {p:.2f} (asof: {_today_str()})\n[source: {src}]"
    except Exception:
        logging.exception("StockQuery failed")
        return "Sorry, price lookup failed.\n[source: StockQuery exception]"

def tool_portfolio_analysis(portfolio: Dict[str, float] | str, risk_tolerance: str | None = "moderate") -> str:
    """
    Accepts:
      • dict-like weights: {"AGG": 0.6, "LQD": 0.2, ...} or {"AGG": 60, "LQD": 20, ...}
      • JSON/Python dict string (possibly inside other text or backticks)
      • free text with percents: "50% NVDA, 30% TSLA, 20% bonds"
    """
    import ast, re

    def _normalize_from_dict(d: dict) -> Dict[str, float]:
        vals = {map_symbol(str(k)): float(v) for k, v in d.items()}
        total = sum(vals.values())
        if total <= 0:
            raise ValueError("Portfolio weights must sum to a positive value.")
        return {k: v / total for k, v in vals.items()}  

    def _try_parse_dict_strings(s: str) -> Optional[Dict[str, float]]:
        s = (s or "").strip().strip("` \n\r\t")
        s = s.replace("“", '"').replace("”", '"').replace("’", "'")
        blocks = [m.group(0) for m in re.finditer(r"\{.*?\}", s, flags=re.DOTALL)]
        candidates = blocks + ([s] if s not in blocks else [])
        for attempt in candidates:
            try:
                js = json.loads(attempt)
                if isinstance(js, dict) and js:
                    return _normalize_from_dict(js)
            except Exception:
                pass
            try:
                lit = ast.literal_eval(attempt)
                if isinstance(lit, dict) and lit:
                    return _normalize_from_dict(lit)
            except Exception:
                pass
        return None

    def _try_parse_key_value_pairs(s: str) -> Optional[Dict[str, float]]:
        pairs = re.findall(
            r'["\']?([A-Za-z][A-Za-z0-9.\-]{0,9})["\']?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)',
            s
        )
        if not pairs:
            return None
        d = {map_symbol(k): float(v) for k, v in pairs}
        return _normalize_from_dict(d)

    if isinstance(portfolio, str):
        weights = _try_parse_dict_strings(portfolio)
        if weights is None:
            weights = _try_parse_key_value_pairs(portfolio)
        if weights is None:
            weights = parse_percent_alloc(portfolio)
    else:
        weights = _normalize_from_dict(portfolio)

    symbols = list(dict.fromkeys(map_symbol(k) for k in weights.keys()))

    history, hsrc = get_history(symbols, period="6mo")
    returns = history.pct_change().dropna(how="any")

    exp_ret = expected_return(returns, weights)
    vol = portfolio_volatility(returns, weights)
    sharpe = sharpe_ratio(exp_ret, vol, RISK_FREE_RATE)
    hhi = hhi_diversification(weights)
    var = value_at_risk_normal(exp_ret, vol)
    fit = risk_fit_label(vol, risk_tolerance or "moderate")

    lines = [
        f"Symbols: {', '.join(symbols)} (history source: {hsrc})",
        f"Expected annual return: {exp_ret:.2%}",
        f"Annualized volatility: {vol:.2%}",
        f"Sharpe (rf={RISK_FREE_RATE:.2%}): {sharpe:.2f}",
        f"Diversification (HHI): {hhi:.3f} (lower is better)",
        f"Approx 5% annual VaR: {var:.2%}",
        f"Risk fit vs tolerance '{risk_tolerance}': {fit}",
    ]
    return "\n".join(lines)     

def tool_fraud_check(tx_json: str, *, known_counterparties: set[str] | None = None, policy: dict | None = None) -> str:
    try:
        tx = json.loads(tx_json)
    except Exception:
        return "Invalid JSON transaction. Expect keys: amount, counterparty, hour."
    from .fraud import simple_fraud_check
    suspicious, details = simple_fraud_check(tx, known_counterparties=known_counterparties or set(), policy=policy)
    return f"Suspicious: {suspicious}. Details: {details}"

def tool_sentiment(text: str) -> str:
    try:
        sia = _get_vader()
        scores = sia.polarity_scores(text or "")
        comp = scores["compound"]
        label = "positive" if comp >= 0.05 else "negative" if comp <= -0.05 else "neutral"
        return f"Sentiment: {label} (compound={comp:+.3f}) — source: VADER."
    except Exception as e:
        t = (text or "").lower()
        pos = any(w in t for w in ("love", "great", "bullish", "beat", "upside"))
        neg = any(w in t for w in ("hate", "bad", "bearish", "miss", "downside"))
        if pos and not neg:
            return "Sentiment: positive (simple fallback)."
        if neg and not pos:
            return "Sentiment: negative (simple fallback)."
        return "Sentiment: neutral (simple fallback)."

def _latest_price_yf(symbol: str) -> Tuple[Optional[float], str]:
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1d", interval="1m")
        if not df.empty:
            return float(df["Close"].iloc[-1]), "yfinance (intraday)"
        df = t.history(period="5d", interval="1d")
        if not df.empty:
            return float(df["Close"].iloc[-1]), "yfinance:last_close"
        return None, "yfinance:unavailable"
    except Exception:
        logging.exception("yfinance failed for %s", symbol)
        return None, "yfinance:error"

def get_latest_price(symbol: str) -> Tuple[Optional[float], str]:
    """Preferred entry: cache -> AlphaVantage -> yfinance. Uses normalized symbol and today's cache key."""
    sy = map_symbol(symbol)
    today = _today_str()

    try:
        cached = get_cached_price(sy, today)
        if cached is not None:
            return float(cached), "cache:today"
    except Exception:
        logging.exception("cache read failed for %s", sy)

    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if api_key:
        p, src = alpha_vantage_price(sy, api_key, timeout=60)
        if p is not None:
            try:
                put_cached_price(sy, today, p)
            except Exception:
                logging.exception("cache write failed for %s", sy)
            return p, src

    p, src = _latest_price_yf(sy)
    if p is not None:
        try:
            put_cached_price(sy, today, p)
        except Exception:
            logging.exception("cache write failed for %s", sy)
    return p, src

def tool_news_headlines(query: str, limit: int = 5) -> str:
    token = (FINNHUB_API_KEY or os.getenv("FINNHUB_API_KEY", ""))
    if not token:
        return ("News is not configured. Set FINNHUB_API_KEY in your environment "
                "to enable Finnhub company/general news.")

    rows = _finnhub_news_from_query(query, limit=limit)
    if rows:
        return "News (source: Finnhub)\n" + "\n".join(rows) + "\nsource: finnhub"
    return f"No recent items for '{query}' in the last 14 days.\nsource: finnhub"
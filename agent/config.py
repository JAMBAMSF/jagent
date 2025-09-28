from __future__ import annotations
import os

def _getenv(*names: str, default: str = "") -> str:
    """Return the first defined env var from names, else default."""
    for n in names:
        v = os.getenv(n)
        if v not in (None, ""):
            return v
    return default

def _as_float(x: str, default: float) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _as_int(x: str, default: int) -> int:
    try:
        return int(x)
    except Exception:
        return default

OPENAI_MODEL = _getenv("OPENAI_MODEL", "JAGENT_OPENAI_MODEL", default="gpt-4o-mini")  # safe default; override if needed

RISK_FREE_RATE   = _as_float(_getenv("RISK_FREE_RATE", "JAGENT_RISK_FREE_RATE", default="0.0425"), 0.0425)
CACHE_TTL_HOURS  = _as_int(_getenv("CACHE_TTL_HOURS", "JAGENT_CACHE_TTL_HOURS", default="1"), 1)
MAX_AGENT_STEPS  = _as_int(_getenv("MAX_AGENT_STEPS", "JAGENT_MAX_AGENT_STEPS", default="4"), 4)

DB_PATH   = _getenv("DB_PATH", "JAGENT_DB_PATH", default=os.path.join("data", "jagent.db"))
SEED_FILE = _getenv("SEED_FILE", "JAGENT_SEED_FILE", default="")

FINNHUB_API_KEY       = _getenv("FINNHUB_API_KEY", "JAGENT_FINNHUB_API_KEY", default="")
FINNHUB_WEBHOOK_SECRET= _getenv("FINNHUB_WEBHOOK_SECRET", "JAGENT_FINNHUB_WEBHOOK_SECRET", default="")
ALPHAVANTAGE_API_KEY  = _getenv("ALPHAVANTAGE_API_KEY", "JAGENT_ALPHAVANTAGE_API_KEY", default="")
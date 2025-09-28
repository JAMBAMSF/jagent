import csv, os, time
from typing import Optional
import logging
from agent.config import CACHE_TTL_HOURS

CACHE_PATH = os.getenv("JAGENT_CACHE_CSV", os.path.join("data", "cache_prices.csv"))
CACHE_TTL_S = int(float(CACHE_TTL_HOURS) * 3600)

def _now() -> float: 
    return time.time()

def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def get_cached_price(symbol: str, date: str) -> Optional[float]:
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        sym = symbol.upper()
        latest = None
        with open(CACHE_PATH, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if row.get("symbol","").upper() == sym and row.get("date") == date:
                    latest = row  # keep the last one
        if latest is None:
            return None
        if _now() - float(latest["ts"]) > CACHE_TTL_S:
            return None
        return float(latest["price"])
    except Exception:
        logging.exception("cache read failed (%s, %s)", symbol, date)
        return None
    
def put_cached_price(symbol: str, date: str, price: float) -> None:
    try:
        _ensure_dir(CACHE_PATH)
        header = ["symbol", "date", "price", "ts"]
        exists = os.path.exists(CACHE_PATH)
        with open(CACHE_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            if not exists:
                w.writeheader()
            w.writerow({"symbol": symbol.upper(), "date": date, "price": price, "ts": _now()})
    except Exception:
        logging.exception("cache write failed (%s, %s)", symbol, date)

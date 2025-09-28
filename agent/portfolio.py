from __future__ import annotations
import math
from typing import Dict
import numpy as np
import pandas as pd
import re
from typing import Dict
from agent.config import RISK_FREE_RATE

def normalize_allocations(alloc: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(alloc.values()))
    if total <= 0: raise ValueError("Allocation weights must sum to > 0")
    return {k: v/total for k, v in alloc.items()}

def parse_percent_alloc(s: str) -> Dict[str, float]:
    pairs = re.findall(r'(\d+(?:\.\d+)?)\s*%\s*([A-Za-z0-9][A-Za-z0-9.\-_]*)', s)
    out: Dict[str, float] = {}
    for pct_str, sym in pairs:
        w = float(pct_str) / 100.0
        sym_clean = re.sub(r'[^A-Za-z0-9]', '', sym).upper()
        if not sym_clean:
            continue
        out[sym_clean] = out.get(sym_clean, 0.0) + w
    if not out: 
        raise ValueError("Could not parse any allocations.")
    return normalize_allocations(out)

def hhi_diversification(weights: Dict[str, float]) -> float:
    return float(sum(w*w for w in weights.values()))

def expected_return(returns_df: pd.DataFrame, weights: Dict[str, float]) -> float:
    daily_mean = returns_df.mean()
    w = np.array([weights.get(c, 0.0) for c in returns_df.columns])
    port_daily = float(np.dot(daily_mean.values, w))
    return port_daily * 252.0

def portfolio_volatility(returns_df: pd.DataFrame, weights: Dict[str, float]) -> float:
    cov = returns_df.cov()
    w = np.array([weights.get(c, 0.0) for c in returns_df.columns])
    var = float(np.dot(w.T, np.dot(cov.values, w)))
    return math.sqrt(var) * math.sqrt(252.0)

def sharpe_ratio(exp_return: float, vol: float, rf: float = RISK_FREE_RATE) -> float:
    if vol <= 0:
        return 0.0
    return (exp_return - rf) / vol

def value_at_risk_normal(exp_return: float, vol: float, z: float = 1.65) -> float:
    return exp_return - z * vol

def risk_fit_label(vol: float, tolerance: str) -> str:
    tol = (tolerance or "").lower().strip()
    if tol in ("conservative", "low"): return "fit" if vol < 0.10 else "too volatile"
    if tol in ("moderate", "medium"):  return "fit" if vol < 0.20 else "too volatile"
    if tol in ("aggressive", "high"):  return "fit" if vol < 0.35 else "too volatile"
    return "unknown"

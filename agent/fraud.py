from __future__ import annotations
from typing import Any, Dict, Tuple, Optional, List, Mapping

def zscore_flag(amount: float, history: List[float]) -> bool:
    if not history or len(history) < 5:
        return False
    mu = sum(history) / len(history)
    sd = (sum((x - mu) ** 2 for x in history) / len(history)) ** 0.5 or 1.0
    return abs((amount - mu) / sd) > 3

def _parse_hour(tx: Dict[str, Any]) -> int:
    h = tx.get("hour")
    if h is not None:
        try:
            return int(h)
        except Exception:
            pass
    t = tx.get("time") or tx.get("timestamp")
    if isinstance(t, str) and ":" in t:
        try:
            return int(t.split(":")[0])
        except Exception:
            pass
    return -1

def simple_fraud_check(
    tx: Dict[str, Any],
    known_counterparties: Optional[set[str]] = None,
    policy: Optional[Dict[str, Any]] = None,
    history_by_cp: Optional[Mapping[str, List[float]]] = None,
) -> Tuple[bool, Dict[str, Any]]:

    policy = policy or {}
    odd_hours = set(policy.get("odd_hours", [0, 1, 2, 3, 4]))
    large_amt = float(policy.get("large_amount_threshold", 5000.0))

    flags: List[str] = []
    amt = float(tx.get("amount") or 0.0)
    cp = (tx.get("counterparty") or "").strip()
    hour = _parse_hour(tx)

    if hour in odd_hours:
        flags.append("odd-hour")
    if known_counterparties is not None and cp and cp not in known_counterparties:
        flags.append("unknown-counterparty")
    if amt >= large_amt:
        flags.append("large-amount")

    # statistical anomaly vs this counterparty's own history
    if history_by_cp and cp:
        hist = history_by_cp.get(cp) or []
        if zscore_flag(amt, hist):
            flags.append("amount-anomaly")

    return (bool(flags), {"flags": flags, "amount": amt, "hour": hour, "counterparty": cp})
from __future__ import annotations
from typing import Tuple

GENERIC_DISCLAIMER = (
    "This content is for informational purposes only and is not financial advice. "
    "No offer, solicitation, or recommendation is being made. "
    "Past performance does not guarantee future results. "
    "For personalized guidance, consult a licensed professional. "
    "Data sources may be delayed or inaccurate; verify independently. "
    "GDPR simulation: you can request deletion of your stored data with 'forget me'. "
    "Recommendations are hypothetical and not personalized advice under SEC rules. "
)

BANNED_PHRASES = (
    "guaranteed profit", "surefire", "inside information", 
    "front-run", "pump and dump", "tax evasion", 
    "insider trading", "day trading strategy", "spoofing",
    "dark edge", "gray edge"
    )

def guard_and_disclaim(text: str, banned_only: bool = False) -> Tuple[bool, str]:
    lower = text.lower()
    if any(p in lower for p in BANNED_PHRASES):
        return (False, "I can’t assist with that request (compliance). If you want, I can explain legal, diversified approaches instead.")
    if banned_only:
        return (True, text)
    return (True, text + "\n\n" + GENERIC_DISCLAIMER + "We avoid favoritism toward individual securities; suggestions are diversified and ETF-first where possible.")
import re

def _alloc_only(text: str) -> str:
    picks = re.findall(r'\d+(?:\.\d+)?\s*%\s*[A-Za-z0-9.\-_]+', text)
    return ", ".join(picks) if picks else text

def test_alloc_only_extracts_pairs():
    s = "please evaluate 50% NVDA and 30% TSLA, also 20% bonds thanks"
    assert _alloc_only(s) == "50% NVDA, 30% TSLA, 20% bonds"

def test_price_regex_catches_natural_language():
    pat = re.compile(
        r"(?:(?P<t1>[A-Za-z][A-Za-z0-9.\-]{0,9})(?:['’]s)?\s+(?:price|quote)\b"
        r"|"
        r"\b(?:what(?:'s| is)\s+)?(?:the\s+)?(?:price|quote)\s+(?:of|for)?\s*(?P<t2>[A-Za-z][A-Za-z0-9.\-]{0,9})\b)",
        re.I,
    )
    m = pat.search("what's NVDA's price?")
    assert m

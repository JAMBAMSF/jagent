from __future__ import annotations
from typing import Callable, Any, Dict, Optional, List
import logging, os, re
from agent.agent import run_and_comply

logger = logging.getLogger("gagent.failsafe")

FAILSAFE_STRICT = os.getenv("FAILSAFE_STRICT", "1") not in {"0", "false", "False"}
FAILSAFE_VERBOSE = os.getenv("FAILSAFE_VERBOSE", "0") in {"1", "true", "True"}

_BAD_PATTERNS = [
    r"\bnan\b",
    r"could not parse",
    r"invalid +json",
    r"unavailable",
    r"no price data found",
    r"yfinance.*failed",
    r"request timed out",
    r"error:",
    r"exception",
]

def _looks_broken(output: str) -> bool:
    if not FAILSAFE_STRICT:
        return False
    if not output:
        return True
    text = str(output).lower()

    if "expected annual return:" in text and "nan" not in text:
        return False

    for pat in _BAD_PATTERNS:
        if re.search(pat, text):
            return True

    if "expected annual return:" in text and "nan" in text:
        return True

    return False

FINAL_SUFFIX = "I liked your questions very much. What else can I help with?"

def _should_suffix() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return os.getenv("GAGENT_FINAL_SUFFIX", "1") == "1"

def format_final(text: str, *, final: bool = True) -> str:
    if final and _should_suffix():
        return f"{text.rstrip()}\n\n{FINAL_SUFFIX}"
    return text

def run_with_failsafe(*, question: str, handlers, chat, context=None, final=False):
    """
    Try handlers in order; if any raises OR returns a low-quality/broken string,
    fall back to the LLM with the original question.
    """
    for h in handlers:
        try:
            out = h()
            if isinstance(out, (bytes, bytearray)):
                out = out.decode("utf-8", "ignore")
            out_str = str(out)

            if _looks_broken(out_str):
                if FAILSAFE_VERBOSE:
                    logger.exception("Failsafe flagged tool output (context=%s): %s", context, out_str[:200])
                else:
                    logger.debug("Failsafe flagged tool output (context=%s)", context)
                raise RuntimeError("tool-low-quality-output")

            return out_str
        except Exception as e:
            if FAILSAFE_VERBOSE:
                logger.exception("Tool handler failed (context=%s): %s", context, e)
            else:
                logger.debug("Tool handler failed (context=%s): %s", context, e)

    # Fallback to LLM (no user-facing stack trace)
    from agent.agent import run_and_comply  # local import to avoid cycles
    return run_and_comply(chat, question)

def freeform_only(
    question: str,
    chat: Callable[[List[Dict[str, str]]], str],
    context: Optional[Dict[str, Any]] = None,
    final: bool = True,
) -> str:
    return run_with_failsafe(question=question, handlers=[], chat=chat, context=context, final=final)

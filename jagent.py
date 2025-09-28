#!/usr/bin/env python
from __future__ import annotations
import argparse, os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from agent.agent import build_agent, run_and_comply
from agent.tools import (
    tool_portfolio_analysis, 
    tool_stock_query, 
    tool_fraud_check, 
    tool_sentiment, 
    tool_news_headlines,
)
from agent.memory import connect, upsert_user, set_risk_tolerance, forget_user, get_user, list_counterparties, upsert_counterparty
from agent.fraud import simple_fraud_check
from agent.compliance import guard_and_disclaim
import json
import re, logging
from agent.failsafe import run_with_failsafe, freeform_only
from dotenv import load_dotenv
load_dotenv()

def _tool_or_llm(agent, fn, *args, **kwargs):
    """Back-compat shim: route through run_with_failsafe so we also catch low-quality outputs."""
    original_prompt = kwargs.pop("original_prompt", "")
    context = kwargs.pop("context", None)
    return run_with_failsafe(
        question=original_prompt or (args[0] if args else ""),
        handlers=[lambda: fn(*args, **kwargs)],
        chat=agent,
        context=context,
        final=False,
    )

PRICE_TICKER_REGEX = re.compile(
    r"(?:(?P<t1>[A-Za-z][A-Za-z0-9.\-]{0,9})(?:['’]s)?\s+(?:price|quote)\b"
    r"|"
    r"\b(?:what(?:'s| is)\s+)?(?:the\s+)?(?:price|quote)\s+(?:of|for)?\s*(?P<t2>[A-Za-z][A-Za-z0-9.\-]{0,9})\b)",
    re.I,
)

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

import logging, sys
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(asctime)s %(name)s: %(message)s",
    stream=sys.stdout
)

def _alloc_only(text: str) -> str:

    pairs = re.findall(r'(\d+(?:\.\d+)?)\s*%\s*([A-Za-z][A-Za-z0-9.\-_]+)', text)
    if not pairs:
        return ""
    STOP = {"IN", "OF", "TO", "INTO", "ON", "AT"}
    ALIAS = {
        "BONDS": "BND",
        "BOND": "BND",
        "FIXEDINCOME": "BND",
        "APPL": "AAPL",   
    }
    cleaned = []
    for pct, sym in pairs:
        s = sym.strip().upper().rstrip(".,;:)")
        if s in STOP:
            continue
        s = ALIAS.get(s, s)
        cleaned.append(f"{pct}% {s}")
    return ", ".join(cleaned)

SYNONYMS = {
    r"\b(high risk|risk-on|risk on||risk[-\s]?on|very aggressive|speculative|max risk)\b": "aggressive",
    r"\b(balanced|medium risk|average risk|moderately)\b": "moderate",
    r"\b(low risk|risk[-\s]?off|risk-averse|risk averse|defensive|capital preservation)\b": "conservative",
}

def _infer_risk_freeform(text: str) -> str | None:
    t = (text or "").lower()

    cue = re.search(
        r"\b("
        r"i am|i'm|"
        r"my\s+risk(?:\s*(?:toler[ae]nce|preference|profile|level|appetite))?\s+is|"
        r"assume\s+(?:i am|i'm)|"
        r"consider me|treat me as|"
        r"set\s+.*risk.*(?:to|as)"
        r")\b",
        t,
    )
    if not cue:
        return None

    m = re.search(r"\b(conservative|moderate|aggressive)\b", t)
    if m:
        return m.group(1)

    for pat, canon in SYNONYMS.items():
        if re.search(pat, t):
            return canon
    
    return None

console = Console()

def _is_followup(text: str) -> bool:
    if not text:
        return False
    last = ""
    for line in str(text).strip().splitlines()[::-1]:
        if line.strip():
            last = line.strip()
            break
    return last.endswith(("?", "？"))

def _friendly_nudge():
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    w = console.size.width
    body = (
        "I liked your question. What else can I help?\n"
        "[dim]Try:[/dim] price NVDA · analyze portfolio 60% AAPL, 40% BND · "
        "payee add \"Soho House New York\""
    )
    console.print(Panel(body, border_style="cyan", width=min(w, 100)))
    
import warnings
warnings.filterwarnings("ignore", message=".*migrating_memory.*")
warnings.filterwarnings("ignore", message=".*LangChain agents will continue to be supported.*")
warnings.filterwarnings("ignore", message=".*Chain.run.*deprecated.*")

HELP = r"""
[bold]JAgent — commands & input formats[/]

Type [bold]help <topic>[/] for details:
  topics: [italic]price, analyze, portfolio, risk, fraud, payee, memory, sentiment, news, safety, exit[/]

[b]Quick commands[/]
  [bold]help[/]                         Show this summary
  [bold]help <topic>[/]                 Show detailed help on a topic
  [bold]set risk <conservative|moderate|aggressive>[/]
  [bold]analyze portfolio <allocs>[/]   e.g., analyze portfolio 50% NVDA, 30% TSLA, 20% bonds
  [bold]price <TICKER>[/]               e.g., price NVDA
  [bold]news <query|TICKER>[/]          e.g., news NVDA   |   news interest rates
  [bold]sentiment <text>[/]             e.g., sentiment "NVDA crushed earnings and guidance was strong"
  [bold]fraud <JSON>[/]                 e.g., fraud {"type":"cash","amount":30000,"counterparty":"AMERICAN EXPRESS","hour":1}
  [bold]payee add <NAME>[/]             Add a frequent counterparty/payee
  [bold]payee list[/]                   List known counterparties (user + global)
  [bold]forget me[/]                    Erase my chats/portfolios from local DB (keeps global payees)
  [bold]exit | quit[/]                  Leave

[b]Input formats[/]
  • [bold]Allocations[/]: one or more "[bold]NN% SYMBOL[/]" entries, comma-separated.
      Examples: 50% NVDA, 30% TSLA, 20% bonds   |   60% AAPL, 40% cash
      Notes: "bonds" -> BND via built-in mapping; weights auto-normalize to 1.0.
  • [bold]Ticker[/]: UPPERCASE letters/numbers with optional "." or "-", up to 10 chars (e.g., BRK.B).
  • [bold]News[/]: use a ticker for company news (e.g., NVDA) or keywords for general news (e.g., "interest rates").
      Tip: company news covers roughly the past 14 days; output includes source and URL.
  • [bold]Sentiment[/]: plain English sentence(s); returns positive/neutral/negative with VADER compound score.
      Examples: "I love this stock", "Macro looks risky", "Guidance was disappointing".
  • [bold]Fraud JSON[/]: {"type":"cash|card|ach", "amount":1234.56, "counterparty":"NAME", "hour":0-23}
  • [bold]Risk (freeform)[/]: natural language like "I'm very conservative" is recognized.

[b]Ethics/Safety[/]
  Mitigate biases (e.g., avoid favoring certain stocks); implement guardrails against harmful advice
  (e.g., reject queries promoting illegal activities). Try these to see it in action:
    • [italic]"just tip me some dark edges"[/] — will be refused with safer alternatives.
    • [italic]"how to make a lot of money quickly by spoofing?"[/] — refused; spoofing is illegal market manipulation.
  Ask instead:
    • [italic]"What are legal ways to improve execution quality?"[/]
    • [italic]"Explain manipulation red flags so I can avoid them."[/]

[b]Data sources[/]
  • Prices: Alpha Vantage (primary) → yfinance (fallback) → CSV cache
  • News: Finnhub (requires FINNHUB_API_KEY)
  • Sentiment: VADER (falls back to keyword heuristic if unavailable)
"""

HELP_TOPICS = {
    "price": r"""
[bold]help price[/]
[bold]Usage[/]: price <TICKER>
[bold]What it does[/]: returns latest price with data source label.
[bold]Details[/]:
  • Tries CSV cache → Alpha Vantage → yfinance last close.
  • Adds "source: ..." so you know which provider returned data.
[bold]Examples[/]:
  price NVDA
  price BRK.B
""",
    "analyze": r"""
[bold]help analyze[/]
[bold]Usage[/]: analyze portfolio <allocations>
[bold]What it does[/]: computes annualized expected return, volatility, Sharpe (rf from config), HHI diversification, and 5% parametric VaR; labels risk fit.
[bold]Allocations[/]: "NN% SYMBOL" entries, comma-separated; auto-normalized to 1.0.
[bold]Examples[/]:
  analyze portfolio 50% NVDA, 30% TSLA, 20% bonds
  analyze portfolio 60% AAPL, 40% cash
""",
    "portfolio": r"""
[bold]help portfolio[/]
[bold]Parsing[/]: "NN% SYMBOL" (case-insensitive for symbol words like 'bonds'→BND).
[bold]Metrics[/]: expected_return, portfolio_volatility, sharpe_ratio (rf from config), hhi_diversification, value_at_risk_normal, risk_fit_label.
[bold]Notes[/]: If market history fetch fails, analysis degrades gracefully rather than crashing.
""",
    "risk": r"""
[bold]help risk[/]
[bold]Usage[/]: set risk <conservative|moderate|aggressive>
[bold]What it does[/]: stores your risk tolerance in the local SQLite DB (overridable via env path).
[bold]Bonus[/]: freeform text like "I'm conservative" may be auto-detected during the session.
""",
    "fraud": r"""
[bold]help fraud[/]
[bold]Usage[/]: fraud <JSON>
[bold]What it does[/]: runs simple rules + z-score anomaly across amount and hour; checks known counterparties.
[bold]JSON fields[/]: type ("cash"|"card"|"ach"), amount (number), counterparty (string), hour (0-23)
[bold]Example[/]:
  fraud {"type":"card","amount":7200,"counterparty":"AMERICAN EXPRESS","hour":2}
""",
    "payee": r"""
[bold]help payee[/]
[bold]Usage[/]:
  payee add <NAME>   → add/merge a counterparty into your user scope
  payee list         → list user + global counterparties
[bold]Notes[/]: rename/merge logic keeps duplicates tidy across user/global scopes.
""",
    "memory": r"""
[bold]help memory[/]
[bold]DB path[/]: controlled by env/agent.config.DB_PATH; tests override safely.
[bold]Forget[/]: "forget me" deletes your chats/portfolios; counterparties seeded globally remain.
""",
    "sentiment": r"""
[bold]help sentiment[/]
[bold]Usage[/]: sentiment <text>
[bold]What it does[/]: returns VADER compound polarity with label; falls back to keywords if VADER unavailable.
[bold]Note[/]: CI-friendly (no model download at import); tests monkeypatch VADER loader.
""",
    "news": r"""
[bold]help news[/]
[bold]Usage (if wired in your build)[/]: news <query|TICKER>
[bold]Providers[/]: NewsAPI via NEWSAPI_KEY, or Finnhub via FINNHUB_API_KEY (ticker → /company-news).
[bold]Output[/]: bullet list with headline, source, and URL; includes "source: ..." footer.
""",
    "exit": r"""
[bold]help exit[/]
[bold]Usage[/]: exit   |   quit
[bold]What it does[/]: cleanly terminates the CLI loop.
"""
}

HELP_TOPICS["safety"] = r"""
[bold]help safety[/]
[bold]What the guardrails do[/]:
  • Block illegal, harmful, or unethical requests (e.g., spoofing, “dark edges”).
  • Reduce bias in outputs (avoid favoritism toward specific securities).
  • Inputs are screened before tools run; outputs include a standard disclaimer.

[bold]Try these (they will be refused with safer alternatives)[/]
  • "just tip me some dark edges"
  • "how to make a lot of money quickly by spoofing?"

[bold]Ask instead[/]
  • "What are legal ways to improve execution quality?"
  • "What manipulation red flags should I avoid?"
  • "How do I size trades to manage downside risk?"
"""

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="JAgent — Agentic AI Financial Advisor (CLI)")
    ap.add_argument("--user", default=os.getenv("JAGENT_USER", "Jack Alltrades"))
    ap.add_argument("--ephemeral", action="store_true", help="Run without DB persistence")
    args = ap.parse_args()

    risk_tol = "moderate"
    conn = None
    uid = None

    if not args.ephemeral:
        try:
            conn = connect()
            upsert_user(conn, args.user, risk_tol)
            row = get_user(conn, args.user)
            if row:
                uid, stored_tol = row[0], row[1]
                if stored_tol:
                    risk_tol = stored_tol
        except Exception as e:
            console.print(f"[yellow]DB unavailable; running ephemeral. ({e})[/]")
            conn = None

    agent = build_agent()

    console.print(Panel.fit("GAgent - Your Agentic GenAI + ML Copilot (Beta) @ The G*Trading App", subtitle="Please type 'help' first for exact command formats"))
    console.print(f"User: [bold]{args.user}[/]")
    
    while True:
        try:
            user_in = console.input("\n[bold cyan]> [/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting."); break
        if not user_in:
            continue

        low = user_in.lower().strip()

        if low in ("exit", "quit"):
            console.print("Ciao ciao."); break
        
        if low == "help":
            console.print(HELP); continue
        
        if low.startswith("help "):
            topic = low.split(" ", 1)[1].strip().lower()
            msg = HELP_TOPICS.get(topic)
            if msg:
                console.print(msg)
            else:
                console.print("[yellow]Unknown help topic.[/] Try: price, analyze, portfolio, risk, fraud, payee, memory, sentiment, news, exit")
            continue

        tol_guess = _infer_risk_freeform(user_in)
        if tol_guess:
            if conn:
                try:
                    uid = upsert_user(conn, args.user, tol_guess)
                    set_risk_tolerance(conn, uid, tol_guess)
                    risk_tol = tol_guess
                    console.print(f"Set risk tolerance to [bold]{tol_guess}[/] (from natural language).")
                    _friendly_nudge()
                except Exception as e:
                    console.print(f"[red]Failed to set risk: {e}[/]")
            else:
                risk_tol = tol_guess
                console.print(f"Set risk tolerance to [bold]{tol}[/] (from natural language).")
                _friendly_nudge()
            continue

        if low.startswith("set risk"):
            parts = low.split()
            if len(parts) >= 3:
                tol = parts[-1]
                if conn:
                    try:
                        uid = upsert_user(conn, args.user, tol)
                        set_risk_tolerance(conn, uid, tol)
                        risk_tol = tol
                        console.print(f"Set risk tolerance to [bold]{tol}[/].")
                        _friendly_nudge()
                    except Exception as e:
                        console.print(f"[red]Failed to set risk: {e}[/]")
                else:
                    risk_tol = tol
                    console.print(f"Risk tolerance set (ephemeral): {tol}", final=True)
                    _friendly_nudge()
            else:
                console.print("Usage: set risk <conservative|moderate|aggressive>")
            continue

        if low == "forget me":
            if conn and uid is not None:
                try:
                    forget_user(conn, args.user)
                    set_risk_tolerance(conn, uid, "moderate")
                    risk_tol = "moderate"
                    console.print("[green]Your chats and portfolios have been deleted; saved payees/counterparties were retained.[/]")
                    _friendly_nudge()
                except Exception as e:
                    console.print(f"[red]Failed to delete: {e}[/]")
            else:
                risk_tol = "moderate"
                console.print("Nothing to delete (ephemeral).")
                _friendly_nudge()
            continue

        # DIRECT TOOL ROUTES (no LLM call)

        if low.startswith("price "):
            ticker = user_in.split(maxsplit=1)[1].strip()
            out = run_with_failsafe(
                question=user_in,
                handlers=[lambda: tool_stock_query(ticker)],
                chat=agent,
                context={"cmd": "price", "ticker": ticker},
                final=False,
            )
            console.print(out)
            if not _is_followup(out):
                _friendly_nudge()
            continue

        if low.startswith("analyze portfolio"):
            alloc_raw = user_in.split("analyze portfolio", 1)[1].strip()
            alloc = _alloc_only(alloc_raw)
            if not alloc or "%" not in alloc:
                console.print("Example: analyze portfolio 50% AAPL, 30% TSLA, 20% bonds")
                continue
            out = run_with_failsafe(
                question=user_in,
                handlers=[lambda: tool_portfolio_analysis(alloc, risk_tolerance=risk_tol)],
                chat=agent,
                context={"cmd": "analyze", "alloc": alloc, "risk": risk_tol},
                final=False,
            )
            console.print(out)
            if not _is_followup(out):
                _friendly_nudge()
            continue

        if low.startswith("fraud "):
            js = user_in.split("fraud", 1)[1].strip()
            known = set()
            if conn and uid is not None:
                try:
                    known = set(list_counterparties(conn, uid))
                except Exception:
                    known = set()
            policy = {"odd_hours": [0,1,2,3,4,5], "large_amount_threshold": 5000.0}
            
            def _call():
                out_raw = tool_fraud_check(js, known_counterparties=known, policy=policy)
                _, out = guard_and_disclaim(out_raw)
                return out

            out = run_with_failsafe(
                question=user_in,
                handlers=[_call],
                chat=agent,
                context={"cmd": "fraud", "policy": policy, "known": sorted(known)},
                final=False,
            )
            console.print(out)
            if not _is_followup(out):
                _friendly_nudge()
            continue


        if low.startswith("sentiment "):
            text_for_sent = user_in.split(" ", 1)[1].strip()
            out = run_with_failsafe(
                question=user_in,
                handlers=[lambda: tool_sentiment(text_for_sent)],
                chat=agent,
                context={"cmd": "sentiment"},
                final=False,
            )
            console.print(out)
            if not _is_followup(out):
                _friendly_nudge()
            continue

        if low.startswith("payee add ") or low.startswith("counterparty add "):
            prefix = "payee add " if low.startswith("payee add ") else "counterparty add "
            name = user_in[len(prefix):].strip().strip('"').strip("'").rstrip(".,;:")
            if not name:
                console.print("Usage: payee/counterparty add <NAME>"); continue
            if conn and uid is not None:
                try:
                    upsert_counterparty(conn, uid, name)
                    console.print(f"Added/updated payee/counterparty: [bold]{name}[/]")
                    _friendly_nudge()   
                except Exception as e:
                    console.print(f"[red]Failed to add payee/counterparty: {e}[/]")
            else:
                console.print("No database (ephemeral mode).")
            continue

        if low.startswith("news "):
            topic = user_in.split(" ", 1)[1].strip()

            def _call():
                q = topic.strip().strip('"').strip("'")
                return tool_news_headlines(q, limit=5)

            out = run_with_failsafe(
                question=f"Give me recent headlines for: {topic}",
                handlers=[_call],
                chat=agent,              
                context={"cmd": "news", "topic": topic},
                final=False,
            )
            console.print(out)
            if not _is_followup(out):
                _friendly_nudge()
            continue

        if low in {"payee list", "counterparty list", "payee/counterparty list"}:
            if conn and uid is not None:
                try:
                    names = list_counterparties(conn, uid) or []
                    msg = (
                        "Saved payees/counterparties:\n- " + "\n- ".join(names)
                        if names else
                        "No saved payees/counterparties."
                    )
                    console.print(msg)
                    _friendly_nudge() 
                except Exception as e:
                    console.print(f"[red]Failed to list payees/counterparties: {e}[/]")
            else:
                console.print("No database (ephemeral mode).")
            continue

        alloc_guess = _alloc_only(user_in)
        if alloc_guess and "%" in alloc_guess:
            out = run_with_failsafe(
            question=user_in,
            handlers=[lambda: tool_portfolio_analysis(alloc_guess, risk_tolerance=risk_tol)],
            chat=agent,
            context={"cmd": "analyze", "alloc": alloc_guess, "risk": risk_tol},
            final=False,
            )
            console.print(out)
            if not _is_followup(out):
                _friendly_nudge()
            continue

        m = PRICE_TICKER_REGEX.search(user_in)
        if m:
            raw = (m.group("t1") or m.group("t2")).upper()
            ticker = re.sub(r"['’]s$", "", raw).rstrip(".,!?):;")
            out = run_with_failsafe(
                question=user_in,
                handlers=[lambda: tool_stock_query(ticker)],
                chat=agent,
                context={"cmd": "price", "ticker": ticker, "regex": True},
            final=True,
            )
            console.print(out)
            _friendly_nudge()
            continue
    
        # FALLBACK: SEND TO THE AGENT/LLM

        out = freeform_only(
            question=user_in,
            chat=agent,
            context={"route": "freeform"},
            final=False,   
        )
        console.print(out)
        if not _is_followup(out):
            _friendly_nudge()

if __name__ == "__main__":
    main()

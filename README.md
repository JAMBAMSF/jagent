# GAgent — Agentic AI + ML Copilot (Beta) @ The G*Trading App

> *Built by Jaxon Archer.* A small, practical **agentic AI** that plans, calls tools, and answers safely for personal finance tasks. Runs locally with free data sources and a simple CLI/Streamlit UI.

---

## TL;DR (Quickstart)

```bash
# 1) Clone & enter
git clone <your-repo-url> && cd <repo>

# 2) Python env (recommended)
python -m venv .venv && source .venv/bin/activate  # on Windows: .venv\Scripts\activate

# 3) Install deps
pip install -r requirements.txt

# 4) (Optional) Set keys (free tiers)
export ALPHAVANTAGE_API_KEY=...        # prices fallback
export FINNHUB_API_KEY=...             # headlines fallback
export OPENAI_API_KEY=...              # if you use the LLM

# 5) Run CLI
python gagent.py

# 6) Or start the minimal web UI
streamlit run streamlit_app.py
```

> **Note:** The system runs fine **offline** using cached/last‑close data and local models; keys simply improve freshness.

---

## What this project does

- **Understands → plans → acts.** A short planning loop (cap at 4 steps) selects tools autonomously.
- **Tools:** **stock price** (with robust fallbacks), **portfolio analysis** (return/vol/Sharpe/HHI/VaR), **fraud checks** (rules + z‑score), and **sentiment/news** (optional).
- **State:** remembers **conversation** and **risk tolerance**; stores users/payees/portfolios in **SQLite**; **prices cached** to cut API calls.
- **Safety:** clear **disclaimers**, **guardrails** for risky/illegal intents, refusals with alternatives.
- **Interfaces:** **CLI** first; **Streamlit** demo optional; small **FastAPI webhook** for headlines/market signals.

---

## How to use (CLI)

At the prompt, you can speak naturally or use verbs:

```text
price NVDA
analyze portfolio 50% AAPL, 30% TSLA, 20% bonds
fraud {"type":"cash","amount":5000,"counterparty":"UNKNOWN","hour":1}
set risk conservative
payee add AMERICAN EXPRESS
payee list
forget me
help
exit
```

**Examples**

- *“What’s AAPL price now?”* → tool picks Alpha Vantage → yfinance → cache, returns price with **`source:`** label.  
- *“Analyze my portfolio 60% AAPL, 40% cash.”* → parses, fetches last 6‑months adj closes, reports **expected return, volatility, Sharpe (rf 4.25%), HHI, 5% VaR**, and a **risk‑fit** tag.  
- *“Is this 5k at 1am suspicious?”* → rule checks (amount, hour, unknown payee) + **z‑score** against counterparty history; outputs **why** flagged/cleared.

> Every advisory answer appends a short **disclaimer** (informational only; not an offer/solicitation; not personalized advice).

---

## Configuration

Environment variables (all optional, sensible defaults exist):

| Variable | Default | Purpose |
|---|---:|---|
| `ALPHAVANTAGE_API_KEY` | — | Primary **price** provider (free tier OK). |
| `FINNHUB_API_KEY` | — | Optional **news** headlines. |
| `OPENAI_API_KEY` | — | If you use the hosted LLM. |
| `RISK_FREE_RATE` | `0.0425` | **Sharpe** risk‑free rate. |
| `CACHE_TTL_HOURS` | `1` | CSV cache time‑to‑live for prices. |
| `GAGENT_CACHE_CSV` | `data/cache_prices.csv` | CSV cache path. |
| `GAGENT_DB_PATH` | `data/gagent.sqlite` | Local SQLite database path. |

> Keys go in `.env` during development; nothing is hard‑coded.

---

## Architecture (at a glance)

```mermaid
graph TD
  U[User (CLI/Streamlit)] --> ORCH[Planner (LangChain)]
  ORCH -->|selects| T1[Price Tool
(AV → yfinance → cache)]
  ORCH -->|selects| T2[Portfolio Tool
(returns, vol, Sharpe, HHI, VaR)]
  ORCH -->|selects| T3[Fraud Tool
(rules + z‑score)]
  ORCH -->|selects| T4[Sentiment/News Tool]
  ORCH --> MEM[Memory (SQLite + cache)]
  ORCH --> COMP[Compliance Guard
(disclaimers, refusals)]
  COMP --> OUT[Final Answer w/ Source & Safety]
```

**Why it’s agentic:** the orchestrator plans steps, calls tools, integrates **provenance** and **policy checks**, and only then answers.

---

## Tools (what they return)

- **Price:** latest price + **`source:`** (Alpha Vantage / yfinance intraday / yfinance last close / CSV cache).  
- **Portfolio:** normalized weights; **expected return** (mean), **volatility** (stdev), **Sharpe**, **HHI** diversification, **5% VaR**; risk‑fit tag (conservative/moderate/aggressive).  
- **Fraud:** `ok/flagged` + reasons (amount threshold, odd hour, unknown counterparty, anomaly score).  
- **Sentiment/News:** optional VADER score + top headlines per ticker (when key provided).

---

## Memory & State

- **SQLite** tables: users (with **risk tolerance**), portfolios, counterparties.  
- **CSV price cache** (TTL) to reduce cost/latency.  
- Commands: `set risk`, `payee add/list`, `forget me` (GDPR‑style delete).

---

## Ethics, Safety, and Compliance

- **Disclaimers** on every advisory output (informational only; not personalized; data may be delayed).  
- **Guardrails** block illegal/dangerous asks (insider trading, “guaranteed profits,” etc.) and offer safe alternatives.  
- **Bias mitigation:** diversified/ETF‑first language; no single‑name hype.  
- **Privacy:** no real PII required; local storage; `.env` for keys.

---

## Testing

```bash
pytest -q
```

Unit tests cover: portfolio math, allocation parsing, symbol mapping, fraud flags, and memory ops. External calls are monkey‑patched for deterministic runs.

---

## Troubleshooting

- **No price returned?** Check `ALPHAVANTAGE_API_KEY` or try again—yfinance last‑close and CSV cache provide fallbacks.  
- **Slow responses?** First price fetch may hit the network; subsequent calls are cached (TTL 1h).  
- **Compliance refusal?** The guard detected risky/illegal content; rephrase or narrow the request.  
- **Windows PowerShell env:** use `$env:ALPHAVANTAGE_API_KEY="..."` (quotes recommended for paths/strings).

---

## Assignment mapping (how this meets the brief)

- **Agentic workflow:** planning loop, autonomous tool selection, memory.  
- **GenAI integration:** LLM for intent parsing/summary; local sentiment; external APIs via tools.  
- **Finance specifics:** disclaimers, guardrails, suitability‑aware tone, provenance labels, cached data.  
- **Tools:** price, portfolio analysis, fraud detection, sentiment/news.  
- **Interface:** CLI (minimum) + Streamlit (optional).  
- **Graceful failure:** fallbacks, TTL cache, friendly errors.  
- **Testing & docs:** unit tests + this README; example commands included.  
- **Edge cases:** ambiguous queries → clarifying; invalid inputs → helpful messages; speculative/illegal asks → refusal.  
- **Performance:** typical responses under **10s** on my laptop (cache improves this).

---

## Roadmap (next steps I’d ship)

- **Dual‑agent gate:** AnalysisAgent + ComplianceAgent (Judge) with self‑checks (e.g., price vs 52‑week band).  
- **Pydantic I/O + JSON‑mode:** structured tool inputs/outputs with confidence + source propagated.  
- **Unified cache:** migrate CSV → SQLite with per‑symbol TTL + circuit breaker.  
- **Telemetry:** latency, error rate, cache hit‑rate, and simple cost ledger.  
- **Market calendar:** proper holiday awareness; news‑per‑holding sentiment.  
- **Optional container:** Dockerfile + Compose (agent + UI + webhook + volume).

---

## Disclaimer

This project is for demonstration and educational purposes. It provides **informational** outputs only and is **not** financial advice, investment solicitation, or a recommendation. Always consult a licensed professional for personal advice.

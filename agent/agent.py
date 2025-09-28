from __future__ import annotations

import os, logging
from typing import Dict, Any, Tuple, List
from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from agent.config import FINNHUB_API_KEY, MAX_AGENT_STEPS

def _build_executor_compat(agent, tools):
    candidates = (
        {"early_stopping_method": "generate", "handle_parsing_errors": True},
        {"early_stopping_method": "force",    "handle_parsing_errors": True},
        {"handle_parsing_errors": True},
        {"early_stopping_method": "generate"},
        {"early_stopping_method": "force"},
        {},
    )
    for kw in candidates:
        try:
            return AgentExecutor(
                agent=agent,
                tools=tools,
                max_iterations=MAX_AGENT_STEPS,
                verbose=True,
                **kw,
            )
        except Exception:
            continue
    return AgentExecutor(agent=agent, tools=tools, verbose=True)

def _no_stream(self, input_messages, stop=None, **kwargs):

    resp = self.invoke(input_messages, stop=stop, **kwargs)

    msg_chunk = AIMessageChunk(
        content=getattr(resp, "content", str(resp)),
        additional_kwargs=getattr(resp, "additional_kwargs", {}),
    )
    if hasattr(resp, "tool_calls"):
        msg_chunk.tool_calls = resp.tool_calls  

    yield ChatGenerationChunk(message=msg_chunk, text=msg_chunk.content)

ChatOpenAI._stream = _no_stream

from agent.tools import (
    tool_stock_query,
    tool_portfolio_analysis,
    tool_fraud_check,
    tool_sentiment,
    tool_news_headlines,
)
from agent.compliance import guard_and_disclaim
from agent.config import OPENAI_MODEL, MAX_AGENT_STEPS as CFG_MAX_STEPS

MODEL_NAME = OPENAI_MODEL or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", CFG_MAX_STEPS or 10))

SYSTEM = """
You are GAgent.

Use a ReAct loop in the hidden scratchpad ONLY (not visible to the user):
- Thought: reason about what to do next.
- Action: exact tool name to call (StockQuery | PortfolioAnalysis | FraudCheck | Sentiment | WSJHeadlines | NewsHeadlines).
- Action Input: the input for that tool (plain text or JSON as appropriate).
- Observation: the tool result.

Repeat Thought/Action/Observation until you have enough to answer.

When done, output:
Final Answer: <concise answer only>

Rules:
- If the user's latest message already contains explicit allocations (percentages like '50%' or '$' amounts, or a dict-like string mapping tickers to weights), DO NOT ask any clarifying question.
- Only ask ONE brief clarifying question if allocations are missing or ambiguous.
- If the human message begins with 'NO_CLARIFY ', do not ask any clarifying question and ignore the prefix.
- Prefer calling tools over guessing data.
- Keep responses concise and include a source note when tools provide one.
"""

def build_agent() -> "AgentWithMemory":

    tools = [
        Tool(
            name="StockQuery",
            description="Fetch latest price for a ticker (e.g., NVDA, AAPL, BRK.B). Returns a one-liner with source note.",
            func=tool_stock_query,
            handle_tool_error=True, 
        ),
        Tool(
            name="PortfolioAnalysis",
            description="Analyze allocations or a dict-like string; returns expected return, volatility, Sharpe, HHI, VaR, and risk fit.",
            func=tool_portfolio_analysis,
            handle_tool_error=True, 
        ),
        Tool(
            name="FraudCheck",
            description="Basic fraud screen for a JSON transaction {amount, counterparty, hour}.",
            func=tool_fraud_check,
            handle_tool_error=True, 
        ),
        Tool(
            name="Sentiment",
            description="VADER sentiment for short text; falls back to simple keyword heuristic if VADER unavailable.",
            func=tool_sentiment,
            handle_tool_error=True, 
        ),
        Tool(   
            name="NewsHeadlines",
            description="Get recent headlines for a ticker/topic. Usage: a short query like 'NVDA' or 'Nvidia AI'.",
            func=tool_news_headlines,
            handle_tool_error=True, 
        ),
        ]

    llm = ChatOpenAI(
        model=MODEL_NAME,
        temperature=0.1,
        timeout=60,
        max_retries=0,
    )

    prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("system", "Available tools:\n{tools}\n\nYou may call only: {tool_names}"),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
    ])

    tool_desc = "\n".join(f"{t.name}: {t.description}" for t in tools)
    tool_names = ", ".join(t.name for t in tools)
    prompt = prompt.partial(tools=tool_desc, tool_names=tool_names)

    core_agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=core_agent,
        tools=tools,
        max_iterations=MAX_AGENT_STEPS,
        handle_parsing_errors=True,
        early_stopping_method="generate",
        verbose=True,
    )

    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    return AgentWithMemory(executor, memory)


class AgentWithMemory:

    def __init__(self, executor: AgentExecutor, memory: ConversationBufferMemory):
        self.exec = executor
        self.mem = memory

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        user_msg = inputs.get("input", "")

        # 1) Pre-invoke compliance check (input side)
        ok_in, maybe_msg = guard_and_disclaim(user_msg, banned_only=True)
        if not ok_in:
            # Block before hitting the LLM/tools if request is non-compliant.
            return {"output": maybe_msg}

        # 2) Pull chat history from memory and call the agent
        hist = self.mem.load_memory_variables({}).get("chat_history", [])
        try:
            result = self.exec.invoke({"input": user_msg, "chat_history": hist})
            ai_msg = result.get("output", str(result))
        except Exception:
            logging.exception("Agent invocation failed")
            ai_msg = "Sorry — something went wrong while processing that. Try rephrasing or a simpler request."

        # 3) Persist turn, then 4) post-invoke compliance (output side)
        self.mem.save_context({"input": user_msg}, {"output": ai_msg})
        ok_out, final_text = guard_and_disclaim(ai_msg)

        return {"output": final_text}


def run_and_comply(executor, prompt: str) -> str:
    try:
        result = executor.invoke({"input": prompt})
        return result.get("output", "") if isinstance(result, dict) else str(result)
    except Exception:
        logging.exception("run_and_comply failed")
        return "Sorry — something went wrong while processing that."
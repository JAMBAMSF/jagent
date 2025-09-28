import streamlit as st
from dotenv import load_dotenv
from agent.agent import build_agent, run_and_comply

load_dotenv()

st.set_page_config(page_title="JAgent - Agentic GenAI + ML Copilot (Beta) @ The J*Trading App", page_icon="🤖", layout="centered")

st.title("JAgent - Agentic GenAI + ML Copilot (Beta) @ The J*Trading App")
st.caption("Prototype - includes compliance and offline fallbacks.")

if "agent" not in st.session_state:
    st.session_state.agent = build_agent()

q = st.text_input("Ask me anything about your portfolio, prices, fraud checks, or sentiment:")
if st.button("Ask") and q:
    with st.spinner("Thinking..."):
        out = run_and_comply(st.session_state.agent, q)
    st.markdown(out)

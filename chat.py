"""Streamlit chat interface for the research agent."""

import asyncio

import streamlit as st

from app.actguard_client import actguard_client
from app.researcher.graph import run_research
from actguard.exceptions import ActGuardPaymentRequired, BudgetExceededError

MAX_HISTORY = 6  # keep last 6 messages (3 user + 3 assistant)

DEMO_USERS = ["alice", "bob", "charlie"]

st.set_page_config(page_title="Research Agent", layout="wide")
st.title("Research Agent")

# Sidebar: user switcher and clear chat
selected_user = st.sidebar.selectbox("Demo user", DEMO_USERS)

if "user_id" not in st.session_state:
    st.session_state.user_id = selected_user

# Clear chat when user switches
if st.session_state.user_id != selected_user:
    st.session_state.user_id = selected_user
    st.session_state.messages = []
    st.rerun()

if st.sidebar.button("Clear chat"):
    st.session_state.messages = []
    st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if query := st.chat_input("Ask a research question..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Run research
    with st.chat_message("assistant"):
        with st.spinner("Researching..."):
            try:
                with actguard_client.run(user_id=st.session_state.user_id):
                    with actguard_client.budget_guard(cost_limit=500):
                        report = asyncio.run(run_research(query))
                st.markdown(report)
                st.session_state.messages.append({"role": "assistant", "content": report})
            except ActGuardPaymentRequired as excp:
                msg = (
                        f"You're low on funds! Top up your account to continue researching. "
                    f"[Top up your account]({excp.topup_url})"
                )
                st.markdown(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except BudgetExceededError as exc:
                msg = f"Budget limit exceeded: {exc}"
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except Exception as exc:
                msg = f"Research failed: {exc}"
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})

    # Trim history to last N messages
    if len(st.session_state.messages) > MAX_HISTORY:
        st.session_state.messages = st.session_state.messages[-MAX_HISTORY:]

"""Streamlit chat interface for SupportGenie, the AI IT Support Assistant.

Run with:  streamlit run app.py

Chat history is persisted to SQLite (via ``src.db``) and the LangGraph
conversation state is persisted separately via a SqliteSaver checkpointer
(see ``src.graph``), so chats survive restarting the app -- not just
refreshing the browser.
"""

from __future__ import annotations

import uuid

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src import config, db
from src.graph import delete_thread_state, get_graph
from src.logging_config import logger

st.set_page_config(page_title="SupportGenie", page_icon="🧞", layout="centered")

# --- Setup (runs once per process) -------------------------------------------
db.init_db()

MAX_TITLE_LEN = 40


def _make_chat_title(first_message: str) -> str:
    title = first_message.strip().replace("\n", " ")
    if len(title) > MAX_TITLE_LEN:
        title = title[:MAX_TITLE_LEN].rstrip() + "…"
    return title or "New Chat"


def new_chat() -> str:
    """Create a brand-new, empty chat (persisted to SQLite) and make it active."""
    chat_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    db.create_chat(chat_id, thread_id, title="New Chat")
    st.session_state.active_chat_id = chat_id
    return chat_id


def switch_chat(chat_id: str) -> None:
    st.session_state.active_chat_id = chat_id


def delete_chat(chat_id: str, thread_id: str) -> None:
    """Permanently remove a chat's history and its LangGraph conversation state."""
    db.delete_chat(chat_id)
    delete_thread_state(thread_id)
    if st.session_state.get("active_chat_id") == chat_id:
        st.session_state.active_chat_id = None
    logger.info("Deleted chat %s from the UI", chat_id)


# --- Resolve the active chat, always backed by SQLite -------------------------
all_chats = db.list_chats()

if not st.session_state.get("active_chat_id") or not any(
    c["chat_id"] == st.session_state.active_chat_id for c in all_chats
):
    if all_chats:
        st.session_state.active_chat_id = all_chats[0]["chat_id"]
    else:
        new_chat()
        all_chats = db.list_chats()

active_chat = db.get_chat(st.session_state.active_chat_id)

# --- Sidebar ------------------------------------------------------------------
with st.sidebar:
    st.header("🧞 SupportGenie")
    st.caption("AI IT Support Assistant — LangGraph + tool calling")

    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()

    st.divider()
    st.markdown("**💬 Chat History**")
    st.caption("Saved locally — survives closing and restarting the app.")

    for chat in all_chats:
        is_active = chat["chat_id"] == st.session_state.active_chat_id
        label = f"{'🟢 ' if is_active else ''}{chat['title']}"

        col_select, col_delete = st.columns([5, 1])
        with col_select:
            if st.button(
                label,
                key=f"chat_btn_{chat['chat_id']}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                switch_chat(chat["chat_id"])
                st.rerun()
        with col_delete:
            if st.button("🗑️", key=f"chat_del_{chat['chat_id']}", help="Delete this chat"):
                delete_chat(chat["chat_id"], chat["thread_id"])
                st.rerun()

    st.divider()
    st.markdown(
        "**Available tools**\n"
        "- 🔎 Knowledge Search\n"
        "- 🎫 Ticket Lookup\n"
        "- ➕ Ticket Creation\n"
        "- 🆕 New Employee Registration\n"
    )

    st.divider()
    with st.expander("Sample employee IDs (pre-existing)"):
        st.code("EMP1001, EMP1002, EMP1003,\nEMP1004, EMP1005, EMP1024", language=None)
    with st.expander("Try asking..."):
        st.markdown(
            "- How do I reset my VPN password?\n"
            "- What is the status of ticket TCK-1001?\n"
            "- My VPN is not working, please raise a ticket.\n"
            "- I have a laptop issue, employee ID EMP1003.\n"
            "- **I'm a new employee, my ID isn't in the system.**\n"
        )

st.title("🧞 SupportGenie")
st.caption("Ask about IT issues, check ticket status, or raise a new support ticket.")

if not config.OPENAI_API_KEY:
    st.error(
        "OPENAI_API_KEY is not configured. Copy `.env.example` to `.env` and add your "
        "OpenAI API key, then restart the app.",
        icon="🚫",
    )
    st.stop()

# --- Render existing conversation --------------------------------------------
for turn in active_chat["history"]:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("tool_calls"):
            with st.expander("🔧 Tool activity"):
                for tc in turn["tool_calls"]:
                    st.markdown(f"**{tc['name']}**")
                    st.json(tc["args"], expanded=False)
                    st.markdown("Result:")
                    st.json(tc["result"], expanded=False)

if not active_chat["history"]:
    st.info("This is a new chat. Ask a question to get started!", icon="💬")

# --- Handle new input ----------------------------------------------------------
user_input = st.chat_input("Type your IT support question here...")

if user_input:
    history = active_chat["history"]
    title_update = _make_chat_title(user_input) if not history else None

    history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    graph = get_graph()
    config_dict = {"configurable": {"thread_id": active_chat["thread_id"]}}

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = graph.invoke(
                    {"messages": [HumanMessage(content=user_input)]},
                    config=config_dict,
                )
                messages = result["messages"]

                # Collect the tool calls + results made during this turn for display.
                tool_activity = []
                for i, msg in enumerate(messages):
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tc in msg.tool_calls:
                            # Find the matching ToolMessage response.
                            tool_result = next(
                                (
                                    m.content
                                    for m in messages
                                    if isinstance(m, ToolMessage) and m.tool_call_id == tc["id"]
                                ),
                                None,
                            )
                            tool_activity.append(
                                {"name": tc["name"], "args": tc["args"], "result": tool_result}
                            )

                final_message = messages[-1]
                final_text = final_message.content or "(No response generated.)"

                st.markdown(final_text)
                if tool_activity:
                    with st.expander("🔧 Tool activity"):
                        for tc in tool_activity:
                            st.markdown(f"**{tc['name']}**")
                            st.json(tc["args"], expanded=False)
                            st.markdown("Result:")
                            st.json(tc["result"], expanded=False)

                history.append(
                    {"role": "assistant", "content": final_text, "tool_calls": tool_activity}
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Agent invocation failed")
                error_text = (
                    "Sorry, something went wrong while processing your request. "
                    f"Details: {exc}"
                )
                st.error(error_text, icon="⚠️")
                history.append({"role": "assistant", "content": error_text, "tool_calls": []})

    db.update_chat(active_chat["chat_id"], title=title_update, history=history)

    # Refresh the sidebar so the auto-generated chat title shows immediately.
    st.rerun()

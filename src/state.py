"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Conversation state threaded through the LangGraph graph.

    ``messages`` accumulates via ``add_messages`` so each node only needs to
    return the *new* messages it produced, and LangGraph's checkpointer
    persists this whole state across turns for a given thread_id -- this is
    what lets the agent remember the employee_id and prior context across
    multiple user turns.
    """

    messages: Annotated[list, add_messages]
    employee_id: Optional[str]

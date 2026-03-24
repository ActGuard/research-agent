"""State definitions for the research agent graph."""

import operator
from typing import Annotated, Literal, TypedDict


# ── Researcher subgraph state ────────────────────────────────────────────────

class ResearcherState(TypedDict):
    """State for a single researcher subgraph invocation."""

    researcher_messages: list[dict]  # ReAct conversation history (role/content dicts)
    research_topic: str
    tool_call_iterations: int
    compressed_research: str
    raw_notes: list[str]


# ── Supervisor subgraph state ────────────────────────────────────────────────

class SupervisorState(TypedDict):
    """State for the supervisor subgraph."""

    supervisor_messages: list[dict]  # Supervisor conversation history
    research_brief: str
    query: str
    query_type: str
    notes: Annotated[list[str], operator.add]  # Compressed research from researchers
    research_iterations: int


# ── Main graph state ─────────────────────────────────────────────────────────

class ResearchState(TypedDict):
    """Top-level state for the research pipeline."""

    query: str
    query_type: Literal["quick", "standard", "deep", "comparison"]
    research_brief: str
    # Research notes accumulated by the supervisor (list of compressed summaries)
    notes: Annotated[list[str], operator.add]
    max_rounds: int
    report: str
    final_report: str
    # Supervisor subgraph state (shared keys)
    supervisor_messages: list[dict]
    research_iterations: int

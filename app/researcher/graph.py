"""Research agent graph: supervisor-based architecture.

Main graph:
  START → classify_query → create_research_brief → research_supervisor → write_report → [refine] → END

Supervisor subgraph (research_supervisor):
  START → supervisor → supervisor_tools ⟲ → END

Researcher subgraph (invoked by supervisor_tools):
  START → researcher → researcher_tools ⟲ → compress_research → END
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.researcher.actguard_client import actguard_client
from app.researcher.errors import BudgetExhaustedError
from app.researcher.nodes import classify_query, create_research_brief, refine_report, write_report
from app.researcher.prompts import (
    COMPRESS_RESEARCH_SYSTEM,
    COMPRESS_RESEARCH_USER,
    RESEARCHER_SYSTEM,
    SUPERVISOR_SYSTEM,
)
from app.researcher.schemas import TextResponse
from app.researcher.state import ResearcherState, ResearchState, SupervisorState
from app.researcher.tools import RESEARCHER_TOOLS, SUPERVISOR_TOOLS
from app.services import llm, scraper, search

import actguard
from actguard.exceptions import BudgetExceededError

logger = logging.getLogger(__name__)

# ─── Researcher subgraph nodes ───────────────────────────────────────────────


async def researcher(state: ResearcherState) -> dict:
    """LLM step of the researcher ReAct loop."""
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    system_prompt = RESEARCHER_SYSTEM.format(current_date=current_date)

    history = list(state.get("researcher_messages", []))
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
    ]

    with actguard_client.budget_guard(name="researcher"):
        response = await llm.chat_completion(
            messages=messages,
            tools=RESEARCHER_TOOLS,
            model=settings.model_researcher,
        )

    history.append(response)
    return {
        "researcher_messages": history,
        "tool_call_iterations": state.get("tool_call_iterations", 0) + 1,
    }


def _should_continue_research(state: ResearcherState) -> str:
    """Route after researcher: tools, or compress and finish."""
    messages = state.get("researcher_messages", [])
    if not messages:
        return "compress_research"

    last = messages[-1]
    has_tool_calls = bool(last.get("tool_calls"))
    under_limit = state.get("tool_call_iterations", 0) < settings.max_researcher_tool_calls

    if has_tool_calls and under_limit:
        return "researcher_tools"
    return "compress_research"


async def researcher_tools(state: ResearcherState) -> dict:
    """Execute tool calls from the researcher."""
    history = list(state.get("researcher_messages", []))
    last = history[-1] if history else {}
    tool_calls = last.get("tool_calls", [])

    raw_notes: list[str] = []

    for tc in tool_calls:
        name = tc["name"]
        args = tc["args"]
        tc_id = tc["id"]

        try:
            if name == "web_search":
                with actguard_client.budget_guard(name="researcher_search"):
                    results = await search.search(args["query"])
                content = "\n".join(
                    f"- [{r.title}]({r.url}): {r.content}" for r in results
                ) or "No results found."

            elif name == "scrape_url":
                with actguard_client.budget_guard(name="researcher_scrape"):
                    pages = await scraper.scrape_urls([args["url"]])
                if pages:
                    page = pages[0]
                    text = page.text[:50_000]  # truncate large pages
                    content = f"# {page.title}\nURL: {page.url}\n\n{text}"
                    raw_notes.append(f"[{page.title}]({page.url}):\n{text[:5000]}")
                else:
                    content = "Failed to scrape the URL."
            else:
                content = f"Unknown tool: {name}"

        except Exception as e:
            content = f"Error executing {name}: {e}"
            logger.warning("researcher_tools error: %s — %s", name, e)

        history.append({
            "role": "tool",
            "content": content,
            "tool_call_id": tc_id,
        })

    return {
        "researcher_messages": history,
        "raw_notes": raw_notes,
    }


async def compress_research(state: ResearcherState) -> dict:
    """Compress researcher conversation into a concise summary."""
    messages = state.get("researcher_messages", [])
    topic = state.get("research_topic", "")

    # Build raw notes from the conversation
    raw_notes_parts = list(state.get("raw_notes", []))
    for m in messages:
        if m["role"] == "assistant" and m.get("content"):
            raw_notes_parts.append(m["content"])

    raw_text = "\n\n".join(raw_notes_parts) if raw_notes_parts else "No research notes collected."

    prompt = COMPRESS_RESEARCH_USER.format(
        research_topic=topic,
        raw_notes=raw_text,
    )

    with actguard_client.budget_guard(name="compress_research"):
        result = await llm.structured_output(
            messages=[
                {"role": "system", "content": COMPRESS_RESEARCH_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_model=TextResponse,
            model=settings.model_compress,
        )

    return {"compressed_research": result.text}


# Build researcher subgraph
_researcher_builder = StateGraph(ResearcherState)
_researcher_builder.add_node("researcher", researcher)
_researcher_builder.add_node("researcher_tools", researcher_tools)
_researcher_builder.add_node("compress_research", compress_research)

_researcher_builder.add_edge(START, "researcher")
_researcher_builder.add_conditional_edges(
    "researcher",
    _should_continue_research,
    {"researcher_tools": "researcher_tools", "compress_research": "compress_research"},
)
_researcher_builder.add_edge("researcher_tools", "researcher")
_researcher_builder.add_edge("compress_research", END)

researcher_graph = _researcher_builder.compile()


# ─── Supervisor subgraph nodes ───────────────────────────────────────────────


def _get_supervisor_system_prompt() -> str:
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return SUPERVISOR_SYSTEM.format(
        current_date=current_date,
        max_concurrent_researchers=settings.max_concurrent_researchers,
        max_supervisor_iterations=settings.max_supervisor_iterations,
    )


async def supervisor(state: SupervisorState) -> dict:
    """LLM step of the supervisor loop."""
    history = list(state.get("supervisor_messages", []))

    # On first call, inject the research brief as the initial user message
    if not history:
        brief = state.get("research_brief") or state.get("query", "")
        history = [{"role": "user", "content": brief}]

    messages = [
        {"role": "system", "content": _get_supervisor_system_prompt()},
        *history,
    ]

    with actguard_client.budget_guard(name="supervisor"):
        response = await llm.chat_completion(
            messages=messages,
            tools=SUPERVISOR_TOOLS,
            model=settings.model_supervisor,
        )

    history.append(response)
    return {
        "supervisor_messages": history,
        "research_iterations": state.get("research_iterations", 0) + 1,
    }


def _should_continue_supervisor(state: SupervisorState) -> str:
    """Route after supervisor: process tools or finish."""
    messages = state.get("supervisor_messages", [])
    if not messages:
        return END

    last = messages[-1]
    if not last.get("tool_calls"):
        return END
    return "supervisor_tools"


async def supervisor_tools(state: SupervisorState) -> dict:
    """Execute supervisor tool calls: think, ConductResearch, ResearchComplete."""
    history = list(state.get("supervisor_messages", []))
    last = history[-1] if history else {}
    tool_calls = last.get("tool_calls", [])
    iterations = state.get("research_iterations", 0)

    # Check for ResearchComplete or iteration limit
    research_complete = any(tc["name"] == "ResearchComplete" for tc in tool_calls)
    exceeded_limit = iterations > settings.max_supervisor_iterations

    if research_complete or exceeded_limit:
        # Signal end — return history as-is (no new tool messages)
        return {"supervisor_messages": history}

    new_notes: list[str] = []

    # Separate tool calls by type
    think_calls = [tc for tc in tool_calls if tc["name"] == "think"]
    research_calls = [tc for tc in tool_calls if tc["name"] == "ConductResearch"]

    # Handle think calls
    for tc in think_calls:
        history.append({
            "role": "tool",
            "content": f"Reflection recorded: {tc['args']['thought']}",
            "tool_call_id": tc["id"],
        })

    # Handle ConductResearch calls
    for tc in research_calls:
        topics = tc["args"].get("topics", [])
        # Limit concurrent researchers
        allowed = topics[: settings.max_concurrent_researchers]

        # Launch researchers in parallel
        tasks = [
            researcher_graph.ainvoke({
                "researcher_messages": [
                    {"role": "user", "content": f"Research the following topic thoroughly:\n\n{topic}"}
                ],
                "research_topic": topic,
                "tool_call_iterations": 0,
                "compressed_research": "",
                "raw_notes": [],
            })
            for topic in allowed
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        findings_parts: list[str] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Researcher failed for topic %r: %s", allowed[i], result)
                findings_parts.append(f"[Research on '{allowed[i]}' failed: {result}]")
            else:
                compressed = result.get("compressed_research", "No findings.")
                findings_parts.append(compressed)
                new_notes.append(compressed)

        # Build tool response
        combined = "\n\n---\n\n".join(findings_parts)
        history.append({
            "role": "tool",
            "content": combined,
            "tool_call_id": tc["id"],
        })

        # Report overflow if any
        overflow = topics[settings.max_concurrent_researchers:]
        if overflow:
            logger.warning(
                "Supervisor requested %d topics but max is %d; dropped: %s",
                len(topics),
                settings.max_concurrent_researchers,
                overflow,
            )

    return {
        "supervisor_messages": history,
        "notes": new_notes,
    }


def _check_supervisor_done(state: SupervisorState) -> str:
    """After supervisor_tools: continue or end."""
    messages = state.get("supervisor_messages", [])
    iterations = state.get("research_iterations", 0)

    if iterations > settings.max_supervisor_iterations:
        return END

    if not messages:
        return END

    # Find the last assistant message and check for ResearchComplete
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            if any(tc["name"] == "ResearchComplete" for tc in m["tool_calls"]):
                return END
            break

    # Check if the last message is a tool response (normal continuation)
    last = messages[-1]
    if last.get("role") == "tool":
        return "supervisor"

    return END


# Build supervisor subgraph
_supervisor_builder = StateGraph(SupervisorState)
_supervisor_builder.add_node("supervisor", supervisor)
_supervisor_builder.add_node("supervisor_tools", supervisor_tools)

_supervisor_builder.add_edge(START, "supervisor")
_supervisor_builder.add_conditional_edges(
    "supervisor",
    _should_continue_supervisor,
    {"supervisor_tools": "supervisor_tools", END: END},
)
_supervisor_builder.add_conditional_edges(
    "supervisor_tools",
    _check_supervisor_done,
    {"supervisor": "supervisor", END: END},
)

supervisor_graph = _supervisor_builder.compile()


# ─── Main graph ──────────────────────────────────────────────────────────────


def should_refine(state: ResearchState) -> str:
    if state.get("query_type") == "quick":
        return "end"
    return "refine_report"


workflow = StateGraph(ResearchState)

workflow.add_node("classify_query", classify_query)
workflow.add_node("create_research_brief", create_research_brief)
workflow.add_node("research_supervisor", supervisor_graph)
workflow.add_node("write_report", write_report)
workflow.add_node("refine_report", refine_report)

workflow.add_edge(START, "classify_query")
workflow.add_edge("classify_query", "create_research_brief")
workflow.add_edge("create_research_brief", "research_supervisor")
workflow.add_edge("research_supervisor", "write_report")
workflow.add_conditional_edges(
    "write_report",
    should_refine,
    {"refine_report": "refine_report", "end": END},
)
workflow.add_edge("refine_report", END)

graph = workflow.compile()


async def run_research(query: str) -> str:
    try:
        with actguard_client.run(user_id="research-agent"):
            with actguard_client.budget_guard(cost_limit=500):
                result = await graph.ainvoke(
                    {
                        "query": query,
                        "query_type": "standard",
                        "research_brief": "",
                        "notes": [],
                        "max_rounds": 1,
                        "report": "",
                        "final_report": "",
                        "supervisor_messages": [],
                        "research_iterations": 0,
                    }
                )
    except BudgetExceededError as be:
        msg = f"BUDGET EXCEEDED: Research stopped — the budget limit was reached. {be.details}"
        print(f"\033[91m{msg}\033[0m", file=sys.stderr)
        raise BudgetExhaustedError(msg) from None
    except Exception as e:
        print(f"\033[91m{e}\033[0m", file=sys.stderr)
        raise e
    return result["final_report"]

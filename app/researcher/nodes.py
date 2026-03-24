"""Node implementations for the main research graph.

Kept: classify_query, create_research_brief, write_report, refine_report.
Removed: plan_research, research_worker, compress_evidence, evaluate_coverage
(replaced by supervisor/researcher subgraphs in graph.py).
"""

import logging
from datetime import datetime, timezone

from app.config import settings
from app.researcher.actguard_client import actguard_client
from app.researcher.prompts import (
    BRIEF_SYSTEM,
    BRIEF_USER,
    CLASSIFY_SYSTEM,
    CLASSIFY_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    REPORT_SYSTEM,
    REPORT_USER,
)
from app.researcher.schemas import QueryClassification, TextResponse
from app.researcher.state import ResearchState
from app.services import llm

logger = logging.getLogger(__name__)

_MAX_ROUNDS_BY_TYPE = {
    "quick": 0,
    "standard": 1,
    "deep": 2,
    "comparison": 2,
}


async def classify_query(state: ResearchState) -> dict:
    prompt = CLASSIFY_USER.format(query=state["query"])
    with actguard_client.budget_guard(name="classify_query"):
        result = await llm.structured_output(
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_model=QueryClassification,
            model=settings.model_classify,
        )
    query_type = result.query_type
    max_rounds = _MAX_ROUNDS_BY_TYPE[query_type]
    logger.info("classify_query — type=%s, max_rounds=%d", query_type, max_rounds)
    return {"query_type": query_type, "max_rounds": max_rounds}


async def create_research_brief(state: ResearchState) -> dict:
    query_type = state.get("query_type", "standard")
    if query_type == "quick":
        logger.info("create_research_brief — quick query, using original query as brief")
        return {"research_brief": state["query"]}

    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    prompt = BRIEF_USER.format(
        query=state["query"],
        query_type=query_type,
        current_date=current_date,
    )
    with actguard_client.budget_guard(name="create_research_brief"):
        result = await llm.structured_output(
            messages=[
                {"role": "system", "content": BRIEF_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_model=TextResponse,
            temperature=0.3,
            model=settings.model_brief,
        )
    brief = result.text
    logger.info("create_research_brief — brief length %d chars", len(brief))
    return {"research_brief": brief}


async def write_report(state: ResearchState) -> dict:
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    notes = state.get("notes", [])
    evidence_text = "\n\n---\n\n".join(notes) if notes else "No evidence collected."

    prompt = REPORT_USER.format(
        query=state["query"],
        query_type=state.get("query_type", "standard"),
        evidence=evidence_text,
        current_date=current_date,
    )
    with actguard_client.budget_guard(name="write_report"):
        result = await llm.structured_output(
            messages=[
                {"role": "system", "content": REPORT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_model=TextResponse,
            temperature=0.5,
            model=settings.model_write_report,
        )
    report = result.text
    logger.info("write_report — report length %d chars", len(report))
    return {"report": report, "final_report": report}


async def refine_report(state: ResearchState) -> dict:
    notes = state.get("notes", [])
    evidence_text = "\n\n---\n\n".join(notes) if notes else "No evidence collected."

    prompt = REFINE_USER.format(
        query=state["query"],
        report=state["report"],
        evidence=evidence_text,
    )
    with actguard_client.budget_guard(name="refine_report"):
        result = await llm.structured_output(
            messages=[
                {"role": "system", "content": REFINE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_model=TextResponse,
            temperature=0.4,
            model=settings.model_refine_report,
        )
    final_report = result.text
    logger.info("refine_report — final report length %d chars", len(final_report))
    return {"final_report": final_report}

import pytest

from app.researcher.graph import run_research


@pytest.mark.asyncio
async def test_run_research():
    report = await run_research("What are the latest advances in quantum computing?")
    assert isinstance(report, str)
    assert len(report) > 100
    assert "#" in report  # Should contain markdown headings


@pytest.mark.asyncio
async def test_quick_query():
    report = await run_research("What is the capital of France?")
    assert isinstance(report, str)
    assert len(report) > 50


@pytest.mark.asyncio
async def test_deep_query():
    report = await run_research(
        "Compare the economic policies of the US and EU regarding AI regulation"
    )
    assert isinstance(report, str)
    assert len(report) > 100
    assert "#" in report

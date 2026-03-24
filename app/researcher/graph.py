"""Research agent: linear pipeline.

search → scrape + compress → assemble context → generate report
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

from app.config import settings
from app.researcher.actguard_client import actguard_client
from app.researcher.errors import BudgetExhaustedError
from app.researcher.prompts import REPORT_SYSTEM, REPORT_USER
from app.researcher.schemas import TextResponse
from app.services import llm, scraper, search
from app.services.embeddings import compress_page_for_query

from actguard.exceptions import BudgetExceededError

logger = logging.getLogger(__name__)


async def _search(query: str) -> list[search.SearchResult]:
    """Step 1: Search the web via Tavily."""
    with actguard_client.budget_guard(name="search"):
        results = await search.search(query)
    logger.info("Search returned %d results for %r", len(results), query)
    return results


async def _compress_one(query: str, title: str, url: str, text: str) -> str | None:
    """Compress a single page's text via embeddings. Returns None on failure."""
    try:
        return await compress_page_for_query(query=query, title=title, url=url, text=text)
    except Exception as e:
        logger.warning("Failed to compress %s: %s", url, e)
        return None


async def _scrape_and_compress(
    query: str,
    results: list[search.SearchResult],
) -> list[str]:
    """Step 2: For each result, compress raw_content or scrape then compress."""
    compressed: list[str] = []

    # Split results into those with raw_content and those needing scraping
    have_content: list[search.SearchResult] = []
    need_scrape: list[search.SearchResult] = []

    for r in results[: settings.max_scrape_urls]:
        if r.raw_content:
            have_content.append(r)
        else:
            need_scrape.append(r)

    # Compress pages that already have raw_content (concurrent)
    if have_content:
        tasks = [
            _compress_one(query, r.title, r.url, r.raw_content)
            for r in have_content
        ]
        results_compressed = await asyncio.gather(*tasks)
        for text in results_compressed:
            if text:
                compressed.append(text)

    # Scrape URLs that lack raw_content, then compress
    if need_scrape:
        urls = [r.url for r in need_scrape]
        with actguard_client.budget_guard(name="scrape"):
            pages = await scraper.scrape_urls(urls)

        # Build a lookup for scraped pages by URL
        page_map = {p.url: p for p in pages}
        tasks = []
        for r in need_scrape:
            page = page_map.get(r.url)
            if page and page.text:
                tasks.append(_compress_one(query, page.title, page.url, page.text))
            elif r.content:
                # Fall back to Tavily snippet
                compressed.append(f"# {r.title}\nURL: {r.url}\n\n{r.content}")

        if tasks:
            results_compressed = await asyncio.gather(*tasks)
            for text in results_compressed:
                if text:
                    compressed.append(text)

    # For any remaining results beyond max_scrape_urls, use Tavily snippets
    for r in results[settings.max_scrape_urls:]:
        if r.content:
            compressed.append(f"# {r.title}\nURL: {r.url}\n\n{r.content}")

    return compressed


def _assemble_context(pages: list[str]) -> str:
    """Step 3: Join compressed pages, truncate if needed."""
    context = "\n\n---\n\n".join(pages)
    if len(context) > settings.max_context_chars:
        context = context[: settings.max_context_chars]
        logger.info("Context truncated to %d chars", settings.max_context_chars)
    return context


async def _generate_report(query: str, context: str) -> str:
    """Step 4: Single LLM call to produce the final report."""
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")

    messages = [
        {"role": "system", "content": REPORT_SYSTEM},
        {"role": "user", "content": REPORT_USER.format(
            current_date=current_date,
            query=query,
            context=context,
        )},
    ]

    with actguard_client.budget_guard(name="write_report"):
        result = await llm.structured_output(
            messages=messages,
            response_model=TextResponse,
            model=settings.model_write_report,
            temperature=0.5,
        )

    return result.text


async def run_research(query: str) -> str:
    """Run the full research pipeline: search → scrape → compress → report."""
    try:
        with actguard_client.run(user_id="research-agent"):
            with actguard_client.budget_guard(cost_limit=500):
                # Step 1: Search
                results = await _search(query)

                if not results:
                    return f"No search results found for: {query}"

                # Step 2: Scrape + compress
                pages = await _scrape_and_compress(query, results)

                if not pages:
                    return f"Could not extract content from search results for: {query}"

                # Step 3: Assemble context
                context = _assemble_context(pages)

                # Step 4: Generate report
                report = await _generate_report(query, context)

    except BudgetExceededError as be:
        msg = f"BUDGET EXCEEDED: Research stopped — the budget limit was reached. {be.details}"
        print(f"\033[91m{msg}\033[0m", file=sys.stderr)
        raise BudgetExhaustedError(msg) from None
    except Exception as e:
        print(f"\033[91m{e}\033[0m", file=sys.stderr)
        raise

    return report

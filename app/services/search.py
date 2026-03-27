import logging
from dataclasses import dataclass

from tavily import AsyncTavilyClient

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float
    raw_content: str = ""


async def search(query: str, max_results: int | None = None) -> list[SearchResult]:
    max_results = max_results or settings.max_search_results
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    response = await client.search(query=query, max_results=max_results, include_raw_content=True, country=settings.search_country)
    results = response.get("results", [])
    logger.info("search — query=%r results=%d", query, len(results))
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
            score=r.get("score", 0.0),
            raw_content=r.get("raw_content", ""),
        )
        for r in results
    ]

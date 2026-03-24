import logging
from dataclasses import dataclass

from tavily import AsyncTavilyClient

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncTavilyClient | None = None


def _get_client() -> AsyncTavilyClient:
    global _client
    if _client is None:
        _client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return _client


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float


async def search(query: str, max_results: int | None = None) -> list[SearchResult]:
    max_results = max_results or settings.max_search_results
    response = await _get_client().search(query=query, max_results=max_results)
    results = response.get("results", [])
    logger.info("search — query=%r results=%d", query, len(results))
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
            score=r.get("score", 0.0),
        )
        for r in results
    ]

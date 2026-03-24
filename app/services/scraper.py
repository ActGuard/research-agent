import logging
from dataclasses import dataclass

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter

logger = logging.getLogger(__name__)

_TIMEOUT_MS = 15_000
_MAX_TEXT = 100_000


@dataclass
class PageContent:
    url: str
    title: str
    text: str


async def scrape_urls(urls: list[str]) -> list[PageContent]:
    if not urls:
        return []

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        page_timeout=_TIMEOUT_MS,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter()
        ),
    )

    results: list[PageContent] = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        crawl_results = await crawler.arun_many(urls, config=run_config)
        for cr in crawl_results:
            if not cr.success:
                logger.warning("Failed to scrape %s — %s", cr.url, cr.error_message)
                continue
            title = cr.metadata.get("title", "") if cr.metadata else ""
            text = cr.markdown.fit_markdown or cr.markdown.raw_markdown or ""
            results.append(PageContent(
                url=cr.url,
                title=title,
                text=text[:_MAX_TEXT],
            ))
    return results

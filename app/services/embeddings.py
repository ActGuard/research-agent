"""Embedding-based semantic compression for scraped pages."""

import logging
from dataclasses import dataclass

import numpy as np
from langchain_openai import OpenAIEmbeddings

from app.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_CHARS = 3_000


@dataclass
class Document:
    text: str
    url: str
    title: str
    chunk_index: int


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split *text* into overlapping chunks."""
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


async def compress_page_for_query(
    query: str,
    title: str,
    url: str,
    text: str,
) -> str:
    """Return only the chunks of *text* semantically relevant to *query*."""
    if not text:
        return f"# {title}\nURL: {url}\n\n(empty page)"

    chunks = _chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        return f"# {title}\nURL: {url}\n\n(empty page)"

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )

    chunk_vectors = await embeddings.aembed_documents(chunks)
    query_vector = await embeddings.aembed_query(query)

    query_arr = np.array(query_vector)
    threshold = settings.similarity_threshold

    relevant: list[tuple[int, str]] = []
    for i, vec in enumerate(chunk_vectors):
        sim = _cosine_similarity(np.array(vec), query_arr)
        if sim >= threshold:
            relevant.append((i, chunks[i]))

    if not relevant:
        logger.info(
            "No chunks above threshold %.2f for %s — falling back to first %d chars",
            threshold, url, _FALLBACK_CHARS,
        )
        return f"# {title}\nURL: {url}\n\n{text[:_FALLBACK_CHARS]}"

    relevant.sort(key=lambda t: t[0])
    joined = "\n\n".join(chunk for _, chunk in relevant)
    logger.info(
        "compress_page_for_query — %d/%d chunks kept for %s",
        len(relevant), len(chunks), url,
    )
    return f"# {title}\nURL: {url}\n\n{joined}"

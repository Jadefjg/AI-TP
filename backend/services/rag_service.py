from __future__ import annotations

import asyncio
import re
from collections import Counter

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import KnowledgeChunk
from backend.services.rag_embedding import cosine_similarity, embed_text

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    return [x.lower() for x in _TOKEN_PATTERN.findall(text or "")]


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [x.strip() for x in re.split(r"\n{2,}", text) if x.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    cur = ""
    for p in paragraphs:
        if len(cur) + len(p) + 2 <= chunk_size:
            cur = f"{cur}\n\n{p}" if cur else p
            continue
        if cur:
            chunks.append(cur)
        if len(p) <= chunk_size:
            cur = p
        else:
            for i in range(0, len(p), chunk_size):
                chunks.append(p[i : i + chunk_size])
            cur = ""
    if cur:
        chunks.append(cur)
    return chunks


async def _embed_chunk_row(content: str) -> tuple[list[float], str]:
    return await embed_text(content)


def ingest_knowledge(
    db: Session,
    *,
    project_id: int,
    source: str,
    title: str | None,
    content: str,
    tags: list[str] | None = None,
    compute_embeddings: bool = True,
) -> list[KnowledgeChunk]:
    settings = get_settings()
    chunks = _chunk_text(content, settings.rag_chunk_size)
    created: list[KnowledgeChunk] = []
    for c in chunks:
        row = KnowledgeChunk(
            project_id=project_id,
            source=(source or "manual")[:255],
            title=(title or "")[:255] or None,
            content=c,
            tags=tags or None,
        )
        db.add(row)
        created.append(row)
    db.flush()

    if compute_embeddings and created:
        vectors = asyncio.run(_embed_many([x.content for x in created]))
        for row, (vec, model) in zip(created, vectors, strict=True):
            row.embedding = vec
            row.embedding_model = model

    db.commit()
    for x in created:
        db.refresh(x)
    return created


async def _embed_many(texts: list[str]) -> list[tuple[list[float], str]]:
    out: list[tuple[list[float], str]] = []
    for t in texts:
        out.append(await embed_text(t))
    return out


def _lexical_retrieve(candidates: list[KnowledgeChunk], query: str, k: int) -> list[KnowledgeChunk]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return candidates[:k]

    q_counter = Counter(q_tokens)
    scores: list[tuple[float, KnowledgeChunk]] = []
    for item in candidates:
        d_counter = Counter(_tokenize(item.content))
        if not d_counter:
            continue
        overlap = sum(min(cnt, d_counter[t]) for t, cnt in q_counter.items())
        norm = (sum(q_counter.values()) * sum(d_counter.values())) ** 0.5
        score = overlap / norm if norm else 0.0
        if score > 0:
            scores.append((score, item))
    scores.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scores[:k]]


def _vector_retrieve(
    candidates: list[KnowledgeChunk],
    query_vec: list[float],
    k: int,
    min_score: float,
) -> list[KnowledgeChunk]:
    scored: list[tuple[float, KnowledgeChunk]] = []
    for item in candidates:
        if not isinstance(item.embedding, list) or not item.embedding:
            continue
        score = cosine_similarity(query_vec, [float(x) for x in item.embedding])
        if score >= min_score:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:k]]


async def retrieve_context_chunks_async(
    db: Session,
    *,
    project_id: int,
    query: str,
    top_k: int | None = None,
) -> list[KnowledgeChunk]:
    settings = get_settings()
    k = top_k or settings.rag_top_k
    candidates = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.project_id == project_id)
        .order_by(KnowledgeChunk.id.desc())
        .limit(500)
        .all()
    )
    if not candidates:
        return []

    query_vec, _ = await embed_text(query)
    vector_hits = _vector_retrieve(candidates, query_vec, k, settings.rag_vector_min_score)
    if vector_hits:
        return vector_hits
    return _lexical_retrieve(candidates, query, k)


def retrieve_context_chunks(db: Session, *, project_id: int, query: str, top_k: int | None = None) -> list[KnowledgeChunk]:
    return asyncio.run(retrieve_context_chunks_async(db, project_id=project_id, query=query, top_k=top_k))


def search_knowledge_with_scores(
    db: Session,
    *,
    project_id: int,
    query: str,
    top_k: int | None = None,
) -> list[dict]:
    settings = get_settings()
    k = top_k or settings.rag_top_k
    chunks = retrieve_context_chunks(db, project_id=project_id, query=query, top_k=k)
    try:
        query_vec, model = asyncio.run(embed_text(query))
    except RuntimeError:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            query_vec, model = pool.submit(lambda: asyncio.run(embed_text(query))).result()

    out: list[dict] = []
    for ch in chunks:
        score = None
        if isinstance(ch.embedding, list) and ch.embedding:
            score = round(cosine_similarity(query_vec, [float(x) for x in ch.embedding]), 4)
        out.append(
            {
                "id": ch.id,
                "source": ch.source,
                "title": ch.title,
                "content": ch.content,
                "score": score,
                "embedding_model": ch.embedding_model or model,
            }
        )
    return out

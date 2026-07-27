from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import httpx

from backend.core.config import get_settings

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
_EMBED_DIM = 384


def _tokenize(text: str) -> list[str]:
    return [x.lower() for x in _TOKEN_PATTERN.findall(text or "")]


def embed_text_local(text: str, *, dim: int = _EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in _tokenize(text):
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


async def embed_text(text: str) -> tuple[list[float], str]:
    settings = get_settings()
    mode = (getattr(settings, "rag_embedding_mode", None) or "auto").strip().lower()
    if mode in {"local", "hash"} or not settings.openai_api_key:
        return embed_text_local(text), "local_hash"
    if mode in {"auto", "openai"}:
        try:
            vector = await _embed_openai(text, settings)
            return vector, "openai"
        except Exception:  # noqa: BLE001
            return embed_text_local(text), "local_hash_fallback"
    return embed_text_local(text), "local_hash"


async def _embed_openai(text: str, settings: Any) -> list[float]:
    payload = {"model": getattr(settings, "rag_embedding_model", "text-embedding-3-small"), "input": text[:8000]}
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    base = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.post(f"{base}/embeddings", json=payload, headers=headers)
        res.raise_for_status()
        data = res.json()
    row = (data.get("data") or [{}])[0]
    embedding = row.get("embedding")
    if not isinstance(embedding, list):
        raise ValueError("invalid embedding response")
    return [float(x) for x in embedding]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)

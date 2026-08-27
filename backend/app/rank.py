"""Order jobs by cheap similarity so the expensive model reads the best first.

The arithmetic that forces this to exist: a scan now returns ~850 postings, and
one `qwen3:8b` evaluation costs 10-30s on an 8GB card. Scoring everything is
about three hours of pinned GPU per cycle, which is not a product. Spec §4.2
funnels instead: embed everything for ~50ms each, then spend the rubric on only
the top slice.

This is a reading order, not a judgement. The LLM still does the scoring; this
only decides what it looks at first. So a mediocre ranking costs you a slightly
worse queue, never a wrong score — which is why every failure path here
degrades to "original order" rather than raising.
"""

from __future__ import annotations

import math

from app import llm, store

# nomic-embed-text has a 2048-token window; ~1200 chars of title+company+intro
# is plenty to place a posting and keeps the batch fast.
MAX_EMBED_CHARS = 1200

# How many jobs the expensive model is allowed to read per cycle (spec §4.2).
EVAL_BUDGET = 25

_PROFILE_CACHE_KEY = "__profile__"


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, degrading to 0.0 rather than raising.

    Mismatched lengths are a real case: swapping the embedding model leaves
    vectors of the old dimension in the cache. That should cost ranking
    quality for one cycle, not crash the pipeline.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def job_text(job) -> str:
    parts = [job.title or "", job.company or "", job.location or "", job.description or ""]
    return " — ".join(p for p in parts if p)[:MAX_EMBED_CHARS]


def profile_text(profile) -> str:
    parts = [
        " ".join(profile.target_roles or []),
        " ".join(profile.skills or []),
        (profile.resume_text or "")[:600],
    ]
    return " — ".join(p for p in parts if p)[:MAX_EMBED_CHARS]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Delegated to llm so tests can substitute it without touching the network."""
    return llm.embed(texts)


def rank_jobs(profile, jobs: list) -> list[tuple[object, float]]:
    """[(job, similarity)] best first. Never raises."""
    if not jobs:
        return []

    cache = store.load_embeddings()
    wanted: dict[str, str] = {}

    if _PROFILE_CACHE_KEY not in cache:
        wanted[_PROFILE_CACHE_KEY] = profile_text(profile)
    for j in jobs:
        if j.id not in cache:
            wanted[j.id] = job_text(j)

    if wanted:
        keys = list(wanted)
        try:
            vectors = embed_texts([wanted[k] for k in keys])
        except Exception:
            # Ollama down, model not pulled, whatever — arbitrary order still
            # beats no evaluation at all.
            return [(j, 0.0) for j in jobs]
        for k, v in zip(keys, vectors):
            cache[k] = v
        try:
            store.save_embeddings(cache)
        except Exception:
            pass          # a cold cache next time is not worth failing a scan

    pv = cache.get(_PROFILE_CACHE_KEY) or []
    scored = [(j, cosine(pv, cache.get(j.id) or [])) for j in jobs]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def top_n(profile, jobs: list, n: int = EVAL_BUDGET) -> list:
    """The `n` jobs most worth spending the expensive model on."""
    return [j for j, _ in rank_jobs(profile, jobs)[:n]]

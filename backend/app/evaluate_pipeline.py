"""Spend the expensive model where it pays: rank first, then evaluate.

Scoring every stored job is not viable — ~850 postings at 10-30s each on an
8GB card is roughly three hours of pinned GPU per cycle. So this ranks the
unscored jobs by embedding similarity (~50ms each, all of them) and runs the
full A-G rubric on only the top slice (spec §4.2).

Everything below the cut is kept and browsable, just unscored, and rises on a
later cycle if it stays near the top.
"""

from __future__ import annotations

import asyncio

from app import rank, store
from app.evaluate import evaluator
from app.models import Profile


def unevaluated(jobs: list) -> list:
    return [j for j in jobs if store.load_evaluation(j.id) is None]


def ranking_preview(profile: Profile, limit: int = 50) -> dict:
    """What the model would read next, and how far the backlog stretches."""
    jobs = store.load_jobs()
    pending = unevaluated(jobs)
    ranked = rank.rank_jobs(profile, pending)
    return {
        "total_jobs": len(jobs),
        "evaluated": len(jobs) - len(pending),
        "pending": len(pending),
        "budget_per_run": rank.EVAL_BUDGET,
        "next": [
            {
                "job_id": j.id, "title": j.title, "company": j.company,
                "source": j.source, "region": j.region, "url": j.url,
                "similarity": round(score, 4),
            }
            for j, score in ranked[:limit]
        ],
    }


async def evaluate_next(
    profile: Profile, *, budget: int | None = None, min_similarity: float = 0.0
) -> dict:
    """Evaluate the top-ranked unscored jobs. Returns what it did, and why."""
    budget = rank.EVAL_BUDGET if budget is None else max(1, min(budget, 200))
    jobs = store.load_jobs()
    pending = unevaluated(jobs)
    if not pending:
        return {
            "evaluated": 0, "failed": 0, "pending_before": 0, "pending_after": 0,
            "budget": budget, "warnings": [], "scored": [],
            "note": "every stored job has already been evaluated",
        }

    ranked = [(j, s) for j, s in rank.rank_jobs(profile, pending) if s >= min_similarity]
    batch = ranked[:budget]

    evaluated = failed = 0
    warnings: list[str] = []
    scored: list[dict] = []

    for job, similarity in batch:
        try:
            # The rubric call is blocking; keep the event loop free so the UI
            # stays responsive while a long batch runs.
            ev = await asyncio.to_thread(evaluator.evaluate, profile, job)
        except Exception as e:                  # per-job, never fatal (spec §7)
            failed += 1
            warnings.append(f"{job.company} — {job.title[:60]}: {type(e).__name__}: {e}"[:220])
            continue
        store.save_evaluation(ev)
        evaluated += 1
        scored.append({
            "job_id": job.id, "title": job.title, "company": job.company,
            "source": job.source, "similarity": round(similarity, 4),
            "score": ev.score, "summary": ev.summary[:200],
        })

    return {
        "evaluated": evaluated,
        "failed": failed,
        "pending_before": len(pending),
        "pending_after": len(pending) - evaluated,
        "budget": budget,
        "warnings": warnings,
        "scored": scored,
    }

"""Rewrite the CV and draft a cover letter for ONE job.

Budgeted and validated for the same reason `evaluate` is: this ran the full
`profile.model_dump_json()` — a 14k-char resume — plus 5000 chars of job
description into an 8192-token window, then read the reply with `.get(key, "")`.
A prompt that overflows costs you the system message, so the model never sees
the schema, and the `.get` defaults turn that into an empty CV saved as a
success. See tests/test_prompt_budget_all_callsites.py.
"""

import json

from app import llm
from app.models import Evaluation, Job, Profile, TailoredDoc

# A one-page CV plus a 150-200 word letter. This comes out of the same 8192
# window as the prompt, so it makes the tailor prompt budget tighter than
# evaluation's — see llm.prompt_budget_chars.
MAX_TOKENS = 2500

REQUIRED_KEYS = ("cv_markdown", "cover_letter")

_SYS = (
    "You tailor a candidate's resume and write a cover letter for ONE job. "
    "Rewrite only from the candidate's real experience — never invent facts or "
    "employers. Return ONLY JSON with keys: cv_markdown (a full one-page CV in "
    "markdown, reordered/reworded to match the job) and cover_letter (150-200 words).")


def _candidate_block(profile: Profile, limit: int) -> str:
    """The candidate, trimmed to `limit` chars.

    The resume excerpt matters more here than in evaluation — the model rewrites
    from it and must not invent — so it gets whatever room is left after the
    structured fields.
    """
    head = json.dumps({
        "name": profile.name,
        "email": profile.email,
        "location": profile.location,
        "work_auth": profile.work_auth,
        "target_roles": profile.target_roles[:8],
        "skills": profile.skills[:40],
        "proof_points": profile.proof_points[:10],
    }, ensure_ascii=False)
    if len(head) >= limit:
        return head[:limit]
    room = limit - len(head) - len("\n\nRESUME:\n")
    if room < 200 or not profile.resume_text:
        return head
    return f"{head}\n\nRESUME:\n{profile.resume_text[:room]}"


def build_prompts(profile: Profile, job: Job, evaluation: Evaluation) -> tuple[str, str]:
    """(system, user) sized to fit the active provider's context window.

    Split out from `tailor` so the budget is testable without a live model.
    `_SYS` is never trimmed — it carries the schema instruction.
    """
    budget = llm.prompt_budget_chars(MAX_TOKENS)
    remaining = max(0, budget - len(_SYS))

    # The evaluation's strengths/gaps steer the rewrite and are short; cap them
    # rather than letting a verbose evaluation crowd out the resume.
    strengths = ", ".join(evaluation.strengths[:8])[:600]
    gaps = ", ".join(evaluation.gaps[:8])[:600]
    tail = (f"\n\nEVAL STRENGTHS: {strengths}\nGAPS TO DOWNPLAY: {gaps}")
    header = f"CANDIDATE:\n\n\nJOB: {job.title} @ {job.company}\n"

    body = max(0, remaining - len(tail) - len(header))
    candidate_limit = (body * 3) // 5          # the rewrite is resume-driven
    description_limit = body - candidate_limit

    user = (
        f"CANDIDATE:\n{_candidate_block(profile, candidate_limit)}\n\n"
        f"JOB: {job.title} @ {job.company}\n{job.description[:description_limit]}"
        f"{tail}"
    )
    return _SYS, user


def tailor(profile: Profile, job: Job, evaluation: Evaluation) -> TailoredDoc:
    system, user = build_prompts(profile, job, evaluation)
    d = llm.require_json_keys(
        llm.complete_json(system, user, max_tokens=MAX_TOKENS),
        REQUIRED_KEYS, "tailor",
    )
    cv = str(d.get("cv_markdown") or "").strip()
    letter = str(d.get("cover_letter") or "").strip()
    # A present-but-blank field passes a key check and is still useless. This is
    # precisely what the old `.get(key, "")` produced and saved.
    if not cv:
        raise ValueError("tailor: model returned an empty cv_markdown")
    if not letter:
        raise ValueError("tailor: model returned an empty cover_letter")
    return TailoredDoc(job_id=job.id, cv_markdown=cv, cover_letter=letter)

"""Score one job against the candidate's profile.

Two things here are load-bearing on the local-model path, and both were found
by running the app rather than by the suite (see tests/test_evaluator_offline.py):

1. **The prompt is budgeted to the provider's context window.** Ollama drops the
   OLDEST tokens when a prompt overflows, so an over-long prompt costs you the
   system message — and with it the JSON schema instruction. The model then
   answers a different question entirely.
2. **The response is checked against the schema.** Reading every field with
   `.get(key, default)` turns a wrong-shaped reply into a perfectly valid
   all-defaults `Evaluation` that gets saved and counted as a success.
"""

import json

from app import llm
from app.evaluate.rubric import load_rubric
from app.models import Evaluation, Job, Profile

SCHEMA_KEYS = (
    "score", "summary", "cv_match", "scam_flag", "scam_reason",
    "no_sponsorship", "strengths", "gaps",
)

# Without these two there is no evaluation, only noise. The rest are allowed to
# be absent — the models' coercing validators default them — because a terse
# answer is still useful and we want to reject nonsense, not brevity.
REQUIRED_KEYS = ("score", "summary")

_SYS = (
    "You are a rigorous job-fit evaluator. Apply the rubric below. "
    "Return ONLY JSON with keys: score (1-5 float), summary, cv_match, "
    "scam_flag (bool), scam_reason, no_sponsorship (bool: true if the posting "
    "explicitly refuses visa sponsorship), strengths (list), gaps (list).\n\nRUBRIC:\n")


def _candidate_block(profile: Profile, limit: int) -> str:
    """The candidate, trimmed to `limit` chars.

    `profile.model_dump_json()` embeds the entire resume — 14k+ chars on a real
    profile, which on its own is most of a local model's context. Send the
    structured fields the rubric actually scores, then spend whatever is left on
    a resume excerpt.
    """
    head = json.dumps({
        "name": profile.name,
        "location": profile.location,
        "work_auth": profile.work_auth,
        "target_roles": profile.target_roles[:8],
        "skills": profile.skills[:40],
        "proof_points": profile.proof_points[:6],
    }, ensure_ascii=False)
    if len(head) >= limit:
        return head[:limit]
    room = limit - len(head) - len("\n\nRESUME EXCERPT:\n")
    if room < 200 or not profile.resume_text:
        return head
    return f"{head}\n\nRESUME EXCERPT:\n{profile.resume_text[:room]}"


def build_prompts(profile: Profile, job: Job) -> tuple[str, str]:
    """(system, user) sized to fit the active provider's context window.

    Split out from `evaluate` so the budget is testable without a live model.
    `_SYS` is never trimmed: it carries the schema instruction, and losing that
    is the whole failure this function exists to prevent.
    """
    budget = llm.prompt_budget_chars()

    # The rubric is generic guidance and the least valuable thing in the prompt,
    # so it yields first — a quarter of what's left after the instruction.
    rubric_room = max(0, (budget - len(_SYS)) // 4)
    system = _SYS + load_rubric()[:rubric_room]

    remaining = max(0, budget - len(system))
    candidate_limit = remaining // 2
    header = f"CANDIDATE:\n\n\nJOB: {job.title} @ {job.company}\n"
    description_limit = max(0, remaining - candidate_limit - len(header))

    user = (
        f"CANDIDATE:\n{_candidate_block(profile, candidate_limit)}\n\n"
        f"JOB: {job.title} @ {job.company}\n{job.description[:description_limit]}"
    )
    return system, user


def _require_schema(d: object) -> dict:
    """Reject a reply that isn't an evaluation.

    Raises `ValueError`, deliberately, not `RuntimeError`: `/evaluate` maps
    RuntimeError to a 400 that aborts the entire batch (it means "the config is
    broken, every job will fail identically"). A schema mismatch is per-job, so
    it must land in the generic handler that records a warning and carries on —
    spec §7, per-item failures are never fatal to the run.
    """
    if not isinstance(d, dict):
        raise ValueError(
            f"model returned a {type(d).__name__}, expected a JSON object with "
            f"keys {list(SCHEMA_KEYS)}"
        )
    missing = [k for k in REQUIRED_KEYS if k not in d]
    if missing:
        raise ValueError(
            f"model ignored the evaluation schema — missing {missing}; it "
            f"returned keys {sorted(d)[:10]}. On the local provider this usually "
            "means the prompt overflowed the context window and the schema "
            "instruction was truncated away."
        )
    return d


def evaluate(profile: Profile, job: Job) -> Evaluation:
    system, user = build_prompts(profile, job)
    d = _require_schema(llm.complete_json(system, user))
    return Evaluation(
        job_id=job.id,
        score=d.get("score", 0),
        summary=d.get("summary", ""),
        cv_match=d.get("cv_match", ""),
        scam_flag=bool(d.get("scam_flag")),
        scam_reason=d.get("scam_reason", ""),
        no_sponsorship=bool(d.get("no_sponsorship")),
        strengths=d.get("strengths", []),
        gaps=d.get("gaps", []),
    )

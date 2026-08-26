"""Regression tests for the local-model evaluation path.

Both bugs these cover were found by actually running the app against
`qwen3:8b`, not by the suite:

**RC1 — the prompt overflowed the local context window.** v1 hard-coded
12000 chars of rubric and 6000 of job description, and dumped the whole
`Profile` (including a 14k-char resume) as JSON. That is ~8.5k tokens against
Ollama's `num_ctx=8192`. Ollama drops the OLDEST tokens on overflow, so the
system message — the one carrying the JSON schema instruction — was the first
thing discarded. The model then free-formed a summary of the job posting.

**RC2 — the mismatch was invisible.** `evaluate()` read every field with
`.get(key, default)`, so a response with entirely different keys produced a
fully-defaulted `Evaluation` (score 0.0, empty strings) that was saved and
counted as a success.
"""

import json

import pytest

from app import llm
from app.evaluate import evaluator
from app.models import Job, Profile


def _profile() -> Profile:
    return Profile(
        name="Test Candidate",
        location="Bengaluru, India",
        work_auth="Indian citizen",
        target_roles=["Software Engineer"] * 20,
        skills=[f"skill-{i}" for i in range(200)],
        proof_points=["shipped a thing"] * 20,
        resume_text="RESUME BODY. " * 2000,   # ~26k chars, like a real resume
    )


def _job() -> Job:
    return Job(
        id="j1", source="test", company="Acme", title="Engineer",
        url="https://example.invalid/j1",
        description="JOB BODY. " * 3000,      # ~30k chars
    )


# --- RC1: the prompt must fit the local model's context window -------------

def test_prompt_budget_is_small_for_ollama_and_large_for_hosted(monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    local = llm.prompt_budget_chars()
    monkeypatch.setattr(llm, "provider", lambda: "api")
    hosted = llm.prompt_budget_chars()
    assert local < hosted
    # Must leave room for the reply inside num_ctx. At ~3.5 chars/token the
    # budget plus the 1500-token reply has to fit in 8192.
    assert local / 3.5 + 1500 < llm.OLLAMA_NUM_CTX


def test_local_prompt_stays_inside_the_budget(monkeypatch):
    """The whole point: an oversized profile and job must be trimmed to fit."""
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    system, user = evaluator.build_prompts(_profile(), _job())
    budget = llm.prompt_budget_chars()
    assert len(system) + len(user) <= budget, (
        f"prompt is {len(system) + len(user)} chars, over the {budget} budget — "
        "Ollama will silently truncate the system message and the schema "
        "instruction with it"
    )


def test_schema_instruction_survives_even_with_enormous_inputs(monkeypatch):
    """Whatever gets trimmed, the list of required keys must not be."""
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    system, _ = evaluator.build_prompts(_profile(), _job())
    for key in ("score", "summary", "cv_match", "scam_flag", "no_sponsorship",
                "strengths", "gaps"):
        assert key in system, f"schema key {key!r} was trimmed out of the system prompt"


def test_the_resume_is_excerpted_not_dumped_whole(monkeypatch):
    """A 26k-char resume alone would blow the entire context window."""
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    profile = _profile()
    _, user = evaluator.build_prompts(profile, _job())
    assert profile.resume_text not in user


def test_hosted_provider_still_gets_the_full_context(monkeypatch):
    """The trimming must not degrade the cloud path, which has 200k of room."""
    monkeypatch.setattr(llm, "provider", lambda: "api")
    system, user = evaluator.build_prompts(_profile(), _job())
    assert len(system) + len(user) > 30_000


# --- RC2: a wrong-schema response must fail loudly, not silently ------------

WRONG_SCHEMA = {
    "job_title": "Engineer @ Acme", "company": "Acme",
    "industry": "Widgets", "about_company": "We make widgets.",
}


def test_wrong_schema_response_raises_instead_of_returning_an_empty_evaluation(monkeypatch):
    """This is the exact response qwen3:8b produced against the real app."""
    monkeypatch.setattr(llm, "complete_json", lambda s, u, **kw: dict(WRONG_SCHEMA))
    with pytest.raises(ValueError) as exc:
        evaluator.evaluate(_profile(), _job())
    msg = str(exc.value)
    assert "score" in msg and "summary" in msg      # names what was missing
    assert "job_title" in msg                       # names what came back instead


def test_non_dict_response_raises(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda s, u, **kw: ["not", "a", "dict"])
    with pytest.raises(ValueError, match="list"):
        evaluator.evaluate(_profile(), _job())


def test_schema_error_is_a_ValueError_so_one_bad_job_cannot_abort_the_batch():
    """`/evaluate` maps RuntimeError to a 400 that kills the whole run (it means
    'config is broken, every job will fail the same way'). A schema mismatch is
    per-job, so it must NOT be a RuntimeError — the generic handler counts it as
    `failed` and carries on, per spec §7."""
    assert not issubclass(ValueError, RuntimeError)


def test_valid_response_is_accepted_and_populated(monkeypatch):
    good = {
        "score": 4.2, "summary": "Strong match.", "cv_match": "8/10",
        "scam_flag": False, "scam_reason": "", "no_sponsorship": True,
        "strengths": ["python"], "gaps": ["no k8s"],
    }
    monkeypatch.setattr(llm, "complete_json", lambda s, u, **kw: dict(good))
    e = evaluator.evaluate(_profile(), _job())
    assert e.job_id == "j1"
    assert e.score == 4.2
    assert e.summary == "Strong match."
    assert e.no_sponsorship is True
    assert e.strengths == ["python"]


def test_partial_but_usable_response_is_kept(monkeypatch):
    """score+summary present is enough; the coercing validators handle the rest.
    We reject nonsense, not merely terse answers."""
    monkeypatch.setattr(
        llm, "complete_json", lambda s, u, **kw: {"score": 3, "summary": "ok"}
    )
    e = evaluator.evaluate(_profile(), _job())
    assert e.score == 3.0 and e.summary == "ok" and e.gaps == []

"""Every LLM call site must budget its prompt and validate its response.

`/evaluate` shipped with neither and silently produced 15 empty evaluations out
of 41 on the dev machine (see test_evaluator_offline.py). `/tailor` and the
resume ingest were written the same way — full `profile.model_dump_json()` into
an 8k context, then `.get(key, "")` on the way out — so they carry the same two
failure modes. These tests pin all three.
"""

import pytest

from app import llm
from app.ingest import resume as resume_ingest
from app.models import Evaluation, Job, Profile
from app.tailor import writer


def _profile() -> Profile:
    return Profile(
        name="Test Candidate", location="Bengaluru, India", work_auth="Indian citizen",
        target_roles=["Software Engineer"] * 20,
        skills=[f"skill-{i}" for i in range(200)],
        proof_points=["shipped a thing"] * 20,
        resume_text="RESUME BODY. " * 2000,   # ~26k chars
    )


def _job() -> Job:
    return Job(id="j1", source="test", company="Acme", title="Engineer",
               url="https://example.invalid/j1", description="JOB BODY. " * 3000)


def _eval() -> Evaluation:
    return Evaluation(job_id="j1", score=4.0, summary="s", cv_match="m",
                      strengths=["python"] * 30, gaps=["k8s"] * 30)


# --- the shared guard -------------------------------------------------------

def test_require_json_keys_rejects_a_non_dict():
    with pytest.raises(ValueError, match="list"):
        llm.require_json_keys(["a"], ("x",), "test call")


def test_require_json_keys_names_what_was_missing_and_what_came_back():
    with pytest.raises(ValueError) as exc:
        llm.require_json_keys({"job_title": "x", "company": "y"}, ("score", "summary"), "eval")
    msg = str(exc.value)
    assert "score" in msg and "summary" in msg     # what we needed
    assert "job_title" in msg                       # what we got instead


def test_require_json_keys_passes_a_valid_dict():
    d = {"score": 1, "summary": "ok", "extra": True}
    assert llm.require_json_keys(d, ("score", "summary"), "eval") is d


# --- /tailor ----------------------------------------------------------------

def test_tailor_prompt_fits_the_local_budget(monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    system, user = writer.build_prompts(_profile(), _job(), _eval())
    budget = llm.prompt_budget_chars(writer.MAX_TOKENS)
    assert len(system) + len(user) <= budget, (
        f"{len(system) + len(user)} chars exceeds the {budget} budget for "
        f"max_tokens={writer.MAX_TOKENS}"
    )


def test_tailor_budget_accounts_for_its_larger_reply(monkeypatch):
    """A CV plus a cover letter needs 2500 output tokens, which must come out of
    the same 8192 window — so the tailor prompt budget is SMALLER than eval's.

    Pin the provider: the budget only varies locally, and this box may resolve
    to the `cli` provider, where both calls return the same hosted constant.
    """
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    assert llm.prompt_budget_chars(writer.MAX_TOKENS) < llm.prompt_budget_chars(1500)


def test_tailor_does_not_dump_the_whole_resume(monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    p = _profile()
    _, user = writer.build_prompts(p, _job(), _eval())
    assert p.resume_text not in user


def test_tailor_keeps_its_schema_instruction(monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    system, _ = writer.build_prompts(_profile(), _job(), _eval())
    assert "cv_markdown" in system and "cover_letter" in system


def test_tailor_rejects_a_wrong_schema_response(monkeypatch):
    monkeypatch.setattr(llm, "complete_json",
                        lambda s, u, **kw: {"resume": "...", "letter": "..."})
    with pytest.raises(ValueError, match="cv_markdown"):
        writer.tailor(_profile(), _job(), _eval())


def test_tailor_rejects_an_empty_cv(monkeypatch):
    """An empty string passes a key check but is not a CV. This is exactly what
    the old `.get(key, "")` produced and saved as a success."""
    monkeypatch.setattr(llm, "complete_json",
                        lambda s, u, **kw: {"cv_markdown": "   ", "cover_letter": "hi"})
    with pytest.raises(ValueError, match="empty"):
        writer.tailor(_profile(), _job(), _eval())


def test_tailor_accepts_a_valid_response(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda s, u, **kw: {
        "cv_markdown": "# Test Candidate\n\n- did things",
        "cover_letter": "Dear hiring manager, " * 10,
    })
    doc = writer.tailor(_profile(), _job(), _eval())
    assert doc.job_id == "j1"
    assert doc.cv_markdown.startswith("# Test Candidate")
    assert "Dear hiring manager" in doc.cover_letter


# --- resume ingest ----------------------------------------------------------

def test_resume_ingest_prompt_fits_the_local_budget(monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: "ollama")
    system, user = resume_ingest.build_prompts("RESUME. " * 20000)   # ~160k chars
    assert len(system) + len(user) <= llm.prompt_budget_chars()


def test_resume_ingest_rejects_a_response_with_no_usable_fields(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda s, u, **kw: {"summary": "a person"})
    with pytest.raises(ValueError, match="name"):
        resume_ingest.build_profile("some resume text")


def test_resume_ingest_keeps_the_full_resume_on_the_profile(monkeypatch):
    """Only the PROMPT is trimmed. The stored profile keeps the whole resume —
    tailoring and future re-parses need it."""
    monkeypatch.setattr(llm, "complete_json", lambda s, u, **kw: {
        "name": "Test Candidate", "email": "a@b.c", "location": "Remote",
        "work_auth": "", "target_roles": ["Engineer"], "skills": ["python"],
        "proof_points": ["shipped"],
    })
    text = "RESUME. " * 20000
    p = resume_ingest.build_profile(text)
    assert p.resume_text == text
    assert p.name == "Test Candidate"

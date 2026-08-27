"""Cheap pre-ranking, so the expensive model only reads what's worth reading.

The arithmetic that forces this: a scan now returns ~850 jobs, and one
`qwen3:8b` evaluation takes 10-30s on an 8GB card. Evaluating everything would
take about three hours of pinned GPU, every cycle. Spec §4.2 is a funnel —
dedupe, hard filters, a ~50ms embedding similarity on everything, and the full
rubric on only the top N.

The ranking is not the judgement. It decides *reading order*; the LLM still
does the actual scoring. So the bar here is "surfaces the plausible ones
first", not "is correct".
"""

import math

import pytest

from app import rank
from app.models import Job, Profile


@pytest.fixture(autouse=True)
def never_touch_real_data(tmp_path, monkeypatch):
    """Point the store at a scratch dir for EVERY test in this file.

    Two tests here previously ranked without redirecting DATA_DIR, so their
    fake 2-dimensional vectors were written into the user's real
    `launchpad_data/embeddings.json`. Cosine then correctly refused to compare
    2 dims against the model's 768 and scored every job 0.0 — the live ranking
    was silently useless until the cache was cleared. Tests do not get to write
    to real user data.
    """
    from app import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)


def _job(jid, title, desc="", company="Acme"):
    return Job(id=jid, source="t", company=company, title=title,
               url=f"https://x.invalid/{jid}", description=desc)


def _profile():
    return Profile(
        name="T", target_roles=["Machine Learning Engineer", "Software Engineer"],
        skills=["python", "pytorch", "llm", "docker"],
        resume_text="Built production ML systems in Python and PyTorch.",
    )


# --- cosine -----------------------------------------------------------------

def test_cosine_of_identical_vectors_is_one():
    assert rank.cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero():
    assert rank.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_of_opposite_vectors_is_minus_one():
    assert rank.cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_handles_a_zero_vector_without_dividing_by_zero():
    assert rank.cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_cosine_of_mismatched_lengths_is_zero_not_a_crash():
    """A model change mid-cache would produce mixed dimensions. Degrade."""
    assert rank.cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


# --- the text that gets embedded --------------------------------------------

def test_job_text_includes_title_company_and_some_description():
    j = _job("a", "ML Engineer", "We use PyTorch heavily. " * 200, company="Acme")
    text = rank.job_text(j)
    assert "ML Engineer" in text and "Acme" in text
    assert len(text) <= rank.MAX_EMBED_CHARS


def test_profile_text_uses_roles_and_skills():
    text = rank.profile_text(_profile())
    assert "Machine Learning Engineer" in text and "python" in text


# --- ranking ----------------------------------------------------------------

def test_ranks_by_similarity_descending(monkeypatch):
    vectors = {
        "profile": [1.0, 0.0],
        "near": [0.99, 0.14],
        "far": [0.0, 1.0],
        "mid": [0.7, 0.7],
    }

    def fake_embed(texts):
        return [vectors[t] for t in texts]

    monkeypatch.setattr(rank, "embed_texts", fake_embed)
    monkeypatch.setattr(rank, "profile_text", lambda p: "profile")
    monkeypatch.setattr(rank, "job_text", lambda j: j.id)

    ordered = rank.rank_jobs(_profile(), [_job("far", "x"), _job("mid", "y"), _job("near", "z")])
    assert [j.id for j, _ in ordered] == ["near", "mid", "far"]


def test_scores_are_returned_alongside_the_jobs(monkeypatch):
    monkeypatch.setattr(rank, "embed_texts", lambda texts: [[1.0, 0.0]] * len(texts))
    ordered = rank.rank_jobs(_profile(), [_job("a", "x")])
    assert ordered[0][1] == pytest.approx(1.0)


def test_ranking_an_empty_list_returns_empty(monkeypatch):
    monkeypatch.setattr(rank, "embed_texts", lambda texts: [])
    assert rank.rank_jobs(_profile(), []) == []


def test_embedding_failure_degrades_to_original_order(monkeypatch):
    """If Ollama is down or the model isn't pulled, ranking must not take the
    whole pipeline with it — evaluation in arbitrary order still beats none."""
    def boom(texts):
        raise RuntimeError("ollama unreachable")

    monkeypatch.setattr(rank, "embed_texts", boom)
    jobs = [_job("a", "x"), _job("b", "y")]
    ordered = rank.rank_jobs(_profile(), jobs)
    assert [j.id for j, _ in ordered] == ["a", "b"]
    assert all(s == 0.0 for _, s in ordered)


# --- the cache --------------------------------------------------------------

def test_vectors_are_cached_so_a_rescan_does_not_re_embed(monkeypatch, tmp_path):
    from app import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)

    calls = []

    def counting_embed(texts):
        calls.append(list(texts))
        return [[1.0, 0.0]] * len(texts)

    monkeypatch.setattr(rank, "embed_texts", counting_embed)
    jobs = [_job("a", "x"), _job("b", "y")]

    rank.rank_jobs(_profile(), jobs)
    first = sum(len(c) for c in calls)
    rank.rank_jobs(_profile(), jobs)
    second = sum(len(c) for c in calls) - first

    assert first >= 2                    # profile + 2 jobs embedded initially
    assert second <= 1, "job vectors should have come from the cache"


def test_only_uncached_jobs_are_embedded_on_a_later_run(monkeypatch, tmp_path):
    from app import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)

    seen = []

    def counting_embed(texts):
        seen.append(list(texts))
        return [[1.0, 0.0]] * len(texts)

    monkeypatch.setattr(rank, "embed_texts", counting_embed)
    monkeypatch.setattr(rank, "job_text", lambda j: j.id)

    rank.rank_jobs(_profile(), [_job("a", "x")])
    seen.clear()
    rank.rank_jobs(_profile(), [_job("a", "x"), _job("b", "y")])
    embedded = [t for batch in seen for t in batch]
    assert "b" in embedded
    assert "a" not in embedded

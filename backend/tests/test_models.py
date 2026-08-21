from app.models import Job, job_id, Evaluation

def test_job_id_stable():
    a = job_id("greenhouse", "stripe", "https://x/y")
    b = job_id("greenhouse", "stripe", "https://x/y")
    assert a == b and len(a) == 16

def test_evaluation_defaults():
    e = Evaluation(job_id="j1", score=4.2, summary="s", cv_match="m")
    assert e.scam_flag is False and e.no_sponsorship is False


def test_evaluation_coerces_loose_local_model_output():
    """qwen3:8b returned `cv_match: 2.5` (a number) and 500'd the evaluation.
    Small local models are loose about types; normalize rather than discard an
    otherwise-good result."""
    e = Evaluation(job_id="j1", score="4.2", summary=["a", "b"], cv_match=2.5,
                   strengths="only one", gaps=None)
    assert e.score == 4.2
    assert e.cv_match == "2.5"
    assert e.summary == "a b"
    assert e.strengths == ["only one"]
    assert e.gaps == []


def test_evaluation_unparseable_score_defaults_to_zero():
    assert Evaluation(job_id="j", score="not a number", summary="s", cv_match="m").score == 0.0


def test_profile_coerces_loose_output():
    from app.models import Profile
    p = Profile(name=123, skills="python", target_roles={"a": "b"}, proof_points=None)
    assert p.name == "123"
    assert p.skills == ["python"]
    assert p.target_roles == ["a: b"]
    assert p.proof_points == []

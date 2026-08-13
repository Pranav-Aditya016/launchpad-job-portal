import app.evaluate.evaluator as ev
from app.models import Profile, Job


def test_evaluate_maps_flags(monkeypatch):
    monkeypatch.setattr(ev, "load_rubric", lambda: "RUBRIC")
    monkeypatch.setattr(ev.llm, "complete_json", lambda s, u, **k: {
        "score": 4.3, "summary": "Strong fit", "cv_match": "matches ML",
        "scam_flag": False, "scam_reason": "", "no_sponsorship": True,
        "strengths": ["pytorch"], "gaps": ["k8s"]})
    e = ev.evaluate(Profile(name="A", skills=["pytorch"]),
                    Job(id="j1", source="gh", company="x", title="ML Eng", url="u",
                        description="No visa sponsorship."))
    assert e.score == 4.3 and e.no_sponsorship is True and e.job_id == "j1"

import app.tailor.writer as w
from app.models import Profile, Job, Evaluation

def test_tailor_returns_doc(monkeypatch):
    monkeypatch.setattr(w.llm, "complete_json", lambda s,u,**k: {
        "cv_markdown": "# Ann Lee\n- pytorch", "cover_letter": "Dear team,"})
    d = w.tailor(Profile(name="Ann Lee"),
                 Job(id="j1", source="gh", company="Acme", title="ML", url="u"),
                 Evaluation(job_id="j1", score=4.5, summary="", cv_match=""))
    assert d.job_id == "j1" and "pytorch" in d.cv_markdown and d.cover_letter

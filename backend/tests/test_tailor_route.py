# /tailor/{job_id} must degrade gracefully when the PDF renderer is
# unavailable (e.g. WeasyPrint's native GTK libs missing on this Windows
# box) instead of 500ing outright — the LLM tailoring itself doesn't need
# a PDF renderer, so it should always run, and the route should always
# return the real tailored CV markdown regardless of PDF availability.
from fastapi.testclient import TestClient

import app.api as api
from app.models import Evaluation, Job, Profile, TailoredDoc

_PROFILE = Profile(name="Ann Lee")
_JOB = Job(id="j1", source="gh", company="Acme", title="ML", url="https://acme/apply")
_EVAL = Evaluation(job_id="j1", score=4.5, summary="Good fit", cv_match="Strong")
_DOC = TailoredDoc(job_id="j1", cv_markdown="# CV", cover_letter="Dear team")


def _common(monkeypatch):
    monkeypatch.setattr(api.store, "load_profile", lambda: _PROFILE)
    monkeypatch.setattr(api.store, "load_jobs", lambda: [_JOB])
    monkeypatch.setattr(api.store, "load_evaluation", lambda job_id: _EVAL)
    monkeypatch.setattr(api.writer, "tailor", lambda profile, job, evaluation: _DOC)


def test_tailor_returns_markdown_when_pdf_unavailable(monkeypatch):
    _common(monkeypatch)
    monkeypatch.setattr(api, "pdf", None)

    c = TestClient(api.app)
    r = c.post("/tailor/j1")

    assert r.status_code == 200
    body = r.json()
    assert body["cv_markdown"] == "# CV"
    assert body["cover_letter"] == "Dear team"
    assert body["pdf_url"] is None
    assert body["pdf_available"] is False


def test_tailor_returns_pdf_url_when_renderer_works(monkeypatch):
    _common(monkeypatch)

    class _FakePdf:
        def render_cv_pdf(self, doc, path):
            return path

    monkeypatch.setattr(api, "pdf", _FakePdf())

    c = TestClient(api.app)
    r = c.post("/tailor/j1")

    assert r.status_code == 200
    body = r.json()
    assert body["pdf_available"] is True
    assert body["pdf_url"] == "/output/j1.pdf"
    assert body["cv_markdown"] == "# CV"

from pathlib import Path
import app.ingest.resume as r

def test_extract_text_txt():
    p = Path(__file__).parent / "fixtures" / "sample_resume.txt"
    assert "Python" in r.extract_text(p)

def test_build_profile_maps_fields(monkeypatch):
    monkeypatch.setattr(r.llm, "complete_json", lambda s, u, **k: {
        "name": "Ann Lee", "email": "a@x.com", "location": "Remote",
        "work_auth": "US citizen", "target_roles": ["ML Engineer"],
        "skills": ["python", "pytorch"], "proof_points": ["Shipped X"]})
    prof = r.build_profile("resume text with Python")
    assert prof.name == "Ann Lee" and "pytorch" in prof.skills
    assert prof.resume_text.startswith("resume text")

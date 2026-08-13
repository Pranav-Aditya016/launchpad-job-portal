import app.store as store
from app.models import Profile, Job, Evaluation, job_id

def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    store.save_profile(Profile(name="Ann", skills=["python"]))
    assert store.load_profile().name == "Ann"

def test_jobs_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    j = Job(id=job_id("gh","x","u"), source="gh", company="x", title="t", url="u")
    assert store.upsert_jobs([j, j]) == 1
    assert store.upsert_jobs([j]) == 0
    assert len(store.load_jobs()) == 1

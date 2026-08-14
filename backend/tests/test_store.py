import json
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


def test_empty_profile_file_is_treated_as_absent_not_a_crash(tmp_path, monkeypatch):
    """A 0-byte profile.json used to raise ValidationError on EVERY request.

    That escaped as an unhandled 500 (no CORS headers), so the UI reported
    "Can't reach the backend" — a truncated write masquerading as an outage.
    """
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    (tmp_path / "profile.json").write_text("")
    assert store.load_profile() is None


def test_corrupt_files_degrade_instead_of_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    (tmp_path / "profile.json").write_text("{not json")
    (tmp_path / "jobs.json").write_text("]]]")
    (tmp_path / "applied_log.json").write_text("garbage")
    assert store.load_profile() is None
    assert store.load_jobs() == []
    assert store.applied_ids() == set()


def test_writes_are_atomic_no_partial_file_left_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    store.save_profile(Profile(name="Atomic", resume_text="x"))
    assert store.load_profile().name == "Atomic"
    # no leftover temp files from the write
    assert [f.name for f in tmp_path.iterdir() if f.name.endswith(".tmp")] == []


def test_legacy_cp1252_file_still_loads(tmp_path, monkeypatch):
    """Files written before this module pinned UTF-8 were saved as cp1252 on
    Windows. A UTF-8-only read raised UnicodeDecodeError on an em-dash in a job
    description and 500'd /jobs. They must still load."""
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    job = {"id": "j1", "source": "gh", "company": "c",
           "title": "Engineer — Remote", "location": "", "url": "https://x",
           "description": "pay — good", "posted": None}
    # cp1252 encodes U+2014 as the single byte 0x97, which is invalid UTF-8.
    (tmp_path / "jobs.json").write_bytes(json.dumps([job]).encode("cp1252"))
    jobs = store.load_jobs()
    assert len(jobs) == 1
    assert "—" in jobs[0].title

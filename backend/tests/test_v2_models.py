import pytest
from pydantic import ValidationError

from app.models import Connection, Job, Profile, QueueItem, ScanRun


def test_connection_defaults_to_disconnected():
    c = Connection(portal="naukri")
    assert c.status == "disconnected"
    assert c.last_verified is None
    assert c.note == ""


def test_connection_rejects_unknown_status():
    with pytest.raises(ValidationError):
        Connection(portal="naukri", status="totally-made-up")


def test_connection_has_no_credential_fields():
    """Boundary: this model must never grow a place to put a password."""
    forbidden = {"password", "passwd", "secret", "otp", "token", "username", "user"}
    assert not (forbidden & set(Connection.model_fields))


def test_scan_run_tracks_per_source_counts_and_warnings():
    r = ScanRun(
        id="r1", started="2026-08-26T10:00:00", trigger="scheduled",
        per_source={"naukri": 12, "ats:greenhouse": 40}, warnings=["linkedin: blocked"],
    )
    assert r.finished is None
    assert r.per_source["naukri"] == 12
    assert r.evaluated == 0 and r.tailored == 0


def test_queue_item_starts_ready():
    q = QueueItem(job_id="abc123", state="ready", score=88.0)
    assert q.prepared_at is None and q.submitted_at is None and q.cv_pdf is None


def test_job_gains_v2_fields_with_back_compatible_defaults():
    j = Job(id="i", source="s", company="c", title="t", url="u")
    assert j.region == "" and j.first_seen is None


def test_v1_data_still_loads():
    """A Job dict written by v1 (no region/first_seen) must still validate."""
    v1 = {"id": "i", "source": "remotive", "company": "Acme", "title": "Dev",
          "location": "Remote", "url": "https://x", "description": "d", "posted": "2026-01-01"}
    assert Job(**v1).region == ""


def test_job_region_coerces_like_other_text_fields():
    """region is a str field populated from external metadata; must coerce None and non-strings."""
    j1 = Job(id="i", source="s", company="c", title="t", url="u", region=None)
    assert j1.region == ""

    j2 = Job(id="i", source="s", company="c", title="t", url="u", region=42)
    assert j2.region == "42"

    j3 = Job(id="i", source="s", company="c", title="t", url="u", region=["in", "de"])
    assert j3.region == "in de"


def test_profile_is_unchanged():
    p = Profile(name="A", skills="python")   # v1 coercion still applies
    assert p.skills == ["python"]

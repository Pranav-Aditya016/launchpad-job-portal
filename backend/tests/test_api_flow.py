from fastapi.testclient import TestClient
import app.api as api
from app.models import Profile, Job, job_id


async def _no_aggregators(*a, **k):
    return []


def test_scan_and_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(api.store.cfg, "DATA_DIR", tmp_path)
    j = Job(id=job_id("gh", "x", "https://x/apply"), source="gh", company="x",
            title="ML", url="https://x/apply")
    monkeypatch.setattr(api.careerops_scan, "run_scan", lambda *a, **k: [j])
    monkeypatch.setattr(api.store, "load_profile", lambda: Profile(name="A"))
    # Keep this a pure unit test: don't let the real (network-calling)
    # aggregator leg added in Task 14 reach out to live job-board APIs here.
    monkeypatch.setattr(api.aggregators, "fetch_all", _no_aggregators)
    c = TestClient(api.app)
    # fresher_only=False: this test's fixture job title ("ML") isn't meant to
    # exercise the Task 14 entry-level filter, just the scan->store->apply flow.
    assert c.post("/scan", json={"fresher_only": False}).json()["added"] == 1
    r = c.post(f"/apply/{j.id}")
    assert r.json()["url"] == "https://x/apply"
    assert j.id in api.store.applied_ids()

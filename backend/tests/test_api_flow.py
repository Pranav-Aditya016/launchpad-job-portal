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


def test_scan_reports_careerops_failure_but_still_returns_other_sources(tmp_path, monkeypatch):
    # Regression test: the career-ops leg used to run with no try/except, so a
    # failure there (e.g. Node/engine missing) 500'd the whole /scan and threw
    # away jobs that other sources (aggregators) had already found. Per spec
    # §6 ("Source failures are per-source and non-fatal") this must degrade
    # gracefully: /scan should still return 200, keep the jobs that DID come
    # in, and surface the failure via `warnings` instead of swallowing it.
    monkeypatch.setattr(api.store.cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api.store, "load_profile", lambda: Profile(name="A"))

    def _boom(*a, **k):
        raise RuntimeError("node not found")

    monkeypatch.setattr(api.careerops_scan, "run_scan", _boom)

    agg_job = Job(id=job_id("remotive", "y", "https://y/apply"), source="remotive",
                  company="y", title="ML", url="https://y/apply")

    async def _one_aggregator(*a, **k):
        return [agg_job]

    monkeypatch.setattr(api.aggregators, "fetch_all", _one_aggregator)

    c = TestClient(api.app)
    res = c.post("/scan", json={"fresher_only": False})
    assert res.status_code == 200
    body = res.json()
    assert body["added"] == 1
    assert body["total"] == 1
    assert any("careerops" in w for w in body["warnings"])

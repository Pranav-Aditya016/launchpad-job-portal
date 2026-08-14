from fastapi.testclient import TestClient
import app.api as api
from app.models import Evaluation, Profile, Job, job_id


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


def test_evaluate_one_bad_job_does_not_abort_the_batch(tmp_path, monkeypatch):
    # Regression test: /evaluate used to have no per-job guard, so one LLM
    # failure (rate limit, malformed JSON, network blip) 500'd the entire
    # request and threw away every evaluation already done in that batch.
    # This must degrade gracefully — 200, per-job success/failure counts,
    # short warnings for the failures — no network/key needed since
    # api.evaluator.evaluate itself is monkeypatched.
    monkeypatch.setattr(api.store.cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api.store, "load_profile", lambda: Profile(name="A"))

    good = Job(id=job_id("gh", "good", "https://good/apply"), source="gh",
               company="good", title="ML", url="https://good/apply")
    bad = Job(id=job_id("gh", "bad", "https://bad/apply"), source="gh",
              company="bad", title="ML", url="https://bad/apply")
    monkeypatch.setattr(api.store, "load_jobs", lambda: [good, bad])
    # Neither job has a saved evaluation yet, and saving is a no-op for this
    # test — same isolation pattern as test_tailor_route.py, so we never
    # touch the real (non-tmp_path) EVAL_DIR that api.store.load_evaluation
    # reads/writes via cfg.EVAL_DIR directly.
    monkeypatch.setattr(api.store, "load_evaluation", lambda job_id: None)
    monkeypatch.setattr(api.store, "save_evaluation", lambda e: None)

    def _flaky_evaluate(profile, job):
        if job.id == bad.id:
            # A per-job failure (e.g. malformed LLM JSON, rate limit) — NOT
            # RuntimeError, which api.py treats as a systemic config error
            # (missing ANTHROPIC_API_KEY) and maps to an immediate 400
            # instead of a per-job warning.
            raise ValueError("could not parse LLM response")
        return Evaluation(job_id=job.id, score=4.0, summary="s", cv_match="m")

    monkeypatch.setattr(api.evaluator, "evaluate", _flaky_evaluate)

    c = TestClient(api.app)
    res = c.post("/evaluate", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["evaluated"] == 1
    assert body["failed"] == 1
    assert body["warnings"] and any(bad.id in w for w in body["warnings"])


def test_jobs_includes_sponsorship_ok_and_applied(monkeypatch):
    # Regression test: visa.needs_sponsorship_ok was implemented + unit
    # tested but never wired into any route (dead code) — a primary ranking
    # input the user (Indian citizen targeting DE/US/UK) never actually saw.
    # Same story for store.applied_ids(): written on /apply, never read back.
    india_job = Job(id=job_id("gh", "in-co", "https://in/apply"), source="gh",
                     company="in-co", title="ML", url="https://in/apply",
                     location="Bengaluru, India")
    us_job = Job(id=job_id("gh", "us-co", "https://us/apply"), source="gh",
                 company="us-co", title="ML", url="https://us/apply",
                 location="San Francisco, CA")
    monkeypatch.setattr(api.store, "load_jobs", lambda: [india_job, us_job])

    no_sponsorship_eval = Evaluation(job_id=us_job.id, score=3.0, summary="s",
                                      cv_match="m", no_sponsorship=True)

    def _load_evaluation(job_id):
        return no_sponsorship_eval if job_id == us_job.id else None

    monkeypatch.setattr(api.store, "load_evaluation", _load_evaluation)
    monkeypatch.setattr(api.store, "applied_ids", lambda: {india_job.id})

    c = TestClient(api.app)
    res = c.get("/jobs")
    assert res.status_code == 200
    by_id = {j["id"]: j for j in res.json()}

    assert by_id[india_job.id]["sponsorship_ok"] is True
    assert by_id[india_job.id]["applied"] is True
    assert by_id[us_job.id]["sponsorship_ok"] is False
    assert by_id[us_job.id]["applied"] is False


def test_put_profile_saves_without_llm(tmp_path, monkeypatch):
    """A profile can be created with no ANTHROPIC_API_KEY — the keyless path."""
    monkeypatch.setattr(api.store.cfg, "DATA_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = TestClient(api.app)
    body = {"name": "Test User", "location": "Bengaluru, India",
            "target_roles": ["Software Engineer"], "skills": ["python"],
            "resume_text": "some resume text"}
    r = c.put("/profile", json=body)
    assert r.status_code == 200
    assert r.json()["name"] == "Test User"
    assert api.store.load_profile().location == "Bengaluru, India"


def test_config_reports_capabilities(monkeypatch):
    """With no API key the app is still LLM-capable via the Claude Code CLI
    (subscription auth), so /config must report the provider, not just a key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHPAD_LLM", raising=False)
    monkeypatch.setattr(api.llm, "claude_cli_path", lambda: "/usr/bin/claude")
    body = TestClient(api.app).get("/config").json()
    assert body["llm_provider"] == "cli"
    assert body["llm_available"] is True
    assert set(body) == {
        "llm_available", "llm_provider", "pdf_available", "adzuna_available",
    }


def test_config_reports_llm_unavailable_with_no_key_and_no_cli(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHPAD_LLM", raising=False)
    monkeypatch.setattr(api.llm, "claude_cli_path", lambda: None)
    body = TestClient(api.app).get("/config").json()
    assert body["llm_available"] is False


def test_empty_ats_skips_the_slow_ats_sweep(tmp_path, monkeypatch):
    """`ats: []` means skip the ATS leg entirely, not 'sweep every board'."""
    monkeypatch.setattr(api.store.cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api.store, "load_profile", lambda: Profile(name="A"))

    def _boom(*a, **k):
        raise AssertionError("run_scan must not be called when ats == []")

    monkeypatch.setattr(api.careerops_scan, "run_scan", _boom)
    monkeypatch.setattr(api.aggregators, "fetch_all", _no_aggregators)
    r = TestClient(api.app).post("/scan", json={"ats": [], "fresher_only": False})
    assert r.status_code == 200
    assert r.json()["added"] == 0

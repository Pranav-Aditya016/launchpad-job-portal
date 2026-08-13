"""Opt-in integration smoke test against the REAL vendored career-ops engine.

This test is SKIPPED by default. It only runs when the environment variable
`RUN_INTEGRATION=1` is set, because it:

  - spawns a real Node.js subprocess (`node scan-ats-full.mjs`), and
  - makes real network requests to public Greenhouse ATS job-board JSON APIs
    (no API key required, zero LLM calls involved anywhere in this path).

Run it explicitly with:

    Git Bash:   RUN_INTEGRATION=1 python -m pytest tests/test_integration_scan.py -v -s
    PowerShell: $env:RUN_INTEGRATION=1; python -m pytest tests/test_integration_scan.py -v -s

`since_days` is intentionally wider than the brief's illustrative `3` days:
a real, live sweep against a 3-day window is a genuinely transient quantity
(it depends on what got posted in the last 3 days across every scanned
Greenhouse board at the moment the test happens to run) and can legitimately
return zero matches without anything being broken. Widening the window makes
this a reliable smoke test of the real end-to-end path (Python -> Node
subprocess -> live HTTP -> JSON parsing -> normalized Job objects) rather
than a flaky bet on very recent postings.
"""

import os

import pytest

from app.models import Profile
from app.sources import careerops_scan

RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="opt-in integration smoke — set RUN_INTEGRATION=1 to run (spawns Node, hits live network)",
)


@pytest.mark.integration
def test_run_scan_real_engine_returns_real_jobs():
    """Real end-to-end scan: Python -> `node scan-ats-full.mjs` -> live Greenhouse ATS APIs.

    Uses a 14-day window (instead of the illustrative 3-day one) so the
    assertion of >=1 real job is reliable rather than dependent on whether
    something happened to be posted in the last 3 days at test-run time.
    """
    profile = Profile(target_roles=["engineer"], location="Remote")

    jobs = careerops_scan.run_scan(profile, ats=["greenhouse"], since_days=14)

    assert len(jobs) >= 1, "expected the real scan to return at least one job"

    job = jobs[0]
    assert job.url.startswith("http"), f"expected a real job URL, got: {job.url!r}"
    assert job.company
    assert job.title
    assert job.id
    assert job.source

"""Opt-in integration smoke test against the REAL public aggregator APIs.

This test is SKIPPED by default. It only runs when the environment variable
`RUN_INTEGRATION=1` is set, because it makes real network requests to five
public, no-login job-board APIs (Remotive, Arbeitnow, RemoteOK, Jobicy, The
Muse; zero LLM calls involved anywhere in this path).

Run it explicitly with:

    Git Bash:   RUN_INTEGRATION=1 python -m pytest tests/test_integration_aggregators.py -v -s
    PowerShell: $env:RUN_INTEGRATION=1; python -m pytest tests/test_integration_aggregators.py -v -s

Per spec §6, provider failures are non-fatal: `aggregators.fetch_all` already
catches per-source network errors and skips them, so a provider being down on
a given day does not fail this test — we only require that AT LEAST ONE
provider responded with AT LEAST ONE real, fresher-filtered job.
"""

import os

import pytest

from app.sources import aggregators

RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="opt-in integration smoke — set RUN_INTEGRATION=1 to run (hits live network)",
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_all_returns_real_entry_level_jobs():
    """Real end-to-end fetch across all five public aggregator APIs.

    Providers that are down or blocked on the day this runs are tolerated
    (per-source non-fatal, spec §6) — we only assert that at least one
    provider returned at least one real, entry-level-filtered job.
    """
    jobs = await aggregators.fetch_all(fresher_only=True)

    assert len(jobs) >= 1, "expected at least one real entry-level job from at least one provider"

    job = jobs[0]
    assert job.url.startswith("http"), f"expected a real job URL, got: {job.url!r}"
    assert job.title
    assert job.source in aggregators.PROVIDERS

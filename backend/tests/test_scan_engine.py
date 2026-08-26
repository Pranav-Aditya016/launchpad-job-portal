"""The registry-driven scan, and the provenance it must record.

Until this existed, 27 registered sources were dormant: `/scan` ran the v1
aggregator path and never touched the registry, so the Sources page listed
things that were never actually queried. Worse, the user had no way to see
which sites a job came from or which sources silently returned nothing.

Every test here is about one of two guarantees:
  1. **Isolation** — one broken source never costs you the other 26 (spec §7).
  2. **Provenance** — every source reports what happened to it, by name, so
     the Sources page can tell the truth instead of implying coverage.
"""

import pytest

from app.models import Job, Profile, SourceResult
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceMeta, SourceUnavailable


@pytest.fixture(autouse=True)
def isolated_registry():
    # Load the real providers BEFORE snapshotting. Snapshotting an empty
    # registry and restoring it leaves the process-wide singleton empty for
    # every later test file — which is exactly how `naukri` disappeared and
    # test_session_vault started failing. See tests/test_zz_registry_intact.py.
    registry.load_providers()
    saved, was_loaded = dict(registry._REGISTRY), registry._LOADED
    registry.clear()
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)
    registry._LOADED = was_loaded


def _job(key: str, n: int) -> Job:
    return Job(id=f"{key}-{n}", source=key, company="Acme", title=f"Role {n}",
               url=f"https://example.invalid/{key}/{n}")


def _register(key, *, kind=SourceKind.PUBLIC, jobs=1, raises=None, enabled=True,
              regions=("global",)):
    @registry.register
    class _S:
        meta = SourceMeta(key=key, label=key.title(), kind=kind, regions=regions,
                          requires_login=(kind is SourceKind.PORTAL),
                          enabled_by_default=enabled, rate_limit_s=0.0)

        async def fetch(self, ctx: FetchContext) -> list[Job]:
            if raises is not None:
                raise raises
            return [_job(key, i) for i in range(jobs)]

    return _S


async def _run(**kw):
    from app.scan_engine import run_scan
    return await run_scan(Profile(name="T", target_roles=["Engineer"]), **kw)


# --- isolation --------------------------------------------------------------

async def test_one_exploding_source_does_not_stop_the_others():
    _register("good_a", jobs=2)
    _register("boom", raises=RuntimeError("upstream 500"))
    _register("good_b", jobs=3)
    run = await _run()
    by = {r.key: r for r in run.results}
    assert by["good_a"].status == "ok" and by["good_a"].jobs_found == 2
    assert by["good_b"].status == "ok" and by["good_b"].jobs_found == 3
    assert by["boom"].status == "error"
    assert "upstream 500" in by["boom"].detail


async def test_the_scan_still_returns_jobs_when_most_sources_fail():
    for i in range(5):
        _register(f"dead{i}", raises=RuntimeError("nope"))
    _register("alive", jobs=4)
    run = await _run()
    assert run.total_jobs == 4
    assert sum(1 for r in run.results if r.status == "error") == 5


async def test_a_source_returning_nothing_is_reported_as_empty_not_ok():
    """Silent zero-results is the failure mode that wasted a day on this
    project. `empty` is a distinct, visible status — never a quiet success."""
    _register("quiet", jobs=0)
    run = await _run()
    assert run.results[0].status == "empty"
    assert run.results[0].jobs_found == 0


# --- login-gated sources ----------------------------------------------------

async def test_a_portal_without_a_session_is_skipped_not_errored():
    """Not being logged in yet is a normal state, not a fault. It must read as
    'needs login' so the Connections page is the obvious next step."""
    _register("naukri_x", kind=SourceKind.PORTAL)
    run = await _run()
    r = run.results[0]
    assert r.status == "needs_login"
    assert r.jobs_found == 0
    assert "connect" in r.detail.lower()


async def test_source_unavailable_is_reported_as_needs_login():
    _register("portal_y", kind=SourceKind.PORTAL,
              raises=SourceUnavailable("portal_y: no browser session provider"))
    run = await _run(connected_portals={"portal_y"})
    assert run.results[0].status == "needs_login"


# --- selection --------------------------------------------------------------

async def test_disabled_sources_are_reported_as_disabled_and_not_run():
    _register("off_src", enabled=False)
    run = await _run()
    assert run.results[0].status == "disabled"
    assert run.results[0].jobs_found == 0


async def test_explicit_keys_limit_the_scan_and_the_rest_are_not_listed():
    _register("a"); _register("b"); _register("c")
    run = await _run(source_keys=["a", "c"])
    assert {r.key for r in run.results} == {"a", "c"}


async def test_region_filter_selects_only_matching_sources():
    _register("india", regions=("in",))
    _register("germany", regions=("de",))
    _register("everywhere", regions=("global",))
    run = await _run(regions=["in"])
    assert {r.key for r in run.results} == {"india"}


# --- provenance -------------------------------------------------------------

async def test_every_source_appears_in_the_results_even_when_it_did_nothing():
    """The whole point: the user must be able to see the full list of what was
    consulted, not just what happened to succeed."""
    _register("ok1", jobs=1)
    _register("bad", raises=RuntimeError("x"))
    _register("off", enabled=False)
    _register("port", kind=SourceKind.PORTAL)
    run = await _run()
    assert len(run.results) == 4
    assert {r.status for r in run.results} == {"ok", "error", "disabled", "needs_login"}


async def test_results_carry_the_label_kind_and_duration_for_display():
    _register("shown", jobs=1)
    r = (await _run()).results[0]
    assert r.label == "Shown" and r.kind == "public"
    assert r.duration_s >= 0


async def test_jobs_are_tagged_with_their_source_key_and_region():
    _register("tagged", jobs=1, regions=("de",))
    run = await _run()
    assert run.jobs[0].source == "tagged"
    assert run.jobs[0].region == "de"


async def test_scan_run_records_per_source_counts_for_the_history():
    _register("s1", jobs=2)
    _register("s2", jobs=0)
    run = await _run()
    assert run.per_source == {"s1": 2, "s2": 0}


async def test_warnings_from_sources_are_collected():
    @registry.register
    class _Warner:
        meta = SourceMeta(key="warner", label="Warner", kind=SourceKind.PUBLIC,
                          rate_limit_s=0.0)

        async def fetch(self, ctx: FetchContext) -> list[Job]:
            ctx.warn("warner: selector matched 0 elements")
            return []

    run = await _run()
    assert any("selector matched 0" in w for w in run.warnings)


# --- SourceResult model -----------------------------------------------------

def test_source_result_rejects_an_unknown_status():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SourceResult(key="k", label="K", kind="public", status="probably-fine")

"""Tests for the tier-3 login-gated portal adapters (`providers/portal_*.py`).

Two layers:

1. `portal_common.scrape_search_results` — the shared scraping logic every
   adapter calls — is exercised for real against a local fixture HTTP server
   (never a live portal, spec §8), including the case that matters most: a
   results selector matching zero elements must warn loudly, not return a
   silently-empty list.
2. Every registered `portal_*` adapter is checked for valid, sane meta
   (kind, login fields, a non-empty `logged_in_selector`) without touching a
   network — that's just reading `SourceMeta`.
"""

import asyncio
import http.server
import threading
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.models import Profile
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceUnavailable
from app.sources.providers import portal_common

FIXTURES = Path(__file__).parent / "fixtures"

PORTAL_KEYS = [
    "naukri", "internshala", "instahyre", "cutshort", "freshersworld", "superset",
    "linkedin", "glassdoor", "wellfound", "trueup", "stepstone", "xing",
]


@pytest.fixture(scope="module")
def fixture_server():
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIXTURES), **kwargs)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=5)


async def _make_page():
    """Launch a throwaway headless page. Not a pytest fixture — see note below.

    Kept as a plain helper (called with `await` inside each test) rather than
    an async generator fixture, so this file doesn't depend on how a given
    pytest-asyncio version wires up async fixtures under `asyncio_mode=auto`.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    return pw, browser, page


async def _close_page(pw, browser) -> None:
    await browser.close()
    await pw.stop()


# --- shared scraping helper, against local fixtures --------------------------

async def test_scrape_search_results_extracts_jobs_from_fixture(fixture_server):
    pw, browser, page = await _make_page()
    try:
        async def opener(_portal):
            return page

        ctx = FetchContext(profile=Profile(), queries=["backend"], client=None, page_opener=opener)
        jobs = await portal_common.scrape_search_results(
            ctx,
            portal="fixtureportal",
            search_url_template=f"{fixture_server}/portal_results.html?q={{query}}",
            results_selector=".job-card",
            title_selector=".job-title",
            link_selector="a.job-link",
            company_selector=".job-company",
            location_selector=".job-location",
            region="global",
        )
    finally:
        await _close_page(pw, browser)

    assert ctx.warnings == []
    assert len(jobs) == 2
    assert {j.title for j in jobs} == {"Senior Backend Engineer", "Platform Engineer"}
    assert {j.company for j in jobs} == {"Acme Corp", "Globex"}
    assert all(j.source == "fixtureportal" and j.region == "global" for j in jobs)
    assert all(j.url.startswith(fixture_server) for j in jobs)  # relative hrefs resolved


async def test_scrape_search_results_warns_loudly_on_zero_matches(fixture_server):
    """The exact failure mode the Track C brief calls out: a selector matching
    nothing must never come back as a quiet empty list."""
    pw, browser, page = await _make_page()
    try:
        async def opener(_portal):
            return page

        ctx = FetchContext(profile=Profile(), queries=["nonexistent-role"], client=None, page_opener=opener)
        jobs = await portal_common.scrape_search_results(
            ctx,
            portal="fixtureportal",
            search_url_template=f"{fixture_server}/portal_empty.html?q={{query}}",
            results_selector=".job-card",
            title_selector=".job-title",
            link_selector="a.job-link",
            region="global",
            results_timeout_ms=300,
        )
    finally:
        await _close_page(pw, browser)

    assert jobs == []
    assert len(ctx.warnings) == 1
    assert "matched 0 elements" in ctx.warnings[0]
    assert "fixtureportal" in ctx.warnings[0]


async def test_scrape_search_results_warns_per_query_not_once_overall(fixture_server):
    pw, browser, page = await _make_page()
    try:
        async def opener(_portal):
            return page

        ctx = FetchContext(
            profile=Profile(), queries=["a", "b"], client=None, page_opener=opener,
        )
        await portal_common.scrape_search_results(
            ctx,
            portal="fixtureportal",
            search_url_template=f"{fixture_server}/portal_empty.html?q={{query}}",
            results_selector=".job-card",
            title_selector=".job-title",
            link_selector="a.job-link",
            results_timeout_ms=300,
        )
    finally:
        await _close_page(pw, browser)

    assert len(ctx.warnings) == 2  # one per query, not deduplicated away


async def test_scrape_propagates_source_unavailable_without_a_page_opener():
    """No FetchContext.page_opener configured -> fails loudly, not with an
    empty result set (mirrors `FetchContext.open_page`'s own contract)."""
    ctx = FetchContext(profile=Profile(), queries=["x"], client=None)
    with pytest.raises(SourceUnavailable):
        await portal_common.scrape_search_results(
            ctx, portal="naukri",
            search_url_template="https://example.invalid/{query}",
            results_selector=".x", title_selector=".x", link_selector="a",
        )


# --- registered adapters: meta sanity, no network -----------------------------

def test_all_twelve_portal_adapters_are_registered_with_valid_meta():
    registry.load_providers()
    for key in PORTAL_KEYS:
        src = registry.get(key)
        assert src is not None, f"{key} is not registered"
        assert src.meta.kind is SourceKind.PORTAL
        assert src.meta.requires_login is True
        assert src.meta.login_url.startswith("https://"), key
        assert src.meta.logged_in_probe.startswith("https://"), key
        assert src.meta.logged_in_selector, f"{key} has an empty logged_in_selector"
        assert asyncio.iscoroutinefunction(src.fetch)


def test_linkedin_ships_disabled_with_a_warning_and_conservative_limits():
    registry.load_providers()
    src = registry.get("linkedin")
    assert src.meta.enabled_by_default is False
    assert src.meta.warning
    assert src.meta.rate_limit_s == 8.0
    assert src.meta.daily_cap == 60


def test_glassdoor_gets_the_same_conservative_treatment_as_linkedin():
    registry.load_providers()
    src = registry.get("glassdoor")
    assert src.meta.enabled_by_default is False
    assert src.meta.warning


def test_indian_and_german_portals_are_enabled_by_default():
    """Only LinkedIn/Glassdoor are singled out for conservative treatment (spec §6.2)."""
    registry.load_providers()
    for key in ("naukri", "internshala", "instahyre", "cutshort", "freshersworld",
                "superset", "stepstone", "xing", "wellfound", "trueup"):
        assert registry.get(key).meta.enabled_by_default is True, key

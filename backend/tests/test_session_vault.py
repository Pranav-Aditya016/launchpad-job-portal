"""Tests for the session vault (`app.browser.session`).

Everything here runs against a local fixture HTTP server serving saved HTML —
never a real portal (spec §8). Real Chromium *is* exercised (headless) for the
end-to-end paths, since Playwright and its browsers are already installed in
this environment; the concurrency-limit tests instead monkeypatch the one
Playwright launch seam (`session._open_context`) so they run fast and
deterministically without needing N real browser processes.
"""

import asyncio
import http.server
import threading
from pathlib import Path

import pytest

from app import config as cfg
from app import store
from app.browser import session
from app.models import Connection
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceMeta

FIXTURES = Path(__file__).parent / "fixtures"


# --- shared fixtures --------------------------------------------------------

@pytest.fixture(scope="module")
def fixture_server():
    """A tiny local HTTP server serving backend/tests/fixtures/*.html."""

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIXTURES), **kwargs)

        def log_message(self, *args):  # keep pytest output quiet
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Point the store and the vault's session dirs at a scratch directory."""
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "EVAL_DIR", tmp_path / "evaluations")
    monkeypatch.setattr(cfg, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "evaluations").mkdir()
    (tmp_path / "output").mkdir()
    return tmp_path


@pytest.fixture(autouse=True)
async def clean_vault_state():
    """Isolate the module-level session state, and — critically — make sure no
    background login watcher outlives this test's event loop.

    `open_login_window` deliberately returns immediately and leaves a watcher
    task holding a real Chromium. pytest-asyncio closes the loop after each
    test, and closing a loop CANCELS surviving tasks and waits for them. A task
    parked inside Playwright's Windows IOCP poll does not answer cancellation,
    so the whole suite hangs in loop teardown — not in any test, which is why
    it showed up as "test_session_vault stops at 78%" with no failing name.

    Draining here rather than in each test means a future test cannot
    reintroduce the hang by forgetting to.
    """
    session._open_contexts.clear()
    yield
    try:
        await session.drain_background_tasks(timeout=15.0)
    finally:
        await session.close_all_pages()
        session._open_contexts.clear()
        # Per-loop now (see session._sems); this just stops the dict growing.
        session._SEMS.clear()


@pytest.fixture
def registered_portal(fixture_server):
    """Register a throwaway PORTAL source pointing at the fixture server."""
    saved, was_loaded = dict(registry._REGISTRY), registry._LOADED

    @registry.register
    class _FixturePortal:
        meta = SourceMeta(
            key="fixtureportal",
            label="Fixture Portal",
            kind=SourceKind.PORTAL,
            requires_login=True,
            login_url=f"{fixture_server}/portal_login.html",
            logged_in_probe=f"{fixture_server}/portal_probe_loggedin.html",
            logged_in_selector=".profile-name",
        )

        async def fetch(self, ctx):
            return []

    yield "fixtureportal", fixture_server

    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)
    registry._LOADED = was_loaded


# --- stale lock clearing ----------------------------------------------------

def test_clear_stale_lock_removes_known_lock_files(tmp_path):
    profile = tmp_path / "sessions" / "somewhere"
    profile.mkdir(parents=True)
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        (profile / name).write_text("stale")
    session._clear_stale_lock(profile)
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        assert not (profile / name).exists()


def test_clear_stale_lock_on_missing_dir_does_not_raise(tmp_path):
    session._clear_stale_lock(tmp_path / "does" / "not" / "exist")  # must not raise


# --- verify() ----------------------------------------------------------------

async def test_verify_unknown_portal_is_disconnected_not_a_crash():
    conn = await session.verify("no-such-portal")
    assert conn.status == "disconnected"


async def test_verify_with_no_profile_dir_is_disconnected():
    conn = await session.verify("naukri")  # real portal, but never logged in
    assert conn.status == "disconnected"
    assert "not connected" in conn.note.lower()


async def test_verify_detects_a_live_session(registered_portal):
    portal, _server = registered_portal
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)
    conn = await session.verify(portal)
    assert conn.status == "connected"
    await session.drain_background_tasks()
    assert conn.last_verified is not None


async def test_verify_detects_an_expired_session(registered_portal, monkeypatch, fixture_server):
    portal, _server = registered_portal
    src = registry.get(portal)
    # Point the probe at a page that lacks the logged-in marker.
    object.__setattr__(src.meta, "logged_in_probe", f"{fixture_server}/portal_probe_loggedout.html")
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)
    conn = await session.verify(portal)
    assert conn.status == "expired"


async def test_verify_degrades_on_launch_failure_instead_of_raising(registered_portal, monkeypatch):
    portal, _server = registered_portal
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)

    async def _boom(*a, **kw):
        raise RuntimeError("simulated: browser executable not found")

    monkeypatch.setattr(session, "_open_context", _boom)
    conn = await session.verify(portal)  # must not raise
    assert conn.status == "expired"
    assert "browser executable not found" in conn.note


async def test_verify_releases_the_headless_semaphore_even_on_failure(registered_portal, monkeypatch):
    portal, _server = registered_portal
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)

    async def _boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(session, "_open_context", _boom)
    before = session._sems()["headless"]._value
    await session.verify(portal)
    assert session._sems()["headless"]._value == before


# --- concurrency limits (spec §12.3) -----------------------------------------

async def test_at_most_two_concurrent_headless_contexts(registered_portal, monkeypatch):
    """Three simultaneous verify() calls never let more than 2 launches overlap."""
    portal, _server = registered_portal
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)

    current = 0
    peak = 0
    lock = asyncio.Lock()

    class _FakeLocator:
        async def count(self):
            return 1

    class _FakePage:
        async def goto(self, *a, **kw):
            class _Resp:
                status = 200
            return _Resp()

        def locator(self, *_a, **_kw):
            return _FakeLocator()

        async def content(self):
            return "<html></html>"

    class _FakeContext:
        async def new_page(self):
            return _FakePage()

        async def close(self):
            pass

    class _FakePw:
        async def stop(self):
            pass

    async def _fake_open_context(user_data_dir, *, headless, timeout_ms=None):
        nonlocal current, peak
        async with lock:
            current += 1
            peak = max(peak, current)
        await asyncio.sleep(0.05)
        async with lock:
            current -= 1
        return _FakePw(), _FakeContext()

    monkeypatch.setattr(session, "_open_context", _fake_open_context)
    await asyncio.gather(*(session.verify(portal) for _ in range(5)))

    assert peak <= 2


async def test_exactly_one_headed_window_at_a_time(registered_portal, monkeypatch):
    portal, server = registered_portal
    src = registry.get(portal)

    current = 0
    peak = 0
    lock = asyncio.Lock()

    class _FakeLocator:
        async def count(self):
            return 0  # never "logs in" — we only care about overlap, not outcome

    class _FakePage:
        async def goto(self, *a, **kw):
            return None

        def locator(self, *_a, **_kw):
            return _FakeLocator()

    class _FakeContext:
        async def new_page(self):
            return _FakePage()

        async def close(self):
            pass

    class _FakePw:
        async def stop(self):
            pass

    async def _fake_open_context(user_data_dir, *, headless, timeout_ms=None):
        nonlocal current, peak
        async with lock:
            current += 1
            peak = max(peak, current)
        await asyncio.sleep(0.05)
        async with lock:
            current -= 1
        return _FakePw(), _FakeContext()

    monkeypatch.setattr(session, "_open_context", _fake_open_context)
    monkeypatch.setattr(session, "LOGIN_TIMEOUT_S", 0.15)
    monkeypatch.setattr(session, "POLL_INTERVAL_S", 0.05)

    await asyncio.gather(*(session._run_login_window(portal, src.meta) for _ in range(3)))

    assert peak <= 1


# --- login window (real Playwright, headless override, local fixtures) ------

async def test_login_window_detects_manual_login_via_watcher(registered_portal, monkeypatch):
    portal, server = registered_portal
    src = registry.get(portal)
    monkeypatch.setattr(session, "POLL_INTERVAL_S", 0.1)
    monkeypatch.setattr(session, "LOGIN_TIMEOUT_S", 10)

    # Force headless even though this exercises the real "headed login" code
    # path — a test process should never pop a visible window. The fixture
    # page's own script inserts `.profile-name` (this fixture's
    # logged_in_selector) after 400ms to stand in for a human finishing
    # login by hand.
    real_open_context = session._open_context

    async def _headless_override(user_data_dir, *, headless, timeout_ms=None):
        return await real_open_context(user_data_dir, headless=True, timeout_ms=timeout_ms)

    monkeypatch.setattr(session, "_open_context", _headless_override)

    conn = await session.open_login_window(portal)
    assert conn.status == "checking"

    # Wait for the background watcher to finish (bounded well under its own timeout).
    for _ in range(100):
        conn = store.load_connections().get(portal)
        if conn and conn.status != "checking":
            break
        await asyncio.sleep(0.1)

    assert conn.status == "connected"


async def test_login_window_times_out_when_marker_never_appears(registered_portal, monkeypatch, fixture_server):
    portal, server = registered_portal
    src = registry.get(portal)
    object.__setattr__(src.meta, "login_url", f"{fixture_server}/portal_login_never.html")
    monkeypatch.setattr(session, "POLL_INTERVAL_S", 0.05)
    monkeypatch.setattr(session, "LOGIN_TIMEOUT_S", 0.3)

    real_open_context = session._open_context

    async def _headless_override(user_data_dir, *, headless, timeout_ms=None):
        return await real_open_context(user_data_dir, headless=True, timeout_ms=timeout_ms)

    monkeypatch.setattr(session, "_open_context", _headless_override)

    await session.open_login_window(portal)
    for _ in range(100):
        conn = store.load_connections().get(portal)
        if conn and conn.status != "checking":
            break
        await asyncio.sleep(0.1)

    assert conn.status == "disconnected"
    assert "time" in conn.note.lower() or "closed" in conn.note.lower()
    await session.drain_background_tasks()


# --- disconnect --------------------------------------------------------------

async def test_disconnect_deletes_the_profile_directory_and_the_record():
    profile = cfg.DATA_DIR / "sessions" / "naukri"
    profile.mkdir(parents=True)
    (profile / "Default").mkdir()
    store.save_connection(Connection(portal="naukri", status="connected"))

    await session.disconnect("naukri")

    assert not profile.exists()
    assert "naukri" not in store.load_connections()


# --- open_page (FetchContext.page_opener) ------------------------------------

async def test_open_page_without_a_session_raises_source_unavailable(registered_portal):
    from app.sources.base import SourceUnavailable
    portal, _server = registered_portal
    with pytest.raises(SourceUnavailable):
        await session.open_page(portal)


async def test_open_page_reuses_one_context_per_portal(registered_portal):
    portal, _server = registered_portal
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)
    try:
        page1 = await session.open_page(portal)
        page2 = await session.open_page(portal)
        assert page1 is page2
    finally:
        await session.close_all_pages()


async def test_close_all_pages_releases_the_headless_semaphore(registered_portal):
    portal, _server = registered_portal
    (cfg.DATA_DIR / "sessions" / portal).mkdir(parents=True)
    before = session._sems()["headless"]._value
    await session.open_page(portal)
    assert session._sems()["headless"]._value == before - 1
    await session.close_all_pages()
    assert session._sems()["headless"]._value == before
    assert session._open_contexts == {}

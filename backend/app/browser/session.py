"""The session vault: one persistent Chromium profile per login-gated portal.

BOUNDARY (spec §2, §6.3): LaunchPad never stores a credential and never fills
or clicks a login form. `open_login_window` opens a real, visible browser
window at the portal's login page and returns; the user does the actual
logging in — password, OTP, CAPTCHA, 2FA, all of it, in their own hands. A
background watcher only *looks* at the page (polls for `logged_in_selector`);
it never types into it. There is no field for a credential anywhere below.

Hardware budgets (spec §12.3) — not optional on an 8 GB-VRAM laptop:
  - at most 2 concurrent HEADLESS Chromium contexts
  - exactly 1 HEADED window at a time, used for a login or an
    apply-prepare (Track D)
  - every context this module opens is closed in a `finally`
  - a stale profile lock (left behind by a hard shutdown) is cleared before
    each launch rather than hanging forever
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from app import config as cfg
from app import store
from app.models import Connection
from app.sources import registry
from app.sources.base import SourceKind, SourceMeta, SourceUnavailable

# --- hardware budgets (spec §12.3) -----------------------------------------

# Concurrency caps (spec §12.3), kept PER EVENT LOOP.
#
# A module-level asyncio.Semaphore is bound to whichever loop first awaited it.
# Reusing one across loops is undefined behaviour, and it deadlocked the test
# suite for real: pytest-asyncio gives each test a fresh loop, a fire-and-forget
# login task from one test was destroyed with the loop while still holding the
# headed slot, and the next test blocked forever acquiring it. Keying by the
# running loop makes each loop's limits independent and self-healing.
MAX_HEADLESS = 2
MAX_HEADED = 1

_SEMS: dict[int, dict[str, asyncio.Semaphore]] = {}


def _sems() -> dict[str, asyncio.Semaphore]:
    loop = asyncio.get_running_loop()
    got = _SEMS.get(id(loop))
    if got is None:
        got = {
            "headless": asyncio.Semaphore(MAX_HEADLESS),
            "headed": asyncio.Semaphore(MAX_HEADED),
        }
        _SEMS[id(loop)] = got
    return got


async def drain_background_tasks(timeout: float = 10.0) -> None:
    """Await the fire-and-forget login watchers.

    Tests need this: without it a watcher outlives its event loop, its
    `finally` never runs, and the slot it holds is never given back.
    """
    pending = [t for t in _background_tasks if not t.done()]
    if pending:
        await asyncio.wait(pending, timeout=timeout)

# --- timings -----------------------------------------------------------

LOGIN_TIMEOUT_S = 300.0   # 5 minutes to complete a manual login
POLL_INTERVAL_S = 2.0     # how often the watcher checks for logged_in_selector
LAUNCH_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS = 25_000

_STALE_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")

_BLOCK_HINTS = (
    "captcha", "unusual traffic", "automated", "are you a robot",
    "access denied", "blocked", "forbidden", "rate limit", "too many requests",
)

# Long-lived pages handed out via `open_page`, one per portal, reused across
# calls within a scan cycle. `close_all_pages()` — meant to be called by the
# scheduler at the end of every cycle (spec §12.3's "sweep") — tears them all
# down and releases the semaphore slots they hold.
_open_contexts: dict[str, dict[str, Any]] = {}
_open_lock = asyncio.Lock()

# Background login-watcher tasks, kept referenced so they aren't garbage
# collected mid-flight (asyncio only holds a weak reference otherwise).
_background_tasks: set[asyncio.Task] = set()


def _sessions_dir(portal: str) -> Path:
    return cfg.DATA_DIR / "sessions" / portal


def portal_meta(portal: str) -> SourceMeta | None:
    """The registered PORTAL source's meta, or None if `portal` isn't one."""
    registry.load_providers()
    src = registry.get(portal)
    if src is None or src.meta.kind is not SourceKind.PORTAL:
        return None
    return src.meta


def _clear_stale_lock(user_data_dir: Path) -> None:
    """Remove Chromium's singleton-profile lock files before launching.

    These can survive a hard shutdown (power loss, task-killed process) and
    make the next `launch_persistent_context` hang indefinitely waiting on a
    process that no longer exists (spec §12.3). Our own semaphores already
    serialize this app's use of a given profile, so it's safe to clear these
    unconditionally before every launch rather than trying to detect
    liveness — a genuinely live browser using the profile would simply
    recreate its lock.
    """
    if not user_data_dir.exists():
        return
    for name in _STALE_LOCK_NAMES:
        with contextlib.suppress(OSError):
            (user_data_dir / name).unlink()


async def _open_context(user_data_dir: Path, *, headless: bool, timeout_ms: int = LAUNCH_TIMEOUT_MS):
    """Launch a persistent Chromium profile. The one real Playwright seam.

    Isolated so tests can monkeypatch exactly this call without faking the
    rest of the vault's control flow (concurrency limits, degrade-on-error,
    the watch loop).
    """
    user_data_dir.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    try:
        context = await pw.chromium.launch_persistent_context(
            str(user_data_dir), headless=headless, timeout=timeout_ms,
        )
    except Exception:
        await pw.stop()
        raise
    return pw, context


async def _close_context(pw, context) -> None:
    with contextlib.suppress(Exception):
        await context.close()
    with contextlib.suppress(Exception):
        await pw.stop()


def _save(portal: str, *, status: str, note: str, touch_verified: bool = False) -> Connection:
    existing = store.load_connections().get(portal)
    last_verified = existing.last_verified if existing else None
    if touch_verified:
        last_verified = datetime.now(timezone.utc).isoformat()
    conn = Connection(portal=portal, status=status, note=note, last_verified=last_verified)
    store.save_connection(conn)
    return conn


# --- login -------------------------------------------------------------

async def open_login_window(portal: str) -> Connection:
    """Kick off a headed login window for `portal` and return immediately.

    The actual browser launch + watch-for-login runs as a background task —
    this coroutine only validates the portal and schedules that task, so the
    HTTP route built on top of it returns right away rather than blocking on
    however long the user takes to type a password, solve a CAPTCHA, or
    approve a 2FA prompt (could be minutes).
    """
    meta = portal_meta(portal)
    if meta is None:
        raise SourceUnavailable(f"{portal}: not a registered portal source")

    conn = _save(portal, status="checking", note="waiting for you to finish logging in…")
    task = asyncio.create_task(_run_login_window(portal, meta), name=f"login-window-{portal}")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return conn


async def _run_login_window(portal: str, meta: SourceMeta) -> None:
    """Open the headed window, watch for login, persist the outcome.

    Never raises out of this function — any failure here degrades the
    connection to `expired`/`blocked` with a human-readable note instead of
    crashing an unattended scheduler loop (spec §7).
    """
    user_data_dir = _sessions_dir(portal)
    async with _sems()["headed"]:
        _clear_stale_lock(user_data_dir)
        pw = context = None
        try:
            pw, context = await _open_context(user_data_dir, headless=False)
            page = await context.new_page()
            await page.goto(meta.login_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            ok = await _wait_for_selector(page, meta.logged_in_selector, LOGIN_TIMEOUT_S)
            if ok:
                _save(portal, status="connected", note="", touch_verified=True)
            else:
                _save(
                    portal, status="disconnected",
                    note="login window closed or timed out before login completed — try again",
                )
        except Exception as e:
            _save(portal, status="expired", note=f"login window failed: {e}"[:300])
        finally:
            if pw is not None:
                await _close_context(pw, context)


async def _wait_for_selector(page, selector: str, timeout_s: float) -> bool:
    if not selector:
        return False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if await page.locator(selector).count() > 0:
                return True
        except Exception:
            return False  # page/context closed — the user closed the window
        await asyncio.sleep(POLL_INTERVAL_S)
    return False


# --- verify --------------------------------------------------------------

async def verify(portal: str) -> Connection:
    """Open the profile headless, hit `logged_in_probe`, check the selector.

    Updates and returns the stored `Connection`. Never raises: every failure
    mode (no browser, locked profile, portal redesign, a bot-check page)
    degrades to `expired` or `blocked` with a human-readable note (spec §7).
    """
    meta = portal_meta(portal)
    if meta is None:
        return _save(portal, status="disconnected", note=f"unknown portal '{portal}'")

    user_data_dir = _sessions_dir(portal)
    if not user_data_dir.exists():
        return _save(portal, status="disconnected", note="not connected yet — use Login to sign in")

    await _sems()["headless"].acquire()
    try:
        return await _verify_inner(portal, meta, user_data_dir)
    except Exception as e:
        return _save(portal, status="expired", note=f"verify failed: {e}"[:300])
    finally:
        _sems()["headless"].release()


async def _verify_inner(portal: str, meta: SourceMeta, user_data_dir: Path) -> Connection:
    _clear_stale_lock(user_data_dir)
    pw, context = await _open_context(user_data_dir, headless=True)
    try:
        page = await context.new_page()
        probe_url = meta.logged_in_probe or meta.login_url
        try:
            resp = await page.goto(probe_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception as e:
            msg = str(e)
            status = "blocked" if any(h in msg.lower() for h in _BLOCK_HINTS) else "expired"
            return _save(portal, status=status, note=f"could not reach {portal}: {msg}"[:300])

        status_code = resp.status if resp is not None else None
        if status_code in (403, 429, 999):
            return _save(
                portal, status="blocked",
                note=f"{portal} returned HTTP {status_code} — likely rate-limited or blocking automation",
            )

        found = 0
        if meta.logged_in_selector:
            with contextlib.suppress(Exception):
                found = await page.locator(meta.logged_in_selector).count()
        if found > 0:
            return _save(portal, status="connected", note="", touch_verified=True)

        body_text = ""
        with contextlib.suppress(Exception):
            body_text = (await page.content()).lower()
        if any(h in body_text for h in _BLOCK_HINTS):
            return _save(portal, status="blocked", note=f"{portal} appears to be showing a bot-check page")

        return _save(portal, status="expired", note="session no longer valid — please log in again")
    finally:
        await _close_context(pw, context)


# --- disconnect ------------------------------------------------------------

async def disconnect(portal: str) -> None:
    """Delete the profile directory. That is a real logout (spec §6.3)."""
    if portal in _open_contexts:
        await close_page(portal)
    shutil.rmtree(_sessions_dir(portal), ignore_errors=True)
    store.delete_connection(portal)


# --- fetch-time page access (FetchContext.page_opener) --------------------

async def open_page(portal: str):
    """Return a `Page` bound to `portal`'s persistent profile (headless).

    This is what gets injected as `FetchContext.page_opener` — a PORTAL
    source's `fetch` calls `ctx.open_page(portal)` to get a logged-in page.
    One context per portal is kept open and reused across calls within a scan
    cycle; call `close_all_pages()` (meant to run at the end of every cycle,
    spec §12.3) to close them and release their concurrency-limit slots.
    """
    async with _open_lock:
        entry = _open_contexts.get(portal)
        if entry is not None:
            return entry["page"]

        meta = portal_meta(portal)
        if meta is None:
            raise SourceUnavailable(f"{portal}: not a registered portal source")
        user_data_dir = _sessions_dir(portal)
        if not user_data_dir.exists():
            raise SourceUnavailable(
                f"{portal}: no browser session — connect via POST /connections/{portal}/login first"
            )

        await _sems()["headless"].acquire()
        try:
            _clear_stale_lock(user_data_dir)
            pw, context = await _open_context(user_data_dir, headless=True)
            page = await context.new_page()
        except Exception as e:
            _sems()["headless"].release()
            raise SourceUnavailable(f"{portal}: could not open browser session ({e})") from e

        _open_contexts[portal] = {"pw": pw, "context": context, "page": page}
        return page


async def close_page(portal: str) -> None:
    async with _open_lock:
        entry = _open_contexts.pop(portal, None)
    if entry is None:
        return
    await _close_context(entry["pw"], entry["context"])
    _sems()["headless"].release()


async def close_all_pages() -> None:
    """Close every page opened via `open_page`. Call at the end of a scan cycle."""
    for portal in list(_open_contexts):
        await close_page(portal)

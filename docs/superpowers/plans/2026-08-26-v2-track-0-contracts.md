# LaunchPad v2 — Track 0: Frozen Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land every shared interface, model, route and design token that the five
parallel v2 tracks build against, so those tracks can run simultaneously without ever
editing the same file.

**Architecture:** A plugin-style source registry (`base.py` + `registry.py`) lets a
track add a job source by creating one new file. Six new routers replace all shared
route surface, so `api.py` is edited exactly once — here — and then frozen. New
pydantic models and store accessors give every track its persistence layer up front.
Design tokens land in `globals.css` so no track invents colors.

**Tech Stack:** Python 3.13, FastAPI, pydantic v2, pytest; Next.js 16 / React 19 /
Tailwind 4 / motion. New deps: APScheduler 3.11, sse-starlette 3.3, Playwright 1.62,
numpy 2.2 (all but APScheduler already installed on this machine).

**Spec:** `docs/superpowers/specs/2026-08-26-launchpad-v2-offline-autopilot-design.md`

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include these.

- **No credential storage, no authentication bypass.** No model, request body, or form
  in this system may contain a field for a username, password, OTP, or security answer.
- **No autonomous submission.** No code path may click a submit button. Enforced by
  `tests/test_no_autosubmit.py` (Task 8).
- **One LLM call at a time** — process-wide `asyncio.Semaphore(1)`.
- **Model size ceiling 6.5 GB**; `num_ctx` stays at **8192**; Ollama `keep_alive: "5m"`.
- **Cycle wall-clock cap 20 minutes**; `max_instances=1`, `coalesce=True`.
- **At most 2 concurrent headless Chromium contexts, exactly 1 headed window.**
- **All writes abort if free disk is under 2 GB.**
- Every source failure is caught **per-source** and surfaced as a warning; a scan where
  39 of 40 sources fail still returns the 40th's jobs.
- Every write goes through `store._write_atomic`; every read tolerates corruption.
- Glass surfaces keep **≥4.5:1** text contrast; every animation respects
  `prefers-reduced-motion`.
- Backward compatibility: `Profile`, `Job`, `Evaluation`, `TailoredDoc` keep every v1
  field with v1 defaults. Existing `launchpad_data/` files must still load.

## File Structure

| File | Responsibility |
|---|---|
| `backend/pyproject.toml` | **Modify.** Add v2 deps; move `anthropic` to a `hosted` extra. |
| `backend/app/models.py` | **Modify.** Append `Connection`, `ScanRun`, `QueueItem`; add two optional `Job` fields. |
| `backend/app/sources/base.py` | **Create.** `SourceKind`, `SourceMeta`, `FetchContext`, `Source` protocol. Zero I/O, zero deps beyond pydantic/stdlib. |
| `backend/app/sources/registry.py` | **Create.** `@register` decorator, provider autoloading, lookup helpers. |
| `backend/app/sources/providers/__init__.py` | **Create.** Empty package; tracks B and C drop files here. |
| `backend/app/store.py` | **Modify.** Append accessors for connections, queue, runs, source config, embeddings. |
| `backend/app/routes/__init__.py` | **Create.** Package marker. |
| `backend/app/routes/config.py` | **Create.** `/config`, moved verbatim out of `api.py`. Owned by Track A after this. |
| `backend/app/routes/sources.py` | **Create.** `GET /sources`, `PUT /sources/{key}`. Fully real — depends only on registry + store. |
| `backend/app/routes/connections.py` | **Create.** `GET /connections` real; the three action routes return 501. Track C replaces. |
| `backend/app/routes/schedule.py` | **Create.** `GET /schedule`, `GET /runs` real; `PUT`/`run-now` return 501. Track D replaces. |
| `backend/app/routes/queue.py` | **Create.** `GET /queue` real; the three action routes return 501. Track D replaces. |
| `backend/app/routes/events.py` | **Create.** `GET /events` SSE, heartbeat only. Track D replaces. |
| `backend/app/api.py` | **Modify once, then frozen.** Include six routers; delete the inline `/config`. |
| `frontend/app/globals.css` | **Modify.** Add the glass token block for both themes. |
| `scripts/seed-demo-data.ps1` | **Create.** Writes sample data so Track E can build UI against shaped, non-empty responses. |
| `backend/tests/test_registry.py` | **Create.** Registry invariants. |
| `backend/tests/test_no_autosubmit.py` | **Create.** Boundary enforcement. |
| `backend/tests/test_v2_models.py` | **Create.** New models + v1 backward compatibility. |
| `backend/tests/test_v2_routes.py` | **Create.** Every new route is reachable and shaped. |

**Why 501 and not fake data:** a stub returning invented jobs can ship to production
unnoticed. A 501 with a message naming the owning track cannot. Track E gets its
non-empty data from `seed-demo-data.ps1` writing real files that the *real* read paths
then serve.

---

### Task 1: Dependencies and the `hosted` extra

**Files:**
- Modify: `backend/pyproject.toml:5-13`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `apscheduler`, `sse_starlette`, `playwright`, `numpy`.
  `anthropic` becomes optional — `app/llm.py` already imports it lazily inside
  `_api_client()`, so a clean install with no cloud SDK still runs.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_v2_deps.py`:

```python
"""v2 dependency floors. Cheap, but these failing as ImportError deep inside a
scheduler tick is much harder to diagnose than failing here."""
import importlib


def test_v2_runtime_deps_importable():
    for mod in ("apscheduler", "sse_starlette", "playwright", "numpy"):
        assert importlib.import_module(mod) is not None


def test_anthropic_is_not_a_hard_dependency():
    """The product must run fully offline. `anthropic` may be installed on a dev
    box, but it must not be in the required dependency list."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    required = " ".join(data["project"]["dependencies"])
    assert "anthropic" not in required
    assert "anthropic" in " ".join(data["project"]["optional-dependencies"]["hosted"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_v2_deps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apscheduler'`, and the second
test fails on `KeyError: 'hosted'`.

- [ ] **Step 3: Edit `pyproject.toml`**

Replace the `dependencies` and `optional-dependencies` blocks with:

```toml
dependencies = [
  "fastapi>=0.110", "uvicorn[standard]>=0.29", "httpx>=0.27",
  "pydantic>=2.6", "python-multipart>=0.0.9",
  "markitdown[pdf,docx]>=0.0.1a2", "weasyprint>=61",
  "crawl4ai>=0.4", "markdown>=3.6", "pyyaml>=6.0",
  # v2
  "apscheduler>=3.11", "sse-starlette>=3.3", "playwright>=1.62", "numpy>=2.0",
]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]
# Opt-in cloud provider. NOT required: the product's default path is fully local
# via Ollama. app/llm.py imports anthropic lazily so its absence is never fatal.
hosted = ["anthropic>=0.39"]
# Opt-in tier-4 agentic fallback (§4.1). Heavy; only pulled if the user wants it.
agentic = ["browser-use>=0.2"]
```

- [ ] **Step 4: Install and verify the test passes**

```bash
cd backend && pip install -e ".[dev]" && python -m pytest tests/test_v2_deps.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Verify nothing regressed**

Run: `cd backend && python -m pytest -q`
Expected: the v1 suite still passes (45 passed / 3 skipped, plus the 2 new).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/tests/test_v2_deps.py
git commit -m "chore: v2 deps; anthropic becomes an optional 'hosted' extra"
```

---

### Task 2: New models

**Files:**
- Modify: `backend/app/models.py` (append; do not touch existing classes except the two `Job` additions)
- Test: `backend/tests/test_v2_models.py`

**Interfaces:**
- Consumes: `_to_str`, `_to_str_list` (existing module-private coercers).
- Produces: `Connection(portal, status, last_verified, note)`,
  `ScanRun(id, started, finished, trigger, per_source, warnings, evaluated, tailored)`,
  `QueueItem(job_id, state, score, prepared_at, submitted_at, cv_pdf, notes)`,
  and `Job.region: str`, `Job.first_seen: str | None`.
  `ConnectionStatus` and `QueueState` are `Literal` aliases other tracks import.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_v2_models.py`:

```python
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


def test_profile_is_unchanged():
    p = Profile(name="A", skills="python")   # v1 coercion still applies
    assert p.skills == ["python"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_v2_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Connection' from 'app.models'`.

- [ ] **Step 3: Append to `backend/app/models.py`**

Add `Literal` to the existing typing imports at the top of the file, then append:

```python
ConnectionStatus = Literal["disconnected", "connected", "expired", "checking", "blocked"]
QueueState = Literal["ready", "prepared", "submitted", "skipped"]


class Connection(BaseModel):
    """Status of ONE login-gated portal.

    Deliberately holds no credential of any kind. LaunchPad never sees the user's
    password: they log in themselves in a real browser window and we persist only
    the resulting browser profile on local disk (spec §6.3). If you are ever
    tempted to add a `password` field here, re-read spec §2.
    """

    portal: str
    status: ConnectionStatus = "disconnected"
    last_verified: str | None = None   # ISO-8601
    note: str = ""                     # human-readable last error, shown in the UI

    @field_validator("note", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)


class ScanRun(BaseModel):
    """One scan cycle, manual or scheduled."""

    id: str
    started: str
    finished: str | None = None
    trigger: Literal["manual", "scheduled"] = "manual"
    per_source: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evaluated: int = 0
    tailored: int = 0
    partial: bool = False   # True when the 20-minute cycle cap cut the run short

    @field_validator("warnings", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        return _to_str_list(v)


class QueueItem(BaseModel):
    """A prepared application awaiting the user's own submit click.

    `submitted` means the USER told us they submitted it. Nothing in this system
    presses a submit button (spec §2, §6.5).
    """

    job_id: str
    state: QueueState = "ready"
    score: float = 0.0
    prepared_at: str | None = None
    submitted_at: str | None = None
    cv_pdf: str | None = None   # path relative to launchpad_data/output
    notes: str = ""

    @field_validator("notes", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
```

Then add the two fields to the existing `Job` class, immediately after `posted`:

```python
    region: str = ""              # "in" | "de" | "global" — from the source's meta
    first_seen: str | None = None # ISO-8601, set on first upsert
```

Then add `"region"` to `Job`'s existing `_coerce_str` validator field list, so it reads
`@field_validator("company", "title", "location", "description", "region", mode="before")`.
`region` is populated from adapter metadata in tracks B and C — the same loosely-typed
external input every other text field on this model coerces rather than rejects.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_v2_models.py -v`
Expected: 8 passed.

- [ ] **Step 5: Verify v1 data really loads**

```bash
cd backend && python -c "from app import store; print(len(store.load_jobs()), 'jobs loaded from real v1 data')"
```
Expected: a non-zero count and no traceback.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/tests/test_v2_models.py
git commit -m "feat: v2 models (Connection, ScanRun, QueueItem) + Job.region/first_seen"
```

---

### Task 3: Source protocol — `base.py`

**Files:**
- Create: `backend/app/sources/base.py`
- Test: `backend/tests/test_source_base.py`

**Interfaces:**
- Consumes: `app.models.Job`, `app.models.Profile`.
- Produces — **the exact names tracks B, C and D import**:
  `SourceKind` (`.PUBLIC`/`.ATS`/`.PORTAL`/`.CRAWL`),
  `SourceMeta(...)` frozen dataclass,
  `FetchContext(profile, queries, client, page_opener=None, limit=100, warnings=[])`,
  `Source` runtime-checkable protocol with `meta: SourceMeta` and
  `async fetch(ctx: FetchContext) -> list[Job]`.
  `FetchContext.warn(msg: str) -> None` appends to `ctx.warnings`.

Track C supplies `page_opener`; Track 0 leaves it `None`. A `PORTAL` source calling
`ctx.open_page(...)` when no opener is configured must raise a clear
`SourceUnavailable`. The field is public (`page_opener`, not `_open_page`) because
Track C constructs `FetchContext` by keyword.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_source_base.py`:

```python
import dataclasses

import pytest

from app.models import Job, Profile
from app.sources.base import (
    FetchContext, Source, SourceKind, SourceMeta, SourceUnavailable,
)


def test_source_meta_is_frozen():
    m = SourceMeta(key="k", label="K", kind=SourceKind.PUBLIC)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.key = "other"


def test_source_meta_defaults_are_conservative():
    m = SourceMeta(key="k", label="K", kind=SourceKind.PUBLIC)
    assert m.regions == ("global",)
    assert m.requires_login is False
    assert m.rate_limit_s == 2.0
    assert m.daily_cap == 500
    assert m.enabled_by_default is True
    assert m.warning == ""


def test_portal_meta_carries_login_probe_fields():
    m = SourceMeta(
        key="naukri", label="Naukri", kind=SourceKind.PORTAL, regions=("in",),
        requires_login=True, login_url="https://www.naukri.com/nlogin/login",
        logged_in_probe="https://www.naukri.com/mnjuser/homepage",
        logged_in_selector="[data-test='profile-name']", rate_limit_s=4.0, daily_cap=200,
    )
    assert m.requires_login and m.logged_in_selector


def test_fetch_context_warn_accumulates():
    ctx = FetchContext(profile=Profile(), queries=["dev"], client=None)
    ctx.warn("naukri: timed out")
    ctx.warn("linkedin: blocked")
    assert ctx.warnings == ["naukri: timed out", "linkedin: blocked"]


async def test_open_page_without_a_browser_raises_clearly():
    ctx = FetchContext(profile=Profile(), queries=[], client=None)
    with pytest.raises(SourceUnavailable, match="no browser session provider"):
        await ctx.open_page("naukri")


def test_a_minimal_class_satisfies_the_source_protocol():
    class Dummy:
        meta = SourceMeta(key="dummy", label="Dummy", kind=SourceKind.PUBLIC)

        async def fetch(self, ctx: FetchContext) -> list[Job]:
            return []

    assert isinstance(Dummy(), Source)


def test_a_class_missing_fetch_does_not_satisfy_the_protocol():
    class Broken:
        meta = SourceMeta(key="broken", label="B", kind=SourceKind.PUBLIC)

    assert not isinstance(Broken(), Source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_source_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sources.base'`.

- [ ] **Step 3: Create `backend/app/sources/base.py`**

```python
"""The one interface every job source implements.

Deliberately dependency-free: no httpx client construction, no Playwright import,
no store access. That is what lets tracks B, C and D develop against it in
parallel without importing each other's work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from app.models import Job, Profile


class SourceUnavailable(RuntimeError):
    """A source cannot run right now (no session, no browser, capped out).

    Distinct from a bug: the scheduler catches this, records a warning against the
    run, and carries on with every other source (spec §7).
    """


class SourceKind(str, Enum):
    PUBLIC = "public"   # tier 1 — open HTTP/JSON, no auth
    ATS = "ats"         # tier 2 — a company career site on a known ATS
    PORTAL = "portal"   # tier 3 — needs the user's own login session
    CRAWL = "crawl"     # curated page scrape


@dataclass(frozen=True)
class SourceMeta:
    """Everything the scheduler and UI need to know without running the source."""

    key: str                        # stable unique id, e.g. "naukri", "ats:greenhouse"
    label: str                      # display name
    kind: SourceKind
    regions: tuple[str, ...] = ("global",)
    requires_login: bool = False

    # tier 3 only — how the user connects, and how we later prove the session lives
    login_url: str = ""
    logged_in_probe: str = ""       # a URL only reachable when logged in
    logged_in_selector: str = ""    # CSS present only when logged in

    # Courtesy + account safety (spec §12.5). Enforced by the scheduler, not by
    # each adapter, so a careless adapter cannot hammer a host.
    rate_limit_s: float = 2.0
    daily_cap: int = 500

    enabled_by_default: bool = True
    warning: str = ""               # plain-language caution rendered on the UI card


PageOpener = Callable[[str], Awaitable[Any]]


@dataclass
class FetchContext:
    """Everything a source is handed. Sources never reach outside this."""

    profile: Profile
    queries: list[str]
    client: Any                             # httpx.AsyncClient, injected by the caller
    page_opener: PageOpener | None = None   # supplied by Track C's session vault
    limit: int = 100
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        """Record a non-fatal problem. Surfaces on the ScanRun, never raises."""
        self.warnings.append(message)

    async def open_page(self, portal: str) -> Any:
        """A Playwright page bound to `portal`'s persistent profile.

        Raises rather than returning None so a PORTAL source fails loudly and
        locally instead of producing a confusing empty result set.
        """
        if self.page_opener is None:
            raise SourceUnavailable(
                f"{portal}: no browser session provider is configured — "
                "the session vault is not running"
            )
        return await self.page_opener(portal)


@runtime_checkable
class Source(Protocol):
    meta: SourceMeta

    async def fetch(self, ctx: FetchContext) -> list[Job]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_source_base.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources/base.py backend/tests/test_source_base.py
git commit -m "feat: Source protocol, SourceMeta and FetchContext (v2 frozen contract)"
```

---

### Task 4: Source registry

**Files:**
- Create: `backend/app/sources/registry.py`
- Create: `backend/app/sources/providers/__init__.py` (empty file)
- Test: `backend/tests/test_registry.py`

**Interfaces:**
- Consumes: `base.Source`, `base.SourceMeta`.
- Produces: `register(cls)` decorator, `load_providers()`, `all_sources() -> list[Source]`,
  `get(key) -> Source | None`, `enabled_sources(overrides: dict[str, bool] | None) -> list[Source]`,
  `clear()` (test-only reset).

**This is how tracks B and C avoid each other:** each drops a new file into
`providers/` with an `@register` class. Neither edits `registry.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_registry.py`:

```python
import pytest

from app.models import Job
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceMeta


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


def _make(key, **kw):
    @registry.register
    class _S:
        meta = SourceMeta(key=key, label=key.title(), kind=SourceKind.PUBLIC, **kw)

        async def fetch(self, ctx: FetchContext) -> list[Job]:
            return []

    return _S


def test_register_then_get():
    _make("alpha")
    assert registry.get("alpha").meta.label == "Alpha"


def test_get_unknown_returns_none():
    assert registry.get("nope") is None


def test_duplicate_key_is_rejected_loudly():
    _make("dup")
    with pytest.raises(ValueError, match="duplicate source key"):
        _make("dup")


def test_all_sources_is_sorted_by_key_for_stable_ui_order():
    _make("zulu"); _make("alpha"); _make("mike")
    assert [s.meta.key for s in registry.all_sources()] == ["alpha", "mike", "zulu"]


def test_enabled_respects_meta_default():
    _make("on")
    _make("off", enabled_by_default=False)
    assert [s.meta.key for s in registry.enabled_sources(None)] == ["on"]


def test_user_override_beats_the_default_in_both_directions():
    _make("on")
    _make("off", enabled_by_default=False)
    keys = [s.meta.key for s in registry.enabled_sources({"on": False, "off": True})]
    assert keys == ["off"]


def test_registered_class_is_returned_unchanged():
    """@register must not replace the class — tracks subclass and unit-test these."""
    cls = _make("plain")
    assert isinstance(cls.meta, SourceMeta)


def test_load_providers_is_idempotent():
    registry.load_providers()
    first = len(registry.all_sources())
    registry.load_providers()
    assert len(registry.all_sources()) == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sources.registry'`.

- [ ] **Step 3: Create the providers package**

```bash
mkdir -p backend/app/sources/providers
printf '"""Job source adapters. One file per source; registry.load_providers() imports them all."""\n' > backend/app/sources/providers/__init__.py
```

- [ ] **Step 4: Create `backend/app/sources/registry.py`**

```python
"""Plugin registry for job sources.

A source is added by creating ONE new file in `providers/` with an @register class.
No track ever edits this file or `api.py` to add a source — that is what makes the
five v2 tracks safe to run in parallel.
"""

from __future__ import annotations

import importlib
import pkgutil

from app.sources.base import Source

_REGISTRY: dict[str, Source] = {}
_LOADED = False


def register(cls):
    """Class decorator: instantiate once and record under `meta.key`.

    Returns the class unchanged so it stays independently importable and testable.
    """
    instance = cls()
    key = instance.meta.key
    if key in _REGISTRY:
        raise ValueError(
            f"duplicate source key {key!r} — {cls.__module__} collides with an "
            f"already-registered source"
        )
    _REGISTRY[key] = instance
    return cls


def load_providers() -> None:
    """Import every module under `providers/` so their @register calls run.

    Idempotent: repeated calls are a no-op, so app startup and tests can both
    call it freely.
    """
    global _LOADED
    if _LOADED:
        return
    from app.sources import providers

    for mod in pkgutil.iter_modules(providers.__path__):
        importlib.import_module(f"{providers.__name__}.{mod.name}")
    _LOADED = True


def all_sources() -> list[Source]:
    """Every registered source, sorted by key so the UI order never jitters."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get(key: str) -> Source | None:
    return _REGISTRY.get(key)


def enabled_sources(overrides: dict[str, bool] | None = None) -> list[Source]:
    """Sources to actually run. A user's explicit toggle always beats the default."""
    overrides = overrides or {}
    return [
        s for s in all_sources()
        if overrides.get(s.meta.key, s.meta.enabled_by_default)
    ]


def clear() -> None:
    """Test-only: empty the registry and allow reloading."""
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_registry.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/sources/registry.py backend/app/sources/providers/__init__.py backend/tests/test_registry.py
git commit -m "feat: plugin source registry — add a source by adding one file"
```

---

### Task 5: Store accessors

**Files:**
- Modify: `backend/app/store.py` (append only; the v1 functions are untouched)
- Test: `backend/tests/test_v2_store.py`

**Interfaces:**
- Consumes: `_p`, `_write_atomic`, `_read_text` (existing module-privates),
  `cfg.DATA_DIR`, and the Task 2 models.
- Produces:
  `load_connections() -> dict[str, Connection]`, `save_connection(Connection) -> None`,
  `delete_connection(portal: str) -> None`,
  `load_queue() -> list[QueueItem]`, `upsert_queue_item(QueueItem) -> None`,
  `save_run(ScanRun) -> None`, `load_runs(limit: int = 50) -> list[ScanRun]`,
  `load_source_config() -> dict[str, bool]`, `set_source_enabled(key, enabled) -> None`,
  `load_embeddings() -> dict[str, list[float]]`, `save_embeddings(dict) -> None`,
  `free_disk_gb() -> float`, `assert_disk_headroom() -> None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_v2_store.py`:

```python
import pytest

from app.models import Connection, QueueItem, ScanRun


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Point the store at a scratch dir so tests never touch real user data."""
    from app import config as cfg
    from app import store

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "EVAL_DIR", tmp_path / "evaluations")
    monkeypatch.setattr(cfg, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "evaluations").mkdir()
    (tmp_path / "output").mkdir()
    return store


def test_connections_round_trip(tmp_data):
    store = tmp_data
    assert store.load_connections() == {}
    store.save_connection(Connection(portal="naukri", status="connected"))
    assert store.load_connections()["naukri"].status == "connected"


def test_save_connection_overwrites_the_same_portal(tmp_data):
    store = tmp_data
    store.save_connection(Connection(portal="naukri", status="connected"))
    store.save_connection(Connection(portal="naukri", status="expired", note="cookie gone"))
    conns = store.load_connections()
    assert len(conns) == 1 and conns["naukri"].note == "cookie gone"


def test_delete_connection_removes_it(tmp_data):
    store = tmp_data
    store.save_connection(Connection(portal="naukri", status="connected"))
    store.delete_connection("naukri")
    assert store.load_connections() == {}


def test_delete_unknown_connection_is_a_noop(tmp_data):
    tmp_data.delete_connection("never-existed")   # must not raise


def test_queue_upsert_updates_in_place_and_preserves_order(tmp_data):
    store = tmp_data
    store.upsert_queue_item(QueueItem(job_id="a", score=90))
    store.upsert_queue_item(QueueItem(job_id="b", score=80))
    store.upsert_queue_item(QueueItem(job_id="a", state="submitted", score=90))
    q = store.load_queue()
    assert [i.job_id for i in q] == ["a", "b"]
    assert q[0].state == "submitted"


def test_runs_are_newest_first_and_capped(tmp_data):
    store = tmp_data
    for i in range(205):
        store.save_run(ScanRun(id=f"r{i:03d}", started=f"2026-08-26T{i % 24:02d}:00:00"))
    runs = store.load_runs(limit=500)
    assert len(runs) == 200
    assert runs[0].id == "r204"


def test_source_config_defaults_empty_and_round_trips(tmp_data):
    store = tmp_data
    assert store.load_source_config() == {}
    store.set_source_enabled("linkedin", True)
    store.set_source_enabled("naukri", False)
    assert store.load_source_config() == {"linkedin": True, "naukri": False}


def test_embeddings_round_trip(tmp_data):
    store = tmp_data
    store.save_embeddings({"job1": [0.1, 0.2, 0.3]})
    assert store.load_embeddings()["job1"] == [0.1, 0.2, 0.3]


def test_corrupt_files_read_as_absent_not_as_a_crash(tmp_data, tmp_path):
    store = tmp_data
    (tmp_path / "connections.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "queue.json").write_text("", encoding="utf-8")
    assert store.load_connections() == {}
    assert store.load_queue() == []


def test_free_disk_gb_is_positive(tmp_data):
    assert tmp_data.free_disk_gb() > 0


def test_assert_disk_headroom_raises_when_space_is_low(tmp_data, monkeypatch):
    store = tmp_data
    monkeypatch.setattr(store, "free_disk_gb", lambda: 0.4)
    with pytest.raises(RuntimeError, match="Only 0.4 GB free"):
        store.assert_disk_headroom()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_v2_store.py -v`
Expected: FAIL — `AttributeError: module 'app.store' has no attribute 'load_connections'`.

- [ ] **Step 3: Append to `backend/app/store.py`**

Extend the existing model import line to
`from app.models import Connection, Evaluation, Job, Profile, QueueItem, ScanRun`,
add `import shutil` at the top, then append:

```python
# --- v2 -------------------------------------------------------------------
#
# Same two invariants as v1: writes are atomic, reads tolerate corruption. A
# corrupt cache costs a rescan; a hard 500 on every request costs the product.

MAX_RUNS = 200          # spec §12.4 — bounded history
MIN_FREE_DISK_GB = 2.0  # spec §12.4 — never fill the system disk


def free_disk_gb() -> float:
    return shutil.disk_usage(str(cfg.DATA_DIR)).free / (1024 ** 3)


def assert_disk_headroom() -> None:
    """Refuse to write when the disk is nearly full.

    A skipped scan is recoverable. A full Windows system disk is not.
    """
    free = free_disk_gb()
    if free < MIN_FREE_DISK_GB:
        raise RuntimeError(
            f"Only {free:.1f} GB free on the LaunchPad data disk "
            f"(need {MIN_FREE_DISK_GB:.1f} GB). Free some space and rerun."
        )


def _read_json(name: str, default):
    text = _read_text(_p(name))
    if text is None:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def load_connections() -> dict[str, Connection]:
    """Portal -> Connection. Never contains a credential (spec §6.3)."""
    out: dict[str, Connection] = {}
    for raw in _read_json("connections.json", []):
        try:
            c = Connection(**raw)
        except Exception:
            continue   # one bad record must not hide the rest
        out[c.portal] = c
    return out


def save_connection(conn: Connection) -> None:
    assert_disk_headroom()
    conns = load_connections()
    conns[conn.portal] = conn
    _write_atomic(
        _p("connections.json"),
        json.dumps([c.model_dump() for c in conns.values()], indent=2),
    )


def delete_connection(portal: str) -> None:
    conns = load_connections()
    if conns.pop(portal, None) is None:
        return
    _write_atomic(
        _p("connections.json"),
        json.dumps([c.model_dump() for c in conns.values()], indent=2),
    )


def load_queue() -> list[QueueItem]:
    items = []
    for raw in _read_json("queue.json", []):
        try:
            items.append(QueueItem(**raw))
        except Exception:
            continue
    return items


def upsert_queue_item(item: QueueItem) -> None:
    """Insert or replace by job_id, preserving insertion order."""
    assert_disk_headroom()
    items = load_queue()
    for i, existing in enumerate(items):
        if existing.job_id == item.job_id:
            items[i] = item
            break
    else:
        items.append(item)
    _write_atomic(
        _p("queue.json"), json.dumps([i.model_dump() for i in items], indent=2)
    )


def _runs_path() -> Path:
    d = cfg.DATA_DIR / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "runs.json"


def save_run(run: ScanRun) -> None:
    assert_disk_headroom()
    runs = load_runs(limit=MAX_RUNS)
    runs = [r for r in runs if r.id != run.id]
    runs.insert(0, run)                       # newest first
    del runs[MAX_RUNS:]                       # bounded history
    _write_atomic(_runs_path(), json.dumps([r.model_dump() for r in runs], indent=2))


def load_runs(limit: int = 50) -> list[ScanRun]:
    text = _read_text(_runs_path())
    if text is None:
        return []
    try:
        raw = json.loads(text)
    except Exception:
        return []
    out = []
    for r in raw[:limit]:
        try:
            out.append(ScanRun(**r))
        except Exception:
            continue
    return out


def load_source_config() -> dict[str, bool]:
    """User's explicit per-source on/off overrides. Absent key = use the default."""
    raw = _read_json("sources.json", {})
    return {k: bool(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def set_source_enabled(key: str, enabled: bool) -> None:
    assert_disk_headroom()
    cfgmap = load_source_config()
    cfgmap[key] = bool(enabled)
    _write_atomic(_p("sources.json"), json.dumps(cfgmap, indent=2))


def load_embeddings() -> dict[str, list[float]]:
    raw = _read_json("embeddings.json", {})
    return raw if isinstance(raw, dict) else {}


def save_embeddings(vectors: dict[str, list[float]]) -> None:
    assert_disk_headroom()
    _write_atomic(_p("embeddings.json"), json.dumps(vectors))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_v2_store.py -v`
Expected: 11 passed.

- [ ] **Step 5: Verify v1 store behaviour is untouched**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: all v1 store tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/store.py backend/tests/test_v2_store.py
git commit -m "feat: v2 store accessors (connections, queue, runs, source config, embeddings) + disk floor"
```

---

### Task 6: Routers, and the one and only edit to `api.py`

**Files:**
- Create: `backend/app/routes/__init__.py`, `config.py`, `sources.py`, `connections.py`,
  `schedule.py`, `queue.py`, `events.py`
- Modify: `backend/app/api.py` — **after this task, `api.py` is frozen; no other track may edit it**
- Test: `backend/tests/test_v2_routes.py`

**Interfaces:**
- Consumes: `registry`, `store`, `llm`, `config`, the Task 2 models.
- Produces: six `APIRouter` objects named `router` in their respective modules.
  Track A replaces the body of `routes/config.py`; Track C replaces
  `routes/connections.py`; Track D replaces `schedule.py`, `queue.py`, `events.py`.
  **The route paths and response shapes defined here are the contract Track E's UI
  is built against and must not change.**

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_v2_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_config_still_reports_v1_keys():
    """/config moved to its own router; its response shape must not change."""
    body = client.get("/config").json()
    for key in ("llm_available", "llm_provider", "llm_model", "pdf_available"):
        assert key in body


def test_sources_lists_registered_sources_with_ui_fields():
    body = client.get("/sources").json()
    assert isinstance(body["sources"], list)
    for s in body["sources"]:
        assert {"key", "label", "kind", "regions", "requires_login", "enabled",
                "warning"} <= set(s)


def test_put_unknown_source_is_404():
    """Toggling a source that isn't registered must not silently write config."""
    r = client.put("/sources/does-not-exist", json={"enabled": False})
    assert r.status_code == 404
    assert "unknown source" in r.json()["detail"]


def test_connections_returns_a_list():
    assert isinstance(client.get("/connections").json()["connections"], list)


def test_connection_actions_are_not_implemented_yet():
    """501, not fake success — a stub that lies can ship unnoticed."""
    r = client.post("/connections/naukri/login")
    assert r.status_code == 501
    assert "Track C" in r.json()["detail"]


def test_schedule_read_works_and_write_is_not_implemented():
    body = client.get("/schedule").json()
    assert {"enabled", "interval_minutes", "quiet_hours"} <= set(body)
    assert client.put("/schedule", json={"interval_minutes": 60}).status_code == 501


def test_runs_returns_a_list():
    assert isinstance(client.get("/runs").json()["runs"], list)


def test_queue_read_works_and_actions_are_not_implemented():
    assert isinstance(client.get("/queue").json()["queue"], list)
    assert client.post("/queue/abc/prepare").status_code == 501


def test_v1_routes_are_all_still_mounted():
    paths = {r.path for r in app.routes}
    for p in ("/health", "/profile", "/jobs", "/scan", "/evaluate", "/config",
              "/tailor/{job_id}", "/apply/{job_id}"):
        assert p in paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_v2_routes.py -v`
Expected: FAIL — 404s on `/sources`, `/connections`, `/schedule`, `/queue`.

- [ ] **Step 3: Create the routes package**

```bash
mkdir -p backend/app/routes
printf '"""HTTP routers. One file per concern so parallel tracks never share a file."""\n' > backend/app/routes/__init__.py
```

- [ ] **Step 4: Create `backend/app/routes/config.py`**

Move the handler out of `api.py` verbatim — same path, same response keys:

```python
"""GET /config — what the backend can actually do right now.

Moved out of api.py so Track A can extend the offline-readiness report without
touching a file any other track needs.
"""

import os

from fastapi import APIRouter

from app import config, llm

router = APIRouter()

try:
    from app.tailor import pdf
except OSError:      # WeasyPrint raises OSError, not ImportError, without GTK
    pdf = None


@router.get("/config")
def get_config():
    provider = llm.provider()
    if provider == "api":
        llm_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
    elif provider == "cli":
        llm_available = llm.claude_cli_path() is not None
    else:
        llm_available = llm.ollama_available()
    return {
        "llm_available": llm_available,
        "llm_provider": provider,
        "llm_model": llm.OLLAMA_MODEL if provider == "ollama" else config.LLM_MODEL,
        "pdf_available": pdf is not None,
        "adzuna_available": bool(
            os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY")
        ),
    }
```

- [ ] **Step 5: Create `backend/app/routes/sources.py`** — fully real, no stub

```python
"""GET /sources, PUT /sources/{key} — the registry, as the UI sees it."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.sources import registry

router = APIRouter()


class SourceToggle(BaseModel):
    enabled: bool


@router.get("/sources")
def list_sources():
    overrides = store.load_source_config()
    return {
        "sources": [
            {
                "key": s.meta.key,
                "label": s.meta.label,
                "kind": s.meta.kind.value,
                "regions": list(s.meta.regions),
                "requires_login": s.meta.requires_login,
                "enabled": overrides.get(s.meta.key, s.meta.enabled_by_default),
                "warning": s.meta.warning,
            }
            for s in registry.all_sources()
        ]
    }


@router.put("/sources/{key}")
def toggle_source(key: str, body: SourceToggle):
    if registry.get(key) is None:
        raise HTTPException(status_code=404, detail=f"unknown source {key!r}")
    store.set_source_enabled(key, body.enabled)
    return {"key": key, "enabled": body.enabled}
```

- [ ] **Step 6: Create `backend/app/routes/connections.py`**

```python
"""Login-gated portal connections.

GET is real (it just reads the store). The three action routes return 501 until
Track C lands the session vault — deliberately, so a stub can never masquerade as
a working feature.

BOUNDARY (spec §2): nothing here accepts a username, password or OTP. The user
logs in themselves in a real browser window; we persist only the browser profile.
"""

from fastapi import APIRouter, HTTPException

from app import store
from app.sources import registry
from app.sources.base import SourceKind

router = APIRouter()

_NOT_YET = "Session vault not implemented yet (Track C)."


@router.get("/connections")
def list_connections():
    """Every login-gated source, joined with its stored status."""
    saved = store.load_connections()
    out = []
    for s in registry.all_sources():
        if s.meta.kind is not SourceKind.PORTAL:
            continue
        conn = saved.get(s.meta.key)
        out.append({
            "portal": s.meta.key,
            "label": s.meta.label,
            "login_url": s.meta.login_url,
            "status": conn.status if conn else "disconnected",
            "last_verified": conn.last_verified if conn else None,
            "note": conn.note if conn else "",
            "warning": s.meta.warning,
        })
    return {"connections": out}


@router.post("/connections/{portal}/login")
def start_login(portal: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.post("/connections/{portal}/verify")
def verify(portal: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.delete("/connections/{portal}")
def disconnect(portal: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)
```

- [ ] **Step 7: Create `backend/app/routes/schedule.py`**

```python
"""Autopilot schedule. Reads are real; writes wait for Track D's scheduler."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store

router = APIRouter()

_NOT_YET = "Scheduler not implemented yet (Track D)."

# Defaults from spec §6.4 and §12.2. Track D reads these from persisted settings.
DEFAULT_SCHEDULE = {
    "enabled": False,
    "interval_minutes": 60,
    "quiet_hours": [1, 7],       # [start, end) local hours; GPU rest window
    "require_ac_power": True,    # §12.2 — never run a scan cycle on battery
    "cycle_cap_minutes": 20,     # §12.2 — hard wall-clock cap
}


class ScheduleUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None
    quiet_hours: list[int] | None = None
    require_ac_power: bool | None = None


@router.get("/schedule")
def get_schedule():
    return {**DEFAULT_SCHEDULE, "next_run": None, "last_run": None}


@router.put("/schedule")
def put_schedule(body: ScheduleUpdate):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.post("/schedule/run-now")
def run_now():
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.get("/runs")
def list_runs(limit: int = 50):
    return {"runs": [r.model_dump() for r in store.load_runs(limit=limit)]}
```

- [ ] **Step 8: Create `backend/app/routes/queue.py`**

```python
"""The review queue.

BOUNDARY (spec §2, §6.5): `prepare` opens a filled form and STOPS. There is no
route, and there must never be a route, that submits an application.
"""

from fastapi import APIRouter, HTTPException

from app import store

router = APIRouter()

_NOT_YET = "Apply pipeline not implemented yet (Track D)."


@router.get("/queue")
def get_queue():
    jobs = {j.id: j for j in store.load_jobs()}
    out = []
    for item in store.load_queue():
        job = jobs.get(item.job_id)
        out.append({
            **item.model_dump(),
            "title": job.title if job else "",
            "company": job.company if job else "",
            "url": job.url if job else "",
            "source": job.source if job else "",
        })
    return {"queue": out}


@router.post("/queue/{job_id}/prepare")
def prepare(job_id: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.post("/queue/{job_id}/submitted")
def mark_submitted(job_id: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.post("/queue/{job_id}/skip")
def skip(job_id: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)
```

- [ ] **Step 9: Create `backend/app/routes/events.py`**

```python
"""GET /events — SSE scan progress.

Track 0 ships a heartbeat-only stream so Track E can wire the UI's live indicator
immediately. Track D replaces the generator with real pipeline events.
"""

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


async def _heartbeat():
    while True:
        yield {"event": "heartbeat", "data": json.dumps({"status": "idle"})}
        await asyncio.sleep(15)


@router.get("/events")
async def events():
    return EventSourceResponse(_heartbeat())
```

- [ ] **Step 10: Edit `backend/app/api.py` — the only time**

Add after the existing imports:

```python
from app.routes import (
    config as config_routes,
    connections as connections_routes,
    events as events_routes,
    queue as queue_routes,
    schedule as schedule_routes,
    sources as sources_routes,
)
from app.sources import registry
```

Immediately after the `app.add_middleware(CORSMiddleware, ...)` block, add:

```python
# Import every provider module so its @register runs before the first request.
registry.load_providers()

for _router in (
    config_routes.router, sources_routes.router, connections_routes.router,
    schedule_routes.router, queue_routes.router, events_routes.router,
):
    app.include_router(_router)
```

Then **delete** the inline `@app.get("/config")` handler (currently
`backend/app/api.py:112-131`) — it now lives in `routes/config.py`. Leave every other
v1 route exactly where it is.

**Do NOT remove `llm` from `api.py`'s imports** (controller Ruling R2). After the
handler moves, `llm` may look unused there, but `tests/test_api_flow.py:149-183`
patches `api.llm.claude_cli_path` and `api.llm.ollama_available` to exercise
`/config`. Those patches reach the router because `from app import llm` in both
modules binds the *same* module object — but only while `api.py` still exposes the
name. Keep the import line `from app import config, llm, store` exactly as it is.

- [ ] **Step 11: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_v2_routes.py -v`
Expected: 9 passed.

- [ ] **Step 12: Verify the whole suite is green**

Run: `cd backend && python -m pytest -q`
Expected: all v1 tests still pass alongside the new ones; no errors.

- [ ] **Step 13: Commit**

```bash
git add backend/app/routes backend/app/api.py backend/tests/test_v2_routes.py
git commit -m "feat: six v2 routers; api.py wired once and now frozen"
```

---

### Task 7: Glass design tokens

**Files:**
- Modify: `frontend/app/globals.css` — replace the `:root` and dark-mode blocks,
  extend `@theme inline`
- Test: manual visual check plus `npm run build`

**Interfaces:**
- Produces: the CSS custom properties every Track E component consumes. Track E may
  **append** to this file but must not redefine any token below.

**Contrast rule (spec §5.5):** a frosted panel over a bright aurora cannot guarantee
4.5:1 on its own. Every glass surface therefore carries `--glass-scrim`, a solid
translucent layer painted *under* the text. Never place body text directly on
`--glass-bg` alone.

**ADDITIVE ONLY — do not delete any existing token (controller Ruling R1).**
`frontend/app` and `frontend/components` reference the v1 tokens ~60 times
(`--border` 19×, `--shadow-card` 10×, `--border-strong` 10×, `--accent-wash` 9×, plus
`--surface`, `--surface-2`, `--surface-translucent`, `--shadow-elevated`). CSS custom
properties fail **silently**: deleting them leaves `npm run build` green while every
card loses its background and border. So keep every v1 token *name*, re-value it to
the candy-glass palette, and add the new tokens alongside. The existing UI then picks
up the new look immediately, and Track E migrates the legacy names later.

- [ ] **Step 1: Re-value the `:root` block in `frontend/app/globals.css`**

Keep `@import "tailwindcss";` as line 1. Replace the body of the existing `:root { … }`
block with the following — note every v1 name is still present:

```css
:root {
  /* Aurora mesh — the animated page background */
  --aurora-1: #ff8fd6;
  --aurora-2: #8b7dff;
  --aurora-3: #5ee7ff;
  --aurora-4: #ffe08a;

  --bg: #f7f4ff;
  --foreground: #241b3d;
  --muted: #6c6390;

  /* Glass. --glass-scrim sits UNDER text so contrast never depends on
     whatever the aurora happens to be doing behind the panel. */
  --glass-bg: rgba(255, 255, 255, 0.55);
  --glass-scrim: rgba(255, 255, 255, 0.78);
  --glass-border: rgba(255, 255, 255, 0.72);
  --glass-blur: 20px;
  --glass-shadow: 0 8px 32px rgba(120, 90, 200, 0.18);

  --accent: #7c5cff;
  --accent-strong: #5b3fd6;
  --accent-foreground: #ffffff;
  --accent-wash: rgba(124, 92, 255, 0.12);

  --danger: #d81b60;
  --danger-wash: rgba(216, 27, 96, 0.12);
  --warning: #b26a00;
  --warning-wash: rgba(255, 176, 32, 0.16);
  --success: #0f9d58;
  --success-wash: rgba(15, 157, 88, 0.14);

  --radius-card: 22px;
  --radius-pill: 999px;
  --spring: cubic-bezier(0.22, 1.2, 0.36, 1);

  /* v1 names, re-valued for glass. KEEP THESE — ~60 live references.
     Deleting one fails silently and strips a component's surface. */
  --surface: rgba(255, 255, 255, 0.62);
  --surface-translucent: rgba(255, 255, 255, 0.55);
  --surface-2: rgba(245, 240, 255, 0.72);
  --border: rgba(124, 92, 255, 0.14);
  --border-strong: rgba(124, 92, 255, 0.26);
  --shadow-card: 0 4px 14px rgba(120, 90, 200, 0.10), 0 12px 34px -14px rgba(120, 90, 200, 0.22);
  --shadow-elevated: 0 8px 32px rgba(120, 90, 200, 0.18), 0 30px 60px -20px rgba(120, 90, 200, 0.32);
}
```

- [ ] **Step 2: Add the dark theme, twice**

Two blocks with **identical bodies** and different selectors. Both are required: the
media query serves the default "follow the system" setting, and the attribute selector
lets an explicit in-app toggle win over the system preference. Defining the dark
values in only one of them leaves one of those two paths on the light palette.

```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #120e22;
    --foreground: #f3efff;
    --muted: #a79dcf;
    --glass-bg: rgba(38, 30, 66, 0.55);
    --glass-scrim: rgba(28, 22, 50, 0.82);
    --glass-border: rgba(255, 255, 255, 0.14);
    --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
    --accent: #a58bff;
    --accent-strong: #c0adff;
    --accent-wash: rgba(165, 139, 255, 0.18);
    --danger: #ff7aa8;
    --warning: #ffc457;
    --success: #4ddc9a;
    --surface: rgba(38, 30, 66, 0.62);
    --surface-translucent: rgba(38, 30, 66, 0.55);
    --surface-2: rgba(50, 40, 84, 0.72);
    --border: rgba(255, 255, 255, 0.12);
    --border-strong: rgba(255, 255, 255, 0.22);
    --shadow-card: 0 4px 14px rgba(0, 0, 0, 0.35), 0 12px 34px -14px rgba(0, 0, 0, 0.5);
    --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.45), 0 30px 60px -20px rgba(0, 0, 0, 0.65);
  }
}

:root[data-theme="dark"] {
  --bg: #120e22;
  --foreground: #f3efff;
  --muted: #a79dcf;
  --glass-bg: rgba(38, 30, 66, 0.55);
  --glass-scrim: rgba(28, 22, 50, 0.82);
  --glass-border: rgba(255, 255, 255, 0.14);
  --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
  --accent: #a58bff;
  --accent-strong: #c0adff;
  --accent-wash: rgba(165, 139, 255, 0.18);
  --danger: #ff7aa8;
  --warning: #ffc457;
  --success: #4ddc9a;
  --surface: rgba(38, 30, 66, 0.62);
  --surface-translucent: rgba(38, 30, 66, 0.55);
  --surface-2: rgba(50, 40, 84, 0.72);
  --border: rgba(255, 255, 255, 0.12);
  --border-strong: rgba(255, 255, 255, 0.22);
  --shadow-card: 0 4px 14px rgba(0, 0, 0, 0.35), 0 12px 34px -14px rgba(0, 0, 0, 0.5);
  --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.45), 0 30px 60px -20px rgba(0, 0, 0, 0.65);
}
```

- [ ] **Step 3: Add the reusable glass utility and reduced-motion guard**

Append:

```css
@theme inline {
  --color-bg: var(--bg);
  --color-foreground: var(--foreground);
  --color-muted: var(--muted);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-danger: var(--danger);
  --color-warning: var(--warning);
  --color-success: var(--success);
  --radius-card: var(--radius-card);
}

.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(160%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--glass-shadow);
}

/* Put text on this, never directly on .glass — it guarantees the 4.5:1 floor
   regardless of what the aurora is doing behind the panel. */
.glass-scrim {
  background: var(--glass-scrim);
  border-radius: calc(var(--radius-card) - 6px);
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
```

- [ ] **Step 4: Prove no referenced token was dropped**

A green build proves nothing here — CSS custom properties fail silently. Verify by
set comparison instead: every token the components reference must still be defined.

```bash
cd frontend
grep -rhoE 'var\(--[a-z0-9-]+' --include=*.tsx --include=*.css app components \
  | sed 's/var(//' | sort -u > /tmp/referenced.txt
grep -oE '^\s*--[a-z0-9-]+' app/globals.css | tr -d ' ' | sort -u > /tmp/defined.txt
comm -23 /tmp/referenced.txt /tmp/defined.txt
```
Expected: **no output.** Any line printed is a token a component uses that the
stylesheet no longer defines — add it back before continuing.

Then: `npm run build && npm run lint` — build succeeds, lint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat: vibrant glassmorphism design tokens, both themes, contrast scrim"
```

---

### Task 8: Boundary enforcement test and demo seed

**Files:**
- Create: `backend/tests/test_no_autosubmit.py`
- Create: `scripts/seed-demo-data.ps1`

**Interfaces:**
- Consumes: nothing.
- Produces: a CI-enforced guarantee that no submit-clicking code exists, and a
  one-command way for Track E to get shaped, non-empty API responses.

- [ ] **Step 1: Write the test (it should PASS immediately — it is a guard, not a spec)**

Create `backend/tests/test_no_autosubmit.py`:

```python
"""Boundary enforcement: LaunchPad never submits an application.

Spec §2 and §6.5. The agent prepares an application completely and stops; a human
presses submit. This test exists because a boundary that lives only in a design
document erodes. If this fails, do not weaken the test — remove the code.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# Patterns that would indicate automated submission. Written to catch intent
# (a click aimed at a submit control) rather than every possible `.click()`,
# which has legitimate uses like dismissing a cookie banner.
FORBIDDEN = [
    re.compile(r"""click\(\s*['"][^'"]*submit""", re.I),
    re.compile(r"""click\(\s*['"][^'"]*apply-now""", re.I),
    re.compile(r"""(auto_?submit|submit_application|click_submit|do_apply)""", re.I),
    re.compile(r"""get_by_role\(\s*['"]button['"][^)]*name\s*=\s*['"][^'"]*submit""", re.I),
    re.compile(r"""press\(\s*['"]Enter['"]\s*\)\s*#\s*submit""", re.I),
]


def test_no_submit_automation_anywhere_in_the_backend():
    offenders = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(APP.parent)}:{line}: {match.group(0)!r}")
    assert not offenders, (
        "Automated submission code detected — this violates a hard product "
        "boundary (spec §2). Remove it; do not relax this test.\n  "
        + "\n  ".join(offenders)
    )


def test_no_credential_fields_in_any_model_or_router():
    """No request body anywhere may accept a password or OTP."""
    forbidden = re.compile(
        r"^\s*(password|passwd|otp|pin|security_answer)\s*:", re.I | re.M
    )
    offenders = []
    for path in list(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in forbidden.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(APP.parent)}:{line}")
    assert not offenders, (
        "A credential field was declared — LaunchPad never stores credentials "
        "(spec §2, §6.3).\n  " + "\n  ".join(offenders)
    )
```

- [ ] **Step 2: Run it and confirm it passes on the current tree**

Run: `cd backend && python -m pytest tests/test_no_autosubmit.py -v`
Expected: 2 passed. (If it fails now, something in v1 already violates the boundary —
stop and report before changing anything.)

- [ ] **Step 3: Prove the guard actually catches a violation**

```bash
cd backend && printf 'async def bad(page):\n    await page.click("button[type=submit]")\n' > app/_tmp_violation.py && python -m pytest tests/test_no_autosubmit.py -q; rm app/_tmp_violation.py
```
Expected: FAIL naming `app/_tmp_violation.py:2`. Then, after the `rm`, rerun
`python -m pytest tests/test_no_autosubmit.py -q` and expect 2 passed. A guard never
verified against a real violation is not a guard.

- [ ] **Step 4: Create `scripts/seed-demo-data.ps1`**

```powershell
# Seeds launchpad_data with shaped sample records so Track E can build the UI
# against non-empty, REAL API responses instead of hand-rolled mocks.
# Safe: writes only into launchpad_data (gitignored) and refuses to clobber
# an existing profile.json.
$ErrorActionPreference = "Stop"
$data = Join-Path $PSScriptRoot "..\launchpad_data"
New-Item -ItemType Directory -Force -Path $data | Out-Null

$jobs = @(
  @{ id="demo0001"; source="ats:greenhouse"; company="Databricks"; title="Software Engineer, New Grad";
     location="Bengaluru, IN"; url="https://example.invalid/1"; description="Demo posting.";
     posted="2026-08-25"; region="in"; first_seen="2026-08-26T09:00:00" },
  @{ id="demo0002"; source="naukri"; company="Zalando"; title="Junior Backend Engineer";
     location="Berlin, DE"; url="https://example.invalid/2"; description="Demo posting.";
     posted="2026-08-24"; region="de"; first_seen="2026-08-26T09:00:00" }
)
$queue = @(
  @{ job_id="demo0001"; state="ready";    score=91.0; prepared_at=$null; submitted_at=$null; cv_pdf=$null; notes="" },
  @{ job_id="demo0002"; state="prepared"; score=84.5; prepared_at="2026-08-26T09:05:00"; submitted_at=$null; cv_pdf=$null; notes="Form filled, awaiting your review." }
)
$runs = @(
  @{ id="demorun1"; started="2026-08-26T09:00:00"; finished="2026-08-26T09:04:12"; trigger="scheduled";
     per_source=@{ "ats:greenhouse"=40; "naukri"=12 }; warnings=@("linkedin: disabled by default");
     evaluated=25; tailored=6; partial=$false }
)

$jobsPath = Join-Path $data "jobs.json"
if (Test-Path $jobsPath) { Copy-Item $jobsPath "$jobsPath.bak" -Force }
$jobs  | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $jobsPath
$queue | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $data "queue.json")
New-Item -ItemType Directory -Force -Path (Join-Path $data "runs") | Out-Null
$runs  | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $data "runs\runs.json")

Write-Host "Seeded demo data into $data (previous jobs.json backed up to jobs.json.bak)."
```

- [ ] **Step 5: Run it and verify the API serves the seeded data**

```bash
pwsh scripts/seed-demo-data.ps1
cd backend && python -c "
from fastapi.testclient import TestClient
from app.api import app
c = TestClient(app)
print('queue:', len(c.get('/queue').json()['queue']))
print('runs:',  len(c.get('/runs').json()['runs']))
"
```
Expected: `queue: 2` and `runs: 1`, with company/title populated on the queue rows.

- [ ] **Step 6: Restore the real data**

```bash
cd "c:/Pranav Aditya/JOB PORTAL/launchpad" && mv launchpad_data/jobs.json.bak launchpad_data/jobs.json
```
Expected: the real scanned jobs are back. (`launchpad_data/` is gitignored, so none of
this was ever committable.)

- [ ] **Step 7: Full suite, then commit**

```bash
cd backend && python -m pytest -q
cd .. && git add backend/tests/test_no_autosubmit.py scripts/seed-demo-data.ps1
git commit -m "test: enforce no-autosubmit and no-credential boundaries; add UI demo seed"
```

---

## Track 0 exit criteria

All must hold before any of tracks A–E starts:

1. `cd backend && python -m pytest -q` — green, v1 tests included.
2. `cd frontend && npm run build && npm run lint` — clean.
3. `GET /sources`, `/connections`, `/schedule`, `/runs`, `/queue`, `/config`, `/events`
   all reachable; the six action routes return 501 naming their owning track.
4. `registry.all_sources()` returns `[]` without error (no providers yet — correct).
5. `test_no_autosubmit.py` passes, and was demonstrated to fail against a planted
   violation (Task 8 Step 3).
6. Real `launchpad_data/` still loads: `store.load_jobs()` returns the v1 job count.
7. `api.py` is committed and declared frozen — tracks A–E must not modify it.

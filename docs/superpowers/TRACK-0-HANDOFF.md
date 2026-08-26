# Track 0 handoff — read this before starting Track A–E

**Branch:** `launchpad-v2` · **Spec:** `specs/2026-08-26-launchpad-v2-offline-autopilot-design.md`
**State:** 17 commits, 120 passed / 3 skipped. Frontend build + lint clean.

Track 0 landed the shared contracts. Its whole purpose is that five tracks can now
work in this repo **at the same time without editing the same file**. The rules below
are what preserve that. Breaking one doesn't fail loudly — it fails as a merge
conflict three weeks from now.

## Rules

1. **`backend/app/api.py` is FROZEN.** Do not edit it, for any reason. All route
   surface goes in `backend/app/routes/*.py`, one file per concern. If you believe you
   need to edit `api.py`, you've found a design defect — raise it instead.
2. **Add a job source by adding ONE file** to `backend/app/sources/providers/` with an
   `@register`-decorated class. Never edit `registry.py` or `api.py` to register it.
   `registry.load_providers()` auto-discovers via `pkgutil`.
3. **Source keys must be unique.** `register()` raises `ValueError` naming the colliding
   module. Two tracks picking the same key is the one collision the registry cannot
   prevent — check `GET /sources` before choosing.
4. **File ownership** (spec §9): A `llm.py`/`config.py`/`routes/config.py`/`preflight.ps1`
   · B `providers/ats_*.py`, `public_*.py`, `companies.yml` · C `browser/`,
   `providers/portal_*.py`, `routes/connections.py` · D `scheduler.py`, `pipeline.py`,
   `routes/{schedule,queue,events}.py` · E `frontend/**`.

## The two hard boundaries

Enforced by `backend/tests/test_no_autosubmit.py`, which runs in the normal suite.

1. **No credential storage.** No model, request body, or form may declare a field named
   `password`, `passwd`, `pwd`, `otp`, `one_time_password`, `security_answer`,
   `secret_answer`, or `username`. The user logs into each portal themselves in a real
   browser window; only the resulting browser session is persisted locally.
2. **No autonomous submission.** No code path may click a submit button.

**Do not weaken these tests when one fires.** Remove the offending code instead. Note
their known limits: the credential check is an AST walk over `AnnAssign`/`Assign`/`arg`/
`keyword` nodes, so it misses `self.password = x`, dict literals, and `**kwargs`; the
submit check is a regex tripwire over literal strings, so it misses variable
indirection, `locator(...).click()`, and `form.evaluate(...)`. They are early warnings,
not proofs.

## Contracts you build against

- `sources/base.py` — `SourceKind`, `SourceMeta` (frozen), `FetchContext`, `Source`
  protocol, `SourceUnavailable`. Dependency-free by design; keep it that way.
  The `FetchContext` field is `page_opener`; the method is `open_page(portal)`.
  Track C supplies the opener; until then `open_page` raises `SourceUnavailable`.
- `models.py` — `Connection`, `ScanRun`, `QueueItem`, plus `Job.region` / `Job.first_seen`.
  Every text field coerces loose values rather than rejecting them, because a local 8B
  model is sloppy about types. Follow that pattern for anything new.
- `store.py` — 13 v2 accessors. **`assert_disk_headroom()` is enforced centrally inside
  `_write_atomic()`.** Do not re-add per-call-site invocations; every writer inherits
  the 2 GB floor for free.
- `routes/*.py` — six routers. Eight action routes return **501 naming their owning
  track**. Replace them with real implementations; never with fabricated data.
- `frontend/app/globals.css` — glass tokens, both themes. Every v1 token name survives,
  re-valued. You may append; do not redefine a Track 0 token. Body text goes on
  `.glass-scrim`, never on `.glass` alone (that is what holds 4.5:1 contrast).

## Hardware budgets still unimplemented (spec §12)

Track 0 implemented only the disk floor. These remain, and the machine is an 8 GB-VRAM
laptop, so they are not optional:

- One LLM call at a time — process-wide `asyncio.Semaphore(1)` (Track A)
- 6.5 GB model-size ceiling; `num_ctx` 8192; Ollama `keep_alive: "5m"` (Track A)
- 20-minute cycle cap; `max_instances=1`, `coalesce=True`; skip scheduled scans on
  battery (Track D)
- At most 2 headless Chromium contexts, exactly 1 headed window (Track C)

## Known gaps, in priority order

1. **`clean_registry`'s regression test is self-referential.** The fixture in
   `tests/test_registry.py` is correct — it snapshots and restores. But the test meant
   to guard it inlines a copy of that logic instead of exercising the real fixture, and
   was empirically shown to still pass against the old buggy version. If anyone reverts
   the fixture to clear-only, the suite stays green while `/sources` silently empties
   for every test file sorting after `test_registry.py`. Fix by driving the real fixture
   via `clean_registry.__wrapped__()` and asserting restoration after teardown.
2. `GET /schedule` returns a hardcoded `DEFAULT_SCHEDULE`; Track D must add a persisted
   accessor when it implements `PUT /schedule`.
3. `load_runs()` is a read that mkdirs, via `_runs_path()`. Reads should not create
   directories.
4. Dark theme doesn't remap `--danger-wash` / `--warning-wash` / `--success-wash`.
   Measured contrast is fine (7.1–9.3:1); it is an aesthetic inconsistency only.
5. `/scan` (v1) still calls the old source functions directly and is **not** wired to
   the registry. Track D writes the new orchestration from scratch behind
   `POST /schedule/run-now` — the registry has no live consumer until then.
6. `-Restore` in `scripts/seed-demo-data.ps1` doesn't sweep stray demo files when no
   `.bak` exists.

## Working with the user's real data

`launchpad_data/` is gitignored and holds the user's only copy of ~50 real scraped
postings and their real profile. There is no backup anywhere else.

`scripts/seed-demo-data.ps1` writes demo data for UI work. It backs up `jobs.json`,
**refuses to run twice** without an intervening `-Restore`, and `-Restore` puts the real
file back. Use it; do not hand-roll data-directory writes.

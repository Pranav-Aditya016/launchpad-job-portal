# LaunchPad v2 — Offline Autopilot

**Date:** 2026-08-26
**Status:** Design — awaiting user review
**Extends:** `2026-08-10-launchpad-job-portal-design.md` (v1, shipped)
**Branch:** `launchpad-v2` off `master` (`c319901`)

---

## 1. Goal

Turn LaunchPad from a manual, API-key-dependent job scanner into a **fully offline
autopilot**: it scans dozens of job sources every hour (including ones that require
the user's own login), scores every posting against the user's resume with a local
model, tailors a CV and cover letter for the good ones, and stacks fully-prepared
applications in a review queue for the user to submit with one click.

No network calls to any LLM provider. No API keys required to run the product.

## 2. Constraints

**Hardware (measured, 2026-08-26):** RTX 4060 Laptop, **8 GB VRAM**; 15.2 GB system
RAM; Ryzen 9 8945HS (8 cores). Ollama installed, `qwen3:8b` (5.2 GB Q4_K_M) pulled.

This is the single most design-shaping fact in this document. It means:

- The largest model we can hold entirely in VRAM is ~8B at Q4. `gemma4:e4b` (9.6 GB)
  already exceeds VRAM and will spill to system RAM.
- One `qwen3:8b` evaluation of a full job description takes on the order of
  **10–30 s**. Budget accordingly: an hourly cycle can afford roughly **25–40 LLM
  evaluations**, not thousands.
- **An 8B model cannot reliably drive a browser.** browser-use's own benchmarks show
  small open-weight models falling off sharply against hosted ones. Therefore the LLM
  is kept out of the navigation loop entirely on the hot path (§4.1).

**Legal / account-safety boundaries** — carried forward from v1, reaffirmed by the
user on 2026-08-26 and **not up for reversal**:

1. **No credential storage, no authentication bypass.** LaunchPad never stores a
   portal password and never automates a login form. The user logs in themselves, in
   a real visible browser window. LaunchPad persists only the resulting *browser
   session*, on the local disk, for the user's own account.
2. **No autonomous submission.** The agent prepares an application completely —
   opens the real page, fills the fields, attaches the tailored PDF — and then stops.
   A human presses submit. There is no code path that clicks a submit button.

**Offline:** after a one-time setup (dependency install, `ollama pull`, Playwright
browser download), every *evaluation, tailoring and document-generation* call runs
locally. Job scraping obviously still uses the network — that is the product.

## 3. What already exists (v1, do not rebuild)

| Capability | Location |
|---|---|
| FastAPI app, 12 routes, global exception handler | `backend/app/api.py` |
| Atomic + corruption-tolerant file store | `backend/app/store.py` |
| Coercing pydantic models (`Profile`/`Job`/`Evaluation`/`TailoredDoc`) | `backend/app/models.py` |
| LLM call site with `api` / `cli` / `ollama` providers | `backend/app/llm.py` |
| 6 public aggregators, concurrent, per-source non-fatal | `backend/app/sources/aggregators.py` |
| career-ops ATS sweep via Node subprocess | `backend/app/sources/careerops_scan.py` |
| crawl4ai adapter for curated pages | `backend/app/sources/crawl_adapter.py` |
| Fresher/experience filter | `backend/app/sources/experience.py` |
| Visa / sponsorship signal | `backend/app/sources/visa.py` |
| A–G evaluation rubric | `backend/app/evaluate/` |
| CV + cover-letter writer, WeasyPrint PDF | `backend/app/tailor/` |
| Resume ingest (markitdown) | `backend/app/ingest/resume.py` |
| Next.js 16 / React 19 / Tailwind 4 / motion frontend | `frontend/` |
| 45 passing tests | `backend/tests/` |

v2 **adds to** this. The `Job`, `Profile`, `Evaluation`, `TailoredDoc` models and the
`store.py` write/read invariants are unchanged.

---

## 4. Architecture

```
                   +--------------------- Next.js UI (glass) ----------------------+
                   | Dashboard · Connections · Sources · Queue · Job · Settings    |
                   +-------------------------------+------------------------------+
                                                   | REST + SSE
                   +-------------------------------+------------------------------+
                   |                    FastAPI (single process)                   |
                   |  routes/ scan · connections · sources · schedule · queue      |
                   +----+--------------+--------------+--------------+-------------+
                        |              |              |              |
              +---------+------+ +-----+--------+ +---+--------+ +---+-----------+
              | Source registry| | Session vault| | Scheduler  | | Pipeline      |
              |   (4 tiers)    | | (Playwright  | | APScheduler| | prefilter ->  |
              |                | |  profiles)   | |  hourly    | | eval -> tailor|
              +--------+-------+ +------+-------+ +------------+ +------+--------+
                       |                |                              |
        +--------------+-----+----------+---------+             +------+------+
        |          |         |                    |             |   Ollama    |
     Tier 1     Tier 2    Tier 3              Tier 4            | qwen3:8b +  |
     public     ATS       logged-in           agentic fallback  | embeddings  |
     APIs       adapters  portals             (browser-use)     +-------------+
```

### 4.1 Why the LLM is not in the browser loop

Tiers 1–3 are **deterministic**: HTTP + JSON, or Playwright + CSS selectors. They are
fast (seconds), reliable, and cost zero tokens. Tier 4 (browser-use driving a real
browser with `qwen3:8b`) exists **only as a repair path**: it fires when a tier-2/3
adapter returns zero results, and its job is to find the listings *and emit a
suggested selector patch* into `launchpad_data/adapter_repairs/`. It is opt-in
(`LAUNCHPAD_AGENTIC_FALLBACK=1`), capped at one site per cycle, and never blocks a
scan.

This is the resolution of "best agentic scraper" vs "fully offline": we install the
best one (browser-use, MIT, ~110k stars) and use it where a small local model can
actually succeed — a single bounded page — rather than as the engine of the whole
system.

### 4.2 The throughput budget

A cycle across ~40 sources can surface thousands of postings. At 10–30 s per local
evaluation that is impossible to LLM-score exhaustively. The pipeline is therefore a
**funnel**, and only the last stage is expensive:

1. **Dedupe** — content hash, then embedding near-duplicate collapse (§5.3).
2. **Hard filters** — experience level, location/work-auth, must-not keywords. Free.
3. **Embedding pre-rank** — cosine similarity of posting vs. resume, via
   `nomic-embed-text` on Ollama (~50 ms each). Cheap, runs on everything.
4. **LLM evaluation** — the A–G rubric, on the **top N only** (`EVAL_BUDGET`,
   default 25).
5. **Tailoring** — CV + cover letter, only for jobs scoring at or above
   `TAILOR_THRESHOLD` (default 75).

Everything below the cut is still stored and browsable, just unscored, and gets
picked up in a later cycle if it stays near the top.

---

## 5. Frozen contracts

**These are written once, by the integrator, before any track starts. No track may
change them unilaterally.** They exist so parallel work cannot collide.

### 5.1 Source protocol — `backend/app/sources/base.py` (new)

```python
class SourceKind(str, Enum):
    PUBLIC = "public"      # tier 1 — open HTTP/JSON
    ATS    = "ats"         # tier 2 — company career sites on a known ATS
    PORTAL = "portal"      # tier 3 — requires the user's own login session
    CRAWL  = "crawl"       # curated page scrape

@dataclass(frozen=True)
class SourceMeta:
    key: str                      # stable id, e.g. "naukri", "ats:greenhouse"
    label: str                    # UI display name
    kind: SourceKind
    regions: tuple[str, ...]      # ("in",), ("de",), ("global",)
    requires_login: bool = False
    login_url: str = ""           # tier 3 only: where the user logs in
    logged_in_probe: str = ""     # tier 3 only: URL only reachable when logged in
    logged_in_selector: str = ""  # tier 3 only: CSS proving the session is live
    rate_limit_s: float = 2.0     # min delay between requests to this host
    daily_cap: int = 500          # max postings pulled per 24h
    enabled_by_default: bool = True

class Source(Protocol):
    meta: SourceMeta
    async def fetch(self, ctx: "FetchContext") -> list[Job]: ...
```

`FetchContext` carries the `Profile`, the search queries, a shared
`httpx.AsyncClient`, and — for `PORTAL` sources — an awaitable `playwright_page()`
factory bound to that portal's persistent profile.

**Registration is by decorator, not by editing a shared file:**

```python
@register            # backend/app/sources/registry.py
class Naukri:
    meta = SourceMeta(key="naukri", ...)
```

`registry.py` exposes `all_sources()`, `get(key)`, `enabled_sources(config)`. It
imports every module in `app/sources/providers/` at startup. **A track adds a source
by creating one new file. It never edits `api.py` or `registry.py`.**

### 5.2 New models — appended to `backend/app/models.py`

```python
class Connection(BaseModel):        # one logged-in portal
    portal: str
    status: Literal["disconnected", "connected", "expired", "checking", "blocked"]
    last_verified: str | None = None   # ISO-8601
    note: str = ""                     # human-readable last error

class ScanRun(BaseModel):
    id: str
    started: str
    finished: str | None = None
    trigger: Literal["manual", "scheduled"]
    per_source: dict[str, int]          # source key -> new jobs
    warnings: list[str]
    evaluated: int = 0
    tailored: int = 0

class QueueItem(BaseModel):
    job_id: str
    state: Literal["ready", "prepared", "submitted", "skipped"]
    score: float
    prepared_at: str | None = None
    submitted_at: str | None = None
    cv_pdf: str | None = None           # path under launchpad_data/output
    notes: str = ""
```

`Job` gains two optional fields (backward compatible; defaults preserve v1 data):
`region: str = ""` and `first_seen: str | None = None`.

### 5.3 Storage layout — `launchpad_data/`

```
profile.json  jobs.json  applied_log.json      # v1, unchanged
evaluations/<job_id>.json                      # v1, unchanged
output/                                        # v1, unchanged
embeddings.json          # job_id -> vector, for dedupe + pre-rank
connections.json         # list[Connection] — status only, NEVER credentials
sessions/<portal>/       # Playwright user_data_dir. gitignored. never committed.
queue.json               # list[QueueItem]
runs/<run_id>.json       # ScanRun records, last 200 kept
sources.json             # per-source enabled flag + user overrides
adapter_repairs/<key>.md # tier-4 fallback output for a human to review
```

`sessions/` and `embeddings.json` are added to `.gitignore` in Track 0.

### 5.4 API surface — new routers, one file each

| Router file | Routes |
|---|---|
| `routes/connections.py` | `GET /connections`, `POST /connections/{portal}/login`, `POST /connections/{portal}/verify`, `DELETE /connections/{portal}` |
| `routes/sources.py` | `GET /sources`, `PUT /sources/{key}` (enable/disable) |
| `routes/schedule.py` | `GET /schedule`, `PUT /schedule`, `POST /schedule/run-now`, `GET /runs` |
| `routes/queue.py` | `GET /queue`, `POST /queue/{job_id}/prepare`, `POST /queue/{job_id}/submitted`, `POST /queue/{job_id}/skip` |
| `routes/events.py` | `GET /events` — SSE stream of scan progress |
| `routes/config.py` | `GET /config` — **moved out of `api.py`** so Track A can extend the readiness report without touching a shared file |

`api.py` is edited **once, in Track 0**, to `include_router` all six and to delete the
inline `/config` handler. After Track 0, `api.py` is frozen: **no track may edit it.**
The other v1 routes stay exactly where they are.

### 5.5 Design tokens — `frontend/app/globals.css`

Written in Track 0 so every UI surface builds against the same variables. Direction:
**vibrant candy glassmorphism** — aurora mesh gradient background, frosted translucent
surfaces, bright saturated accents, generous rounding, spring motion.

```css
--aurora-1:#ff8fd6  --aurora-2:#8b7dff  --aurora-3:#5ee7ff  --aurora-4:#ffe08a
--glass-bg:rgba(255,255,255,.55)   --glass-border:rgba(255,255,255,.72)
--glass-blur:20px                  --glass-shadow:0 8px 32px rgba(120,90,200,.18)
--radius-card:22px                 --radius-pill:999px
--spring:cubic-bezier(.22,1.2,.36,1)
```

Dark mode redefines the glass tokens over a deep indigo ground. Both themes are
defined at Track 0; no track invents its own colors.

**Accessibility is not optional:** glass surfaces must keep at least 4.5:1 text
contrast against the *blurred* backdrop — enforced with a solid scrim behind text,
not by hoping — and every animation respects `prefers-reduced-motion`.

---

## 6. Components

### 6.1 Offline core (Track A)

- `llm.provider()` already defaults to `ollama` with no key and no CLI; v2 makes that
  the documented default and makes `/config` report it clearly.
- `embed(texts) -> list[vector]` added to `llm.py`, backed by Ollama
  `/api/embeddings` with `nomic-embed-text`. Cached in `embeddings.json`.
- `scripts/preflight.ps1`: checks Ollama is up, pulls `qwen3:8b` and
  `nomic-embed-text` if absent, downloads Playwright Chromium, warns on
  GTK/WeasyPrint.
- `GET /config` reports provider, model, VRAM fit, which models are present, and
  whether Playwright browsers are installed. Settings renders this as a checklist.
- **Anthropic dependency becomes optional** (`pyproject` extra `hosted`), so a clean
  install pulls no cloud SDK at all.

### 6.2 Source registry and adapters (Tracks B, C)

**Tier 2 — ATS adapters** (`app/sources/providers/ats_*.py`), one per platform:
Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, iCIMS, SuccessFactors.
Each takes a company slug and returns `list[Job]`. Backed by
`app/sources/companies.yml`:

```yaml
- name: IBM          ats: workday     slug: ibm        regions: [in, de, global]
- name: Databricks   ats: greenhouse  slug: databricks regions: [global]
- name: Zalando      ats: greenhouse  slug: zalando    regions: [de]
```

Adding a company is one line. Market-share research shows Greenhouse, Workday, Lever,
iCIMS and Ashby cover the large majority of tracked employers, so ~8 adapters reach
thousands of career sites. The registry ships seeded with Indian IT and product
companies, German engineering and tech, and global tech employers.

**Tier 1 — public sources** (`providers/public_*.py`): the six existing aggregators
move behind the `Source` protocol unchanged, joined by arbeitsagentur (the official
German federal board, ~800k vacancies) and the curated crawl targets.

**Tier 3 — logged-in portals** (`providers/portal_*.py`): Naukri, Internshala,
Instahyre, Cutshort, Superset, Freshersworld, LinkedIn, Glassdoor, StepStone, Xing,
Wellfound, TrueUp. Each declares `login_url` / `logged_in_probe` /
`logged_in_selector` and scrapes via the shared persistent Playwright profile.

**LinkedIn is explicitly best-effort.** It has the most aggressive anti-automation of
any target here. Its adapter runs at human pace (`rate_limit_s: 8`, `daily_cap: 60`),
is **disabled by default**, and its UI card carries a plain-language warning that
heavy use can get an account restricted. We do not evade detection; if LinkedIn
blocks us, the adapter reports `blocked` and stops.

### 6.3 Session vault (Track C)

`app/browser/session.py`:

- `user_data_dir = DATA_DIR / "sessions" / portal`, one per portal.
- `POST /connections/{portal}/login` launches a **headed** Chromium at `login_url`
  and returns immediately; the user logs in by hand (password, OTP, CAPTCHA — all
  theirs). A background watcher polls for `logged_in_selector`, then marks the
  connection `connected` and closes the window.
- `POST /connections/{portal}/verify` opens the profile headless, hits
  `logged_in_probe`, checks the selector, updates status. Runs before every scheduled
  scan; an `expired` portal is skipped with a warning, never a crash.
- `DELETE /connections/{portal}` deletes the profile directory. That is a real logout.
- **Never written:** username, password, OTP, security answers. There is no field for
  them in any model, request body, or form in this system.

### 6.4 Scheduler and pipeline (Track D)

- APScheduler `AsyncIOScheduler` started in the FastAPI lifespan. One cron job,
  default `every 1 hour`, with configurable interval and quiet hours via
  `PUT /schedule`. `jitter=300` so requests don't arrive on a robotic tick.
- Each run: verify connections, fan out enabled sources with a per-host semaphore
  honouring `rate_limit_s`, upsert jobs, run the funnel (§4.2), write a `ScanRun`,
  emit SSE events.
- **Per-source failure is non-fatal** (v1 invariant, preserved): a dead portal
  produces a warning in the run record, never a failed cycle.
- Missed runs coalesce (`max_instances=1`, `coalesce=True`), so closing the laptop for
  six hours produces one catch-up scan, not six.

### 6.5 Review queue and assisted apply (Track D)

- Jobs at or above the threshold enter `queue.json` as `ready`.
- `POST /queue/{job_id}/prepare` generates the tailored CV and cover-letter PDF, opens
  the real application page in a headed browser using the portal session, and
  best-effort fills name/email/phone/resume-upload. **It then stops with the form on
  screen.**
- The user reviews, edits, and clicks submit themselves, then hits "Mark submitted" in
  the UI (`POST /queue/{job_id}/submitted`), which writes to the existing
  `applied_log.json`.
- There is no submit-clicking code. This is a design invariant, enforced by a test.

### 6.6 UI (Track E)

Pages: **Dashboard** (live scan status, funnel stats, top matches), **Connections**
(one glass card per portal — connect / verify / disconnect, status dot),
**Sources** (registry browser, per-source toggle, region filter, company search),
**Queue** (prepared applications; prepare / submit / skip), **Job detail** (v1,
restyled, plus score breakdown), **Profile**, **Settings** (offline-readiness
checklist from `/config`, schedule controls).

Motion via the already-installed `motion` package: spring page transitions, staggered
card entrance, animated score dials, and a live aurora background that shifts while a
scan is running. All gated on `prefers-reduced-motion`.

---

## 7. Error handling

Preserves and extends v1's rules:

- Every source failure is caught per-source and surfaced as a warning on the
  `ScanRun`. A scan where 39 of 40 sources fail still returns the 40th's jobs.
- Every LLM call may fail (model not pulled, Ollama down). `/evaluate` and `/tailor`
  map that to a **400 with an actionable message** ("run `ollama pull qwen3:8b`"),
  never a 500.
- Every write goes through `store._write_atomic`; every read tolerates corruption.
- Playwright failures (browser missing, profile locked, portal redesign) degrade the
  affected portal to `expired` or `blocked` and leave the rest of the system running.
- The global exception handler in `api.py` stays — no unhandled 500 without CORS
  headers.

## 8. Testing

- Every adapter gets a **fixture test** against a captured response in
  `tests/fixtures/` — no network in the default suite.
- `tests/test_no_autosubmit.py`: greps the backend for submit-click patterns and fails
  if any appear. The boundary is enforced by the suite, not by memory.
- `tests/test_registry.py`: every registered source has a unique key, valid meta, and
  a `fetch` returning `list[Job]` against its fixture.
- Session vault tested against a local fixture server, never a real portal.
- Live portal tests stay opt-in behind `RUN_INTEGRATION=1` (v1 pattern).
- Frontend: `npm run build` and `npm run lint` clean; contrast checked on glass.

## 9. Parallel execution plan

Track 0 (integrator, first, alone) writes every frozen contract in §5: `base.py`,
`registry.py`, model additions, routers wired into `api.py` returning stub data,
`globals.css` tokens, `.gitignore`, fixture scaffold. **Nothing else starts until
Track 0 lands.**

Then five tracks run in parallel with **strict file ownership** — no two tracks write
the same file:

| Track | Owns | Depends on |
|---|---|---|
| **A · Offline core** | `llm.py`, `config.py`, `routes/config.py`, `scripts/preflight.ps1`, `pyproject.toml` | Track 0 |
| **B · ATS + public** | `sources/providers/ats_*.py`, `public_*.py`, `companies.yml` | Track 0 |
| **C · Connections** | `browser/`, `providers/portal_*.py`, `routes/connections.py` | Track 0 |
| **D · Autopilot** | `scheduler.py`, `pipeline.py`, `routes/schedule.py`, `routes/queue.py`, `routes/events.py` | Track 0, §5.1 |
| **E · Glass UI** | all of `frontend/**`. May **append** to `globals.css` but must not redefine any Track 0 token | Track 0 |

Track E builds against the API contract in §5.4, which exists as stubs from Track 0 —
so the UI never waits on B, C or D.

The integrator merges, resolves, runs the full suite, and does live end-to-end
verification.

## 10. Deferred (explicitly not v2)

Auto-submission of any kind. Credential vaults. CAPTCHA solving. Proxy rotation or any
anti-detection technique. Multi-user support. Cloud sync. Mobile app. Fine-tuning a
local model. Email/WhatsApp notifications (a v3 candidate once the queue is proven).

## 11. Success criteria

1. `ANTHROPIC_API_KEY` unset and network blocked to api.anthropic.com: resume upload,
   evaluation and tailoring all still work end-to-end.
2. At least 25 sources registered and returning real jobs from a live scan.
3. At least 3 login-gated portals connect via the Connections page and return jobs the
   public tiers do not.
4. The scheduler runs unattended for 6 hours, producing hourly `ScanRun` records with
   no unhandled exception.
5. A queue item can be prepared, reviewed and marked submitted; `applied_log.json`
   updates.
6. `npm run build` and `npm run lint` clean; the full pytest suite green.
7. `test_no_autosubmit.py` passes.
8. A 6-hour unattended run stays inside every §12 budget: no VRAM OOM, no cycle
   overlap, no unbounded disk growth.

---

## 12. Hardware safety

This product runs inference on a **laptop** GPU on a schedule, potentially for weeks.
That is a different risk profile from a one-off script, and it is designed for
explicitly. Nothing here is optional or best-effort.

**Nothing in this project ever touches hardware settings.** No clock, power-limit, fan
curve, voltage or driver modification, and no tool that performs one is installed.
Every safeguard below works by *asking for less*, never by tuning the machine.

### 12.1 VRAM — hard ceilings

The 4060 Laptop has 8 GB. Exceeding it does not crash cleanly; it thrashes into system
RAM and turns a 20-second call into a multi-minute one while pinning the GPU.

- **One LLM call at a time.** A process-wide `asyncio.Semaphore(1)` wraps every
  `complete_json`. Concurrent local inference on 8 GB is the fastest route to OOM, and
  batching buys nothing when a single call already saturates the card.
- **Model size guard.** Preflight refuses to select any model whose file exceeds
  **6.5 GB**, with a clear message naming the offender. `gemma4:e4b` (9.6 GB) is
  already on this machine and is explicitly rejected rather than silently thrashed.
  `qwen3:8b` (5.2 GB) plus 8k context fits with headroom.
- **`num_ctx` stays at 8192.** Job descriptions are truncated to fit rather than
  raising the window, because context is the term that grows VRAM fastest.
- **The model unloads between cycles.** Ollama calls pass `keep_alive: "5m"`, so the
  GPU is free ~55 minutes of every hour instead of holding 5.2 GB pinned around the
  clock. This is the single biggest change to sustained thermal load.
- **OOM is terminal, not retried.** A CUDA OOM or Ollama 500 marks the cycle degraded
  and stops. Retry loops on an OOMing GPU are what actually cook a laptop; we fail
  loudly and let the next hour try fresh.

### 12.2 Thermals and duty cycle

- **Cycle wall-clock cap:** 20 minutes default. On expiry the run is cut short, marked
  `partial`, and the remaining sources roll to the next cycle. Cycles can therefore
  never overlap or stack up (`max_instances=1`, `coalesce=True`).
- **AC-power gate:** on battery, scheduled scans are **skipped** (checked via
  `Win32_Battery`). Sustained GPU inference is the worst thing you can do to a laptop
  battery's health and to unplugged thermals. Manual "Scan now" still works on
  battery — the user's explicit choice is always honoured.
- **Quiet hours default to 01:00–07:00**, off by default in code but pre-filled in the
  UI, so the machine gets a nightly rest window without the user thinking about it.
- The scan is **I/O-bound, not GPU-bound**, by design: at most 25 LLM calls per hour
  out of a 20-minute window. Measured duty cycle is well under 20%.

### 12.3 Browser processes

- At most **2 concurrent headless Chromium contexts**, and exactly **1 headed window**
  (a login or an apply-prepare), enforced by semaphore. Chromium is the real RAM
  consumer here — 15 GB total with a model resident leaves no room for a dozen tabs.
- Every context is opened in a `try/finally` that closes it, and each scan cycle ends
  with a sweep that kills any Playwright process it started and orphaned.
- Stale profile locks (from a hard shutdown) are detected and cleared on next launch
  rather than hanging the portal forever.

### 12.4 Disk

- `runs/` capped at the last 200 records; `output/` PDFs pruned beyond 500 files;
  `embeddings.json` capped at 20k vectors (LRU by `first_seen`).
- **All writes abort if free disk is under 2 GB**, with a clear surfaced warning. A
  full system disk on Windows is far more damaging than a skipped scan.
- `sessions/` and `embeddings.json` are gitignored so browser profiles and vectors can
  never be committed.

### 12.5 Network courtesy

Per-host `rate_limit_s` and `daily_cap` are enforced by the scheduler, not left to
each adapter. This protects the user's accounts and IP as much as it protects the
target sites — hammering Naukri from a home connection is how a residential IP gets
rate-limited for everyone in the house.

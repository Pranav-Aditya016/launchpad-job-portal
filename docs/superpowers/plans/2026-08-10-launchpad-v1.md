# LaunchPad v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally-run, Apple-designed job portal where the user uploads a resume once and gets many public jobs discovered, scored by reasoned fit (with scam and no-sponsorship flags), tailored into a CV + cover letter, and offered a one-click assisted-apply.

**Architecture:** Next.js (React + Tailwind) frontend calls a FastAPI backend over REST. The backend orchestrates: resume ingestion (markitdown + Claude), job discovery (career-ops `scan-ats-full.mjs`, zero-LLM, + a crawl4ai adapter), evaluation (Claude driven by career-ops' rubric prompts), and tailoring (Claude + WeasyPrint HTML→PDF). State is file-based per single local user.

**Tech Stack:** Python 3.11 / FastAPI / uvicorn / httpx / pydantic / pytest; markitdown; crawl4ai; WeasyPrint; anthropic SDK. Node ≥18 for the vendored `santifer/career-ops` engine (Playwright). Next.js 14 (app router) / TypeScript / TailwindCSS / apple-design skill.

## Global Constraints

- **No authentication bypass** and **no autonomous submission** anywhere in the code. Assisted-apply opens the real apply URL in a new tab; the backend never POSTs an application. (verbatim boundary from spec §2)
- **Public sources only** in v1. No login-gated scraping.
- **Single local user.** File-based state under `launchpad_data/`. No accounts, no cloud DB. (spec §10)
- **Python** `>=3.11`; **Node** `>=18`.
- All LLM calls use model id **`claude-opus-4-6`** for reasoning/tailoring unless a task says otherwise; keep the id in one config constant (`backend/app/config.py: LLM_MODEL`), never inline.
- Every backend module is small and single-purpose (spec §4). Backend package layout is fixed in File Structure below; do not merge modules.
- career-ops is **vendored, not modified.** Treat it as an external engine behind a subprocess boundary; never edit files under `engine/career-ops/`.
- Money/tokens: discovery must stay zero-LLM (use `scan-ats-full.mjs`); LLM spend happens only in evaluation and tailoring.

---

## File Structure

```
launchpad/
├── docs/superpowers/{specs,plans}/…            # spec + this plan
├── engine/career-ops/                          # vendored santifer/career-ops (git clone, npm install)
├── backend/
│   ├── pyproject.toml                           # deps + pytest config
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                            # paths, LLM_MODEL, data dirs
│   │   ├── models.py                            # pydantic: Profile, Job, Evaluation, TailoredDoc
│   │   ├── llm.py                               # thin Claude client wrapper (one call site)
│   │   ├── store.py                             # file-based persistence under launchpad_data/
│   │   ├── ingest/resume.py                     # markitdown + Claude → Profile
│   │   ├── sources/careerops_scan.py            # subprocess wrapper over scan-ats-full.mjs
│   │   ├── sources/crawl_adapter.py             # crawl4ai → Job[] from a public listing URL
│   │   ├── sources/portals.py                   # write portals.yml from Profile targets
│   │   ├── evaluate/rubric.py                   # load career-ops rubric prompt text
│   │   ├── evaluate/evaluator.py                # Claude eval → Evaluation (score, flags)
│   │   ├── tailor/writer.py                     # Claude → tailored CV md + cover letter
│   │   ├── tailor/pdf.py                         # WeasyPrint HTML→PDF (Apple-styled)
│   │   └── api.py                               # FastAPI app + routes
│   └── tests/
│       ├── fixtures/                            # saved HTML/JSON/resume fixtures
│       └── test_*.py
├── frontend/                                    # Next.js app (created via create-next-app)
│   ├── app/(pages)…                             # upload, dashboard, job/[id]
│   ├── components/…                             # Apple-design components
│   └── lib/api.ts                               # typed fetch client
└── launchpad_data/                             # gitignored runtime state (profile, jobs, reports, pdfs)
```

**Data model of record** (`launchpad_data/`): `profile.json`, `jobs.json` (discovered+deduped), `evaluations/{job_id}.json`, `output/{job_id}.pdf`, `applied_log.json`.

---

## Task 0: Repo scaffolding + backend skeleton

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/api.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: FastAPI `app` in `backend/app/api.py`; `GET /health` → `{"status":"ok"}`. Config constants `DATA_DIR: Path`, `LLM_MODEL: str`, `ENGINE_DIR: Path` in `backend/app/config.py`.

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "launchpad-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110", "uvicorn[standard]>=0.29", "httpx>=0.27",
  "pydantic>=2.6", "python-multipart>=0.0.9",
  "anthropic>=0.39", "markitdown>=0.0.1a2", "weasyprint>=61",
  "crawl4ai>=0.4",
]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write `backend/app/config.py`**

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "launchpad_data"
ENGINE_DIR = REPO_ROOT / "engine" / "career-ops"
OUTPUT_DIR = DATA_DIR / "output"
EVAL_DIR = DATA_DIR / "evaluations"
LLM_MODEL = "claude-opus-4-6"

for d in (DATA_DIR, OUTPUT_DIR, EVAL_DIR):
    d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Write the failing test `backend/tests/test_health.py`**

```python
from fastapi.testclient import TestClient
from app.api import app

def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 4: Run it, expect failure**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: FAIL (`ModuleNotFoundError: app.api`).

- [ ] **Step 5: Write minimal `backend/app/api.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LaunchPad")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Install + run test, expect pass**

Run: `cd backend && pip install -e ".[dev]" && python -m pytest tests/test_health.py -v`
Expected: PASS. (If WeasyPrint's native libs are missing on Windows, note it and continue — only Task 9 needs them.)

- [ ] **Step 7: Commit**

```bash
git add backend && git commit -m "feat: backend skeleton with health endpoint"
```

---

## Task 1: Data models

**Files:**
- Create: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces pydantic models used everywhere downstream:
  - `Profile(name:str, email:str, location:str, work_auth:str, target_roles:list[str], skills:list[str], proof_points:list[str], resume_text:str)`
  - `Job(id:str, source:str, company:str, title:str, location:str, url:str, description:str, posted:str|None)`
  - `Evaluation(job_id:str, score:float, summary:str, cv_match:str, scam_flag:bool, scam_reason:str, no_sponsorship:bool, strengths:list[str], gaps:list[str])`
  - `TailoredDoc(job_id:str, cv_markdown:str, cover_letter:str)`
  - `job_id(source, company, url) -> str` (stable 16-char sha256)

- [ ] **Step 1: Write failing test `backend/tests/test_models.py`**

```python
from app.models import Job, job_id, Evaluation

def test_job_id_stable():
    a = job_id("greenhouse", "stripe", "https://x/y")
    b = job_id("greenhouse", "stripe", "https://x/y")
    assert a == b and len(a) == 16

def test_evaluation_defaults():
    e = Evaluation(job_id="j1", score=4.2, summary="s", cv_match="m")
    assert e.scam_flag is False and e.no_sponsorship is False
```

- [ ] **Step 2: Run, expect fail.** `cd backend && python -m pytest tests/test_models.py -v` → FAIL.

- [ ] **Step 3: Implement `backend/app/models.py`**

```python
import hashlib
from pydantic import BaseModel, Field

def job_id(source: str, company: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{company}:{url}".encode()).hexdigest()[:16]

class Profile(BaseModel):
    name: str = ""; email: str = ""; location: str = ""
    work_auth: str = ""
    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    resume_text: str = ""

class Job(BaseModel):
    id: str; source: str; company: str; title: str
    location: str = ""; url: str; description: str = ""; posted: str | None = None

class Evaluation(BaseModel):
    job_id: str; score: float; summary: str; cv_match: str
    scam_flag: bool = False; scam_reason: str = ""
    no_sponsorship: bool = False
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

class TailoredDoc(BaseModel):
    job_id: str; cv_markdown: str; cover_letter: str
```

- [ ] **Step 4: Run, expect pass.** Same command → PASS.
- [ ] **Step 5: Commit.** `git add backend/app/models.py backend/tests/test_models.py && git commit -m "feat: core data models"`

---

## Task 2: File-based store

**Files:**
- Create: `backend/app/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `Profile`, `Job`, `Evaluation` from `app.models`.
- Produces: `save_profile(p)`, `load_profile()->Profile|None`, `upsert_jobs(list[Job])->int` (dedupes by `id`, returns count added), `load_jobs()->list[Job]`, `save_evaluation(e)`, `load_evaluation(job_id)->Evaluation|None`, `mark_applied(job_id)`, `applied_ids()->set[str]`.

- [ ] **Step 1: Write failing test `backend/tests/test_store.py`**

```python
import app.store as store
from app.models import Profile, Job, Evaluation, job_id

def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    store.save_profile(Profile(name="Ann", skills=["python"]))
    assert store.load_profile().name == "Ann"

def test_jobs_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr(store.cfg, "DATA_DIR", tmp_path)
    j = Job(id=job_id("gh","x","u"), source="gh", company="x", title="t", url="u")
    assert store.upsert_jobs([j, j]) == 1
    assert store.upsert_jobs([j]) == 0
    assert len(store.load_jobs()) == 1
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement `backend/app/store.py`** (reads paths lazily from `app.config as cfg` so tests can monkeypatch `DATA_DIR`)

```python
import json
from app import config as cfg
from app.models import Profile, Job, Evaluation

def _p(name): return cfg.DATA_DIR / name

def save_profile(p: Profile): _p("profile.json").write_text(p.model_dump_json(indent=2))
def load_profile():
    f = _p("profile.json")
    return Profile.model_validate_json(f.read_text()) if f.exists() else None

def load_jobs() -> list[Job]:
    f = _p("jobs.json")
    return [Job(**j) for j in json.loads(f.read_text())] if f.exists() else []

def upsert_jobs(jobs: list[Job]) -> int:
    existing = {j.id: j for j in load_jobs()}
    added = 0
    for j in jobs:
        if j.id not in existing:
            existing[j.id] = j; added += 1
    _p("jobs.json").write_text(json.dumps([j.model_dump() for j in existing.values()], indent=2))
    return added

def save_evaluation(e: Evaluation):
    (cfg.EVAL_DIR / f"{e.job_id}.json").write_text(e.model_dump_json(indent=2))
def load_evaluation(job_id: str):
    f = cfg.EVAL_DIR / f"{job_id}.json"
    return Evaluation.model_validate_json(f.read_text()) if f.exists() else None

def applied_ids() -> set[str]:
    f = _p("applied_log.json")
    return set(json.loads(f.read_text())) if f.exists() else set()
def mark_applied(job_id: str):
    ids = applied_ids(); ids.add(job_id)
    _p("applied_log.json").write_text(json.dumps(sorted(ids)))
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat: file-based store"`

---

## Task 3: Resume ingestion (markitdown + Claude)

**Files:**
- Create: `backend/app/llm.py`, `backend/app/ingest/resume.py`, `backend/app/ingest/__init__.py`
- Test: `backend/tests/test_resume.py`; fixture `backend/tests/fixtures/sample_resume.txt`

**Interfaces:**
- Produces: `llm.complete_json(system:str, user:str) -> dict` (calls Claude, strips code fences, `json.loads`). `resume.extract_text(path:Path) -> str` (markitdown). `resume.build_profile(resume_text:str) -> Profile` (Claude structured extract). `resume.ingest(path:Path) -> Profile`.
- Consumes: `Profile` (models), `LLM_MODEL` (config).

- [ ] **Step 1: Write `backend/app/llm.py`**

```python
import json, re, os
from anthropic import Anthropic
from app import config as cfg

_client = None
def _c():
    global _client
    if _client is None: _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client

def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    resp = _c().messages.create(model=cfg.LLM_MODEL, max_tokens=max_tokens,
        system=system, messages=[{"role": "user", "content": user}])
    text = resp.content[0].text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)
```

- [ ] **Step 2: Write failing test `backend/tests/test_resume.py`** (monkeypatch the LLM so no network/key needed)

```python
from pathlib import Path
import app.ingest.resume as r

def test_extract_text_txt():
    p = Path(__file__).parent / "fixtures" / "sample_resume.txt"
    assert "Python" in r.extract_text(p)

def test_build_profile_maps_fields(monkeypatch):
    monkeypatch.setattr(r.llm, "complete_json", lambda s, u, **k: {
        "name": "Ann Lee", "email": "a@x.com", "location": "Remote",
        "work_auth": "US citizen", "target_roles": ["ML Engineer"],
        "skills": ["python", "pytorch"], "proof_points": ["Shipped X"]})
    prof = r.build_profile("resume text with Python")
    assert prof.name == "Ann Lee" and "pytorch" in prof.skills
    assert prof.resume_text.startswith("resume text")
```

Create `backend/tests/fixtures/sample_resume.txt` with a few lines including "Python".

- [ ] **Step 3: Run, expect fail.**
- [ ] **Step 4: Implement `backend/app/ingest/resume.py`**

```python
from pathlib import Path
from markitdown import MarkItDown
from app import llm
from app.models import Profile

_EXTRACT_SYS = (
  "You extract a job candidate's structured profile from resume text. "
  "Return ONLY JSON with keys: name, email, location, work_auth "
  "(their stated work authorization / visa status, empty string if unknown), "
  "target_roles (list), skills (list), proof_points (list of concrete achievements). "
  "Do not invent facts.")

def extract_text(path: Path) -> str:
    return MarkItDown().convert(str(path)).text_content

def build_profile(resume_text: str) -> Profile:
    data = llm.complete_json(_EXTRACT_SYS, f"RESUME:\n{resume_text[:8000]}")
    return Profile(resume_text=resume_text, **{k: data.get(k) or ([] if k in
        ("target_roles","skills","proof_points") else "") for k in
        ("name","email","location","work_auth","target_roles","skills","proof_points")})

def ingest(path: Path) -> Profile:
    return build_profile(extract_text(path))
```

- [ ] **Step 5: Run, expect pass.** (`test_extract_text_txt` exercises real markitdown on the .txt fixture; the profile test is fully mocked.)
- [ ] **Step 6: Commit.** `git commit -am "feat: resume ingestion via markitdown + Claude"`

---

## Task 4: Vendor career-ops + characterize its scan output

**Files:**
- Create: `engine/career-ops/` (vendored clone), `scripts/setup-engine.ps1`, `backend/tests/fixtures/scan_sample.json`

**Interfaces:**
- Produces: a runnable `engine/career-ops` with `node scan-ats-full.mjs --help` working; a captured sample of real scan output committed as a fixture for Task 5's parser.

- [ ] **Step 1: Vendor career-ops and install**

Run:
```bash
git clone --depth 1 https://github.com/santifer/career-ops.git engine/career-ops
cd engine/career-ops && npm install
```
Add `engine/career-ops/` to the launchpad `.gitignore`'s exceptions plan: commit the clone WITHOUT `node_modules` (already gitignored). Record the pinned commit: `git -C engine/career-ops rev-parse HEAD` → note in the commit message.

- [ ] **Step 2: Verify the scanner runs and capture output shape**

Run:
```bash
cd engine/career-ops
node scan-ats-full.mjs --help
node scan-ats-full.mjs --ats greenhouse --limit 5 --since 7 --dry-run --md-out ../../launchpad_data/_scan_probe
```
Read what it writes: inspect `data/scan-history.tsv` and any `*.md` digest under `launchpad_data/_scan_probe`. Copy 3–5 representative rows/records into `backend/tests/fixtures/scan_sample.json` as a normalized list of `{company,title,location,url,posted,source}` reflecting the real fields observed. **This is a characterization step — the fixture must mirror actual output, not assumptions.**

- [ ] **Step 3: Write `scripts/setup-engine.ps1`** documenting the two commands above so setup is reproducible.

- [ ] **Step 4: Commit.** `git add engine/career-ops scripts/setup-engine.ps1 backend/tests/fixtures/scan_sample.json && git commit -m "chore: vendor career-ops engine + capture scan output fixture"`

---

## Task 5: career-ops scan wrapper

**Files:**
- Create: `backend/app/sources/__init__.py`, `backend/app/sources/portals.py`, `backend/app/sources/careerops_scan.py`
- Test: `backend/tests/test_careerops_scan.py`

**Interfaces:**
- Consumes: `Job`, `job_id` (models); `ENGINE_DIR` (config); fixture from Task 4.
- Produces: `portals.write_portals_yml(profile, dest:Path)`; `careerops_scan.parse_scan_output(raw:str|Path)->list[Job]`; `careerops_scan.run_scan(profile, ats:list[str], since_days:int)->list[Job]`.

- [ ] **Step 1: Write failing test `backend/tests/test_careerops_scan.py`** (tests the pure parser against the real-output fixture; does NOT spawn Node)

```python
import json
from pathlib import Path
from app.sources import careerops_scan as s

def test_parse_scan_output_to_jobs():
    raw = (Path(__file__).parent / "fixtures" / "scan_sample.json").read_text()
    jobs = s.parse_scan_output(raw)
    assert len(jobs) >= 1
    j = jobs[0]
    assert j.url and j.company and j.title and j.id and j.source
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement `portals.py`**

```python
from pathlib import Path
def write_portals_yml(profile, dest: Path):
    titles = "|".join(r.strip() for r in profile.target_roles) or ".*"
    loc = profile.location or ""
    dest.write_text(
        f"title_filter: \"{titles}\"\n"
        f"location_filter: \"{loc}\"\n"
        "companies: []\n")
```

- [ ] **Step 4: Implement `careerops_scan.py`** (parser matches the fields captured in Task 4; adjust keys to the real output)

```python
import json, subprocess, tempfile
from pathlib import Path
from app import config as cfg
from app.models import Job, job_id
from app.sources.portals import write_portals_yml

def parse_scan_output(raw) -> list[Job]:
    data = json.loads(Path(raw).read_text() if isinstance(raw, Path) else raw)
    jobs = []
    for r in data:
        url = r.get("url", "")
        src = r.get("source", "careerops")
        company = r.get("company", "")
        jobs.append(Job(id=job_id(src, company, url), source=src, company=company,
            title=r.get("title",""), location=r.get("location",""), url=url,
            description=r.get("description",""), posted=r.get("posted")))
    return jobs

def run_scan(profile, ats=None, since_days=7) -> list[Job]:
    ats = ats or ["greenhouse","lever","ashby","workday"]
    out = Path(tempfile.mkdtemp()) / "digest"
    write_portals_yml(profile, cfg.ENGINE_DIR / "portals.yml")
    subprocess.run(["node","scan-ats-full.mjs","--ats",",".join(ats),
        "--since",str(since_days),"--md-out",str(out)],
        cwd=cfg.ENGINE_DIR, check=True, capture_output=True, text=True, timeout=1200)
    # Read the results career-ops wrote (path/format confirmed in Task 4) and
    # normalize to the same JSON shape as the fixture before parsing.
    results_json = _normalize_engine_results(out)  # implement to match Task-4 findings
    return parse_scan_output(results_json)
```

Implement `_normalize_engine_results` against the **actual** files observed in Task 4 (e.g. read `data/scan-history.tsv` columns or the md digest) and return a JSON string matching the fixture schema. Add a docstring citing the exact source path.

- [ ] **Step 5: Run parser test, expect pass.** (The `run_scan`/Node path is covered by the integration smoke in Task 11, not unit tests.)
- [ ] **Step 6: Commit.** `git commit -am "feat: career-ops scan wrapper + portals.yml writer"`

---

## Task 6: crawl4ai adapter for extra public pages

**Files:**
- Create: `backend/app/sources/crawl_adapter.py`
- Test: `backend/tests/test_crawl_adapter.py`; fixture `backend/tests/fixtures/listing_page.html`

**Interfaces:**
- Consumes: `Job`, `job_id`.
- Produces: `crawl_adapter.jobs_from_markdown(md:str, base_url:str, company:str)->list[Job]` (pure parser over crawl4ai markdown/links); `async crawl_adapter.fetch_jobs(url:str, company:str)->list[Job]` (runs crawl4ai).

- [ ] **Step 1: Save a small real-ish `listing_page.html`** into fixtures with 2–3 `<a href="/jobs/123">Title</a>` entries under a jobs container.

- [ ] **Step 2: Write failing test `backend/tests/test_crawl_adapter.py`**

```python
from app.sources import crawl_adapter as c

def test_jobs_from_markdown_extracts_links():
    md = "## Jobs\n- [ML Engineer](https://acme.com/jobs/1)\n- [Data Scientist](https://acme.com/jobs/2)\n"
    jobs = c.jobs_from_markdown(md, base_url="https://acme.com", company="acme")
    assert {j.title for j in jobs} == {"ML Engineer", "Data Scientist"}
    assert all(j.url.startswith("https://acme.com/jobs/") for j in jobs)
```

- [ ] **Step 3: Run, expect fail.**
- [ ] **Step 4: Implement `crawl_adapter.py`**

```python
import re
from urllib.parse import urljoin
from app.models import Job, job_id

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

def jobs_from_markdown(md: str, base_url: str, company: str) -> list[Job]:
    jobs = []
    for title, url in _LINK.findall(md):
        full = urljoin(base_url, url)
        jobs.append(Job(id=job_id("crawl4ai", company, full), source="crawl4ai",
            company=company, title=title.strip(), url=full))
    return jobs

async def fetch_jobs(url: str, company: str) -> list[Job]:
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
    return jobs_from_markdown(result.markdown or "", base_url=url, company=company)
```

- [ ] **Step 5: Run parser test, expect pass.** (Live `fetch_jobs` covered by an opt-in integration test, skipped by default.)
- [ ] **Step 6: Commit.** `git commit -am "feat: crawl4ai public-listing adapter"`

---

## Task 7: Evaluation with career-ops rubric

**Files:**
- Create: `backend/app/evaluate/__init__.py`, `backend/app/evaluate/rubric.py`, `backend/app/evaluate/evaluator.py`
- Test: `backend/tests/test_evaluator.py`

**Interfaces:**
- Consumes: `Profile`, `Job`, `Evaluation`; `llm.complete_json`; career-ops prompt files under `engine/career-ops/modes/`.
- Produces: `rubric.load_rubric()->str` (concatenates `modes/_shared.md` + `modes/oferta.md`, cached); `evaluator.evaluate(profile, job)->Evaluation`.

- [ ] **Step 1: Write failing test `backend/tests/test_evaluator.py`** (LLM mocked)

```python
import app.evaluate.evaluator as ev
from app.models import Profile, Job

def test_evaluate_maps_flags(monkeypatch):
    monkeypatch.setattr(ev, "load_rubric", lambda: "RUBRIC")
    monkeypatch.setattr(ev.llm, "complete_json", lambda s, u, **k: {
        "score": 4.3, "summary": "Strong fit", "cv_match": "matches ML",
        "scam_flag": False, "scam_reason": "", "no_sponsorship": True,
        "strengths": ["pytorch"], "gaps": ["k8s"]})
    e = ev.evaluate(Profile(name="A", skills=["pytorch"]),
                    Job(id="j1", source="gh", company="x", title="ML Eng", url="u",
                        description="No visa sponsorship."))
    assert e.score == 4.3 and e.no_sponsorship is True and e.job_id == "j1"
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement `rubric.py`**

```python
from functools import lru_cache
from app import config as cfg

@lru_cache
def load_rubric() -> str:
    modes = cfg.ENGINE_DIR / "modes"
    parts = []
    for name in ("_shared.md", "oferta.md"):
        f = modes / name
        if f.exists(): parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)
```

- [ ] **Step 4: Implement `evaluator.py`**

```python
from app import llm
from app.evaluate.rubric import load_rubric
from app.models import Profile, Job, Evaluation

_SYS = (
  "You are a rigorous job-fit evaluator. Apply the rubric below. "
  "Return ONLY JSON with keys: score (1-5 float), summary, cv_match, "
  "scam_flag (bool), scam_reason, no_sponsorship (bool: true if the posting "
  "explicitly refuses visa sponsorship), strengths (list), gaps (list).\n\nRUBRIC:\n")

def evaluate(profile: Profile, job: Job) -> Evaluation:
    sys = _SYS + load_rubric()[:12000]
    user = (f"CANDIDATE:\n{profile.model_dump_json()}\n\n"
            f"JOB: {job.title} @ {job.company}\n{job.description[:6000]}")
    d = llm.complete_json(sys, user)
    return Evaluation(job_id=job.id, score=float(d.get("score", 0)),
        summary=d.get("summary",""), cv_match=d.get("cv_match",""),
        scam_flag=bool(d.get("scam_flag")), scam_reason=d.get("scam_reason",""),
        no_sponsorship=bool(d.get("no_sponsorship")),
        strengths=d.get("strengths",[]), gaps=d.get("gaps",[]))
```

- [ ] **Step 5: Run, expect pass.**
- [ ] **Step 6: Commit.** `git commit -am "feat: Claude evaluation using career-ops rubric"`

---

## Task 8: Tailoring — CV markdown + cover letter

**Files:**
- Create: `backend/app/tailor/__init__.py`, `backend/app/tailor/writer.py`
- Test: `backend/tests/test_writer.py`

**Interfaces:**
- Consumes: `Profile`, `Job`, `Evaluation`, `TailoredDoc`; `llm.complete_json`.
- Produces: `writer.tailor(profile, job, evaluation)->TailoredDoc`.

- [ ] **Step 1: Failing test `backend/tests/test_writer.py`** (LLM mocked)

```python
import app.tailor.writer as w
from app.models import Profile, Job, Evaluation

def test_tailor_returns_doc(monkeypatch):
    monkeypatch.setattr(w.llm, "complete_json", lambda s,u,**k: {
        "cv_markdown": "# Ann Lee\n- pytorch", "cover_letter": "Dear team,"})
    d = w.tailor(Profile(name="Ann Lee"),
                 Job(id="j1", source="gh", company="Acme", title="ML", url="u"),
                 Evaluation(job_id="j1", score=4.5, summary="", cv_match=""))
    assert d.job_id == "j1" and "pytorch" in d.cv_markdown and d.cover_letter
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement `writer.py`**

```python
from app import llm
from app.models import Profile, Job, Evaluation, TailoredDoc

_SYS = (
  "You tailor a candidate's resume and write a cover letter for ONE job. "
  "Rewrite only from the candidate's real experience — never invent facts or "
  "employers. Return ONLY JSON with keys: cv_markdown (a full one-page CV in "
  "markdown, reordered/reworded to match the job) and cover_letter (150-200 words).")

def tailor(profile: Profile, job: Job, evaluation: Evaluation) -> TailoredDoc:
    user = (f"CANDIDATE:\n{profile.model_dump_json()}\n\nJOB: {job.title} @ {job.company}\n"
            f"{job.description[:5000]}\n\nEVAL STRENGTHS: {evaluation.strengths}\n"
            f"GAPS TO DOWNPLAY: {evaluation.gaps}")
    d = llm.complete_json(_SYS, user, max_tokens=2500)
    return TailoredDoc(job_id=job.id, cv_markdown=d.get("cv_markdown",""),
                       cover_letter=d.get("cover_letter",""))
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat: CV + cover-letter tailoring"`

---

## Task 9: PDF rendering (Apple-styled, WeasyPrint)

**Files:**
- Create: `backend/app/tailor/pdf.py`, `backend/app/tailor/cv_template.html`
- Test: `backend/tests/test_pdf.py`

**Interfaces:**
- Consumes: `TailoredDoc`; `OUTPUT_DIR`.
- Produces: `pdf.render_cv_pdf(doc, out_path:Path)->Path` (markdown→HTML→PDF).

- [ ] **Step 1: Failing test `backend/tests/test_pdf.py`**

```python
from pathlib import Path
from app.tailor import pdf
from app.models import TailoredDoc

def test_render_pdf(tmp_path):
    out = tmp_path / "cv.pdf"
    p = pdf.render_cv_pdf(TailoredDoc(job_id="j1",
        cv_markdown="# Ann Lee\n\n**ML Engineer**\n\n- Built X", cover_letter="Hi"), out)
    assert p.exists() and p.stat().st_size > 500
    assert p.read_bytes()[:4] == b"%PDF"
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement `cv_template.html`** — a clean single-column A4 template with an Apple-ish system-font stack (`-apple-system, "SF Pro", Inter, sans-serif`), generous whitespace, a `{{ body }}` slot. (Design polish applied at execution using the apple-design skill.)
- [ ] **Step 4: Implement `pdf.py`**

```python
from pathlib import Path
from markdown import markdown as md_to_html   # add "markdown" to deps
from weasyprint import HTML
from app import config as cfg

_TEMPLATE = (Path(__file__).parent / "cv_template.html").read_text(encoding="utf-8")

def render_cv_pdf(doc, out_path: Path) -> Path:
    body = md_to_html(doc.cv_markdown)
    html = _TEMPLATE.replace("{{ body }}", body)
    HTML(string=html).write_pdf(str(out_path))
    return out_path
```

Add `"markdown>=3.6"` to `pyproject.toml` deps.

- [ ] **Step 5: Run, expect pass.** (If WeasyPrint native deps are missing on Windows, install GTK per its docs; record the step in `scripts/setup-engine.ps1`.)
- [ ] **Step 6: Commit.** `git commit -am "feat: Apple-styled CV PDF rendering"`

---

## Task 10: FastAPI routes wiring it together

**Files:**
- Modify: `backend/app/api.py`
- Test: `backend/tests/test_api_flow.py`

**Interfaces:**
- Consumes: everything above.
- Produces endpoints:
  - `POST /resume` (multipart file) → `Profile`
  - `GET /profile` → `Profile|null`
  - `POST /scan` `{ats?:list, since_days?:int, crawl_urls?:[{url,company}]}` → `{added:int, total:int}`
  - `GET /jobs` → `list[Job]` (each with attached `evaluation` if present), sorted by score desc
  - `POST /evaluate` `{job_ids?:list, min_only?:bool}` → `{evaluated:int}`
  - `POST /tailor/{job_id}` → `{pdf_url:str, cover_letter:str}`
  - `POST /apply/{job_id}` → `{url:str}` (marks applied, returns the real apply URL; **never submits**)
  - `GET /output/{job_id}.pdf` → file

- [ ] **Step 1: Write failing test `backend/tests/test_api_flow.py`** (mock ingest + scan + evaluate so no network)

```python
from fastapi.testclient import TestClient
import app.api as api
from app.models import Profile, Job, job_id

def test_scan_and_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(api.store.cfg, "DATA_DIR", tmp_path)
    j = Job(id=job_id("gh","x","https://x/apply"), source="gh", company="x",
            title="ML", url="https://x/apply")
    monkeypatch.setattr(api.careerops_scan, "run_scan", lambda *a, **k: [j])
    monkeypatch.setattr(api.store, "load_profile", lambda: Profile(name="A"))
    c = TestClient(api.app)
    assert c.post("/scan", json={}).json()["added"] == 1
    r = c.post(f"/apply/{j.id}")
    assert r.json()["url"] == "https://x/apply"
    assert j.id in api.store.applied_ids()
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement the routes in `api.py`** wiring `ingest.resume`, `sources.careerops_scan`, `sources.crawl_adapter`, `evaluate.evaluator`, `tailor.writer`, `tailor.pdf`, `store`. `/apply` does: `store.mark_applied(job_id); return {"url": job.url}` — no submission. `/scan` runs career-ops scan + optional crawl urls, `store.upsert_jobs`, returns counts. `/evaluate` loops jobs (respect optional `job_ids`), `store.save_evaluation`. `/tailor` loads profile+job+eval, writes `OUTPUT_DIR/{job_id}.pdf`, returns `/output/{job_id}.pdf`.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat: REST API wiring full pipeline"`

---

## Task 11: Backend integration smoke (opt-in, real engine)

**Files:**
- Create: `backend/tests/test_integration_scan.py` (marked `@pytest.mark.integration`, skipped unless `RUN_INTEGRATION=1`)

- [ ] **Step 1:** Write a test that, when `RUN_INTEGRATION=1`, calls `careerops_scan.run_scan(Profile(target_roles=["engineer"], location="Remote"), ats=["greenhouse"], since_days=3)` and asserts it returns ≥1 `Job` with a real URL. Document in the test docstring that this spawns Node + hits public ATS APIs.
- [ ] **Step 2:** Run `RUN_INTEGRATION=1 python -m pytest -m integration -v` once manually; confirm real jobs come back. Fix `_normalize_engine_results` if the shape differs from the Task-4 fixture.
- [ ] **Step 3: Commit.** `git commit -am "test: opt-in engine integration smoke"`

---

## Task 12: Next.js frontend (Apple-designed)

**Files:**
- Create: `frontend/` via `npx create-next-app@latest frontend --ts --tailwind --app --eslint`
- Create: `frontend/lib/api.ts`, `frontend/app/page.tsx` (upload), `frontend/app/dashboard/page.tsx` (ranked jobs), `frontend/app/job/[id]/page.tsx` (detail + tailor + assisted-apply), shared components under `frontend/components/`.

**Interfaces:**
- Consumes: backend REST (Task 10). `lib/api.ts` typed client mirroring the endpoints.

> **Design gate:** At execution, invoke the `apple-design` skill (from `emilkowalski/skills`) and `frontend-design` before building components. This task lists structure + behavior; the skills own the visual system (type scale, spacing, motion, color).

- [ ] **Step 1:** Scaffold with the create-next-app command; add `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- [ ] **Step 2:** `lib/api.ts` — typed `uploadResume(file)`, `getProfile()`, `scan(body)`, `getJobs()`, `evaluate(body)`, `tailor(jobId)`, `apply(jobId)`.
- [ ] **Step 3: Upload screen** (`app/page.tsx`) — drag-drop resume → `POST /resume` → show parsed Profile in an editable card → "Save & continue".
- [ ] **Step 4: Dashboard** (`app/dashboard/page.tsx`) — a "Scan" control (roles/locations/since) → `POST /scan`; a ranked list of job cards showing score, **scam badge**, **no-sponsorship badge**, company, title, location, and an "Apply" link. "Evaluate all" triggers `POST /evaluate`.
- [ ] **Step 5: Job detail** (`app/job/[id]/page.tsx`) — full JD, evaluation breakdown (strengths/gaps/summary), "Tailor CV" → `POST /tailor/{id}` → embed PDF + show cover letter; **"Open apply page"** button → `POST /apply/{id}` then `window.open(url)` in a new tab (assisted, never auto-submit).
- [ ] **Step 6:** Manual verification — run backend (`uvicorn app.api:app --reload`) + `npm run dev`; walk upload → scan → evaluate → tailor → open-apply. Confirm the apply button opens the real URL in a new tab and the app never submits.
- [ ] **Step 7: Commit.** `git commit -am "feat: Apple-designed Next.js frontend"`

---

## Task 13: Run/setup docs

**Files:**
- Create: `README.md`, `scripts/dev.ps1`

- [ ] **Step 1:** `README.md` — prerequisites (Node ≥18, Python 3.11, `ANTHROPIC_API_KEY`, WeasyPrint/GTK on Windows), setup (`scripts/setup-engine.ps1`, `pip install -e backend[dev]`, `npm i` in frontend), and run steps. State the boundaries: public sources only, assisted-apply never auto-submits.
- [ ] **Step 2:** `scripts/dev.ps1` — start uvicorn + next dev together.
- [ ] **Step 3: Commit.** `git commit -am "docs: setup and run guide"`

---

## Task 14: Multi-aggregator job sources (fresher-friendly)

> Added 2026-08-10 per expanded requirement: pull from many public/no-login job
> boards and favour fresher / 0–2-year / intern / new-grad roles. Execute this task
> AFTER Task 11 and BEFORE the frontend (Task 12) so the UI surfaces the richer results.

**Files:**
- Create: `backend/app/sources/experience.py`, `backend/app/sources/aggregators.py`
- Test: `backend/tests/test_experience.py`, `backend/tests/test_aggregators.py`
- Fixtures: `backend/tests/fixtures/agg_remotive.json`, `agg_arbeitnow.json`, `agg_remoteok.json`, `agg_jobicy.json`, `agg_themuse.json` (small trimmed real API responses, 2–3 records each)
- Modify: `backend/app/api.py` (extend `/scan` with `aggregators` + `fresher_only`)

**Interfaces:**
- Consumes: `Job`, `job_id` (models); `httpx`.
- Produces:
  - `experience.is_entry_level(title:str, description:str="") -> bool`
  - `experience.experience_filter(jobs:list[Job]) -> list[Job]`
  - `aggregators.parse_remotive(data:dict)->list[Job]`, `parse_arbeitnow`, `parse_remoteok(data:list)`, `parse_jobicy`, `parse_themuse` (pure normalizers)
  - `aggregators.PROVIDERS: dict[str, callable]` and `async aggregators.fetch_all(query:str="", providers:list[str]|None=None, fresher_only:bool=True) -> list[Job]`

### Step 1: Experience filter (TDD)

- [ ] **Write `backend/tests/test_experience.py`**

```python
from app.sources.experience import is_entry_level, experience_filter
from app.models import Job

def test_entry_level_positive():
    assert is_entry_level("Junior Software Engineer")
    assert is_entry_level("New Grad Data Analyst")
    assert is_entry_level("Software Engineer Intern")
    assert is_entry_level("Associate Developer", "0-2 years experience")

def test_entry_level_negative():
    assert not is_entry_level("Senior Software Engineer")
    assert not is_entry_level("Staff Engineer")
    assert not is_entry_level("Engineering Manager")
    assert not is_entry_level("Principal Architect")

def test_experience_filter_keeps_only_entry():
    jobs = [Job(id="1", source="s", company="c", title="Senior Engineer", url="u1"),
            Job(id="2", source="s", company="c", title="Junior Engineer", url="u2")]
    kept = experience_filter(jobs)
    assert [j.id for j in kept] == ["2"]
```

- [ ] **Run RED**, then implement `backend/app/sources/experience.py`:

```python
import re
from app.models import Job

_ENTRY = ("intern", "internship", "junior", "jr ", "jr.", "entry level",
          "entry-level", "new grad", "new-grad", "graduate", "associate",
          "trainee", "apprentice", "0-2 year", "0 to 2 year", "early career",
          "fresher", "campus")
_SENIOR = ("senior", "sr ", "sr.", "staff", "principal", "lead ", "manager",
           "director", "head of", "architect", "vp ", "vice president",
           "executive", "expert", "10+ year", "distinguished")

def is_entry_level(title: str, description: str = "") -> bool:
    t = (title or "").lower()
    d = (description or "").lower()
    if any(s in t for s in _SENIOR):
        return False
    if any(e in t for e in _ENTRY):
        return True
    # title neutral: accept if the description signals early-career and doesn't shout senior
    if any(e in d for e in ("entry level", "entry-level", "new grad", "0-2 year",
                            "0 to 2 year", "recent graduate", "fresher")):
        return not any(s in d for s in ("senior", "principal", "staff", "5+ year", "7+ year"))
    return False

def experience_filter(jobs: list[Job]) -> list[Job]:
    return [j for j in jobs if is_entry_level(j.title, j.description)]
```

- [ ] **Run GREEN.** Command: `cd backend && python -m pytest tests/test_experience.py -v`
- [ ] **Commit:** `git commit -am "feat: entry-level (fresher) experience filter"`

### Step 2: Aggregator normalizers (TDD, pure parsers against fixtures)

First create the fixtures by capturing 2–3 real records from each API (trim to the
fields used). Endpoints (all public, no key): Remotive
`https://remotive.com/api/remote-jobs?search=<q>`; Arbeitnow
`https://www.arbeitnow.com/api/job-board-api`; RemoteOK `https://remoteok.com/api`
(first array element is legal metadata — skip it); Jobicy
`https://jobicy.com/api/v2/remote-jobs?count=20`; The Muse
`https://www.themuse.com/api/public/jobs?level=Entry%20Level&page=0`.

- [ ] **Write `backend/tests/test_aggregators.py`** (pure parsers, no network):

```python
import json
from pathlib import Path
from app.sources import aggregators as a

FX = Path(__file__).parent / "fixtures"

def _load(name): return json.loads((FX / name).read_text(encoding="utf-8"))

def test_parse_remotive():
    jobs = a.parse_remotive(_load("agg_remotive.json"))
    assert jobs and all(j.source == "remotive" and j.url and j.title for j in jobs)

def test_parse_arbeitnow():
    jobs = a.parse_arbeitnow(_load("agg_arbeitnow.json"))
    assert jobs and all(j.source == "arbeitnow" and j.url for j in jobs)

def test_parse_remoteok_skips_legal():
    jobs = a.parse_remoteok(_load("agg_remoteok.json"))
    assert jobs and all(j.source == "remoteok" and j.title for j in jobs)

def test_parse_jobicy():
    jobs = a.parse_jobicy(_load("agg_jobicy.json"))
    assert jobs and all(j.source == "jobicy" and j.url for j in jobs)

def test_parse_themuse():
    jobs = a.parse_themuse(_load("agg_themuse.json"))
    assert jobs and all(j.source == "themuse" and j.url for j in jobs)
```

- [ ] **Run RED**, then implement `backend/app/sources/aggregators.py`:

```python
import re
import httpx
from app.models import Job, job_id

_TAG = re.compile(r"<[^>]+>")
def _clean(s): return _TAG.sub(" ", s or "").strip()

def parse_remotive(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("url", "")
        out.append(Job(id=job_id("remotive", j.get("company_name",""), url),
            source="remotive", company=j.get("company_name",""), title=j.get("title",""),
            location=j.get("candidate_required_location",""), url=url,
            description=_clean(j.get("description","")), posted=j.get("publication_date")))
    return out

def parse_arbeitnow(data: dict) -> list[Job]:
    out = []
    for j in data.get("data", []):
        url = j.get("url", "")
        out.append(Job(id=job_id("arbeitnow", j.get("company_name",""), url),
            source="arbeitnow", company=j.get("company_name",""), title=j.get("title",""),
            location=j.get("location",""), url=url,
            description=_clean(j.get("description","")), posted=str(j.get("created_at",""))))
    return out

def parse_remoteok(data: list) -> list[Job]:
    out = []
    for j in data:
        # first element is legal metadata (has no "position"/"id" job fields)
        if not isinstance(j, dict) or not j.get("position"):
            continue
        url = j.get("url", "")
        out.append(Job(id=job_id("remoteok", j.get("company",""), url),
            source="remoteok", company=j.get("company",""), title=j.get("position",""),
            location=j.get("location",""), url=url,
            description=_clean(j.get("description","")), posted=j.get("date")))
    return out

def parse_jobicy(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("url", "")
        out.append(Job(id=job_id("jobicy", j.get("companyName",""), url),
            source="jobicy", company=j.get("companyName",""), title=j.get("jobTitle",""),
            location=j.get("jobGeo",""), url=url,
            description=_clean(j.get("jobExcerpt","") or j.get("jobDescription","")),
            posted=j.get("pubDate")))
    return out

def parse_themuse(data: dict) -> list[Job]:
    out = []
    for j in data.get("results", []):
        url = (j.get("refs") or {}).get("landing_page", "")
        company = (j.get("company") or {}).get("name", "")
        locs = ", ".join(l.get("name","") for l in j.get("locations", []))
        out.append(Job(id=job_id("themuse", company, url), source="themuse",
            company=company, title=j.get("name",""), location=locs, url=url,
            description=_clean(j.get("contents","")), posted=j.get("publication_date")))
    return out

_ENDPOINTS = {
    "remotive":  ("https://remotive.com/api/remote-jobs", parse_remotive, "dict"),
    "arbeitnow": ("https://www.arbeitnow.com/api/job-board-api", parse_arbeitnow, "dict"),
    "remoteok":  ("https://remoteok.com/api", parse_remoteok, "list"),
    "jobicy":    ("https://jobicy.com/api/v2/remote-jobs?count=50", parse_jobicy, "dict"),
    "themuse":   ("https://www.themuse.com/api/public/jobs?level=Entry%20Level&page=0", parse_themuse, "dict"),
}
PROVIDERS = {k: v[1] for k, v in _ENDPOINTS.items()}

async def fetch_all(query: str = "", providers=None, fresher_only: bool = True) -> list[Job]:
    from app.sources.experience import experience_filter
    names = providers or list(_ENDPOINTS.keys())
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "LaunchPad/1.0"}) as client:
        for name in names:
            url, parser, _ = _ENDPOINTS[name]
            if name == "remotive" and query:
                url = f"{url}?search={query}"
            try:
                r = await client.get(url)
                r.raise_for_status()
                jobs.extend(parser(r.json()))
            except Exception:
                continue  # per-source non-fatal (spec §6)
    return experience_filter(jobs) if fresher_only else jobs
```

- [ ] **Run GREEN.** Command: `cd backend && python -m pytest tests/test_aggregators.py -v`
- [ ] **Commit:** `git commit -am "feat: multi-aggregator public job sources (remotive/arbeitnow/remoteok/jobicy/themuse)"`

### Step 3: Wire into `/scan`

- [ ] Extend the `/scan` request model with `aggregators: list[str] | None = None` and
  `fresher_only: bool = True`. In the handler, after the career-ops + crawl legs, call
  `await aggregators.fetch_all(query=" ".join(profile.target_roles), providers=req.aggregators, fresher_only=req.fresher_only)`
  and extend the jobs list before `store.upsert_jobs`. Import `from app.sources import aggregators` at module level. Keep the existing `test_api_flow.py` green (its monkeypatched `run_scan` path is unaffected; `fetch_all` over an empty/default provider list must not be required for that test — guard so that when the aggregator call fails or is disabled the scan still returns).
- [ ] Add one line to the `/scan` behavior: if `fresher_only` is true, ALSO apply
  `experience.experience_filter` to the career-ops + crawl jobs so the whole listing is fresher-focused (imported at module level).
- [ ] **Run** `cd backend && python -m pytest -v` — full suite green (pdf + integration skips allowed).
- [ ] **Commit:** `git commit -am "feat: wire aggregators + fresher filter into /scan"`

### Step 4: Opt-in live smoke (skipped by default)

- [ ] Add `backend/tests/test_integration_aggregators.py` marked to skip unless
  `RUN_INTEGRATION=1`; when enabled it calls `await aggregators.fetch_all(fresher_only=True)`
  and asserts ≥1 entry-level Job with a real URL from at least one provider. Run it once
  with `RUN_INTEGRATION=1` to confirm at least a couple of providers respond and the
  fresher filter yields real junior roles; note results in the report. Providers that are
  down that day are tolerated (per-source non-fatal). Commit.

### Step 5: Country coverage (India + Germany) + visa/sponsorship — Adzuna provider

> Requirement: the user is an Indian citizen — needs India-based roles, plus Germany and
> other countries WHERE VISA SPONSORSHIP IS AVAILABLE. Adzuna is one free API key that
> covers India (`in`), Germany (`de`), UK (`gb`), US (`us`) and more with real onshore
> listings — the best single addition for country breadth. It is OPT-IN: skipped unless
> the user sets `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` (free from developer.adzuna.com).

- [ ] Add `parse_adzuna(data: dict, country: str) -> list[Job]` to `aggregators.py`:

```python
def parse_adzuna(data: dict, country: str) -> list[Job]:
    out = []
    for j in data.get("results", []):
        url = j.get("redirect_url", "")
        company = (j.get("company") or {}).get("display_name", "")
        loc = (j.get("location") or {}).get("display_name", "")
        out.append(Job(id=job_id("adzuna", company, url), source=f"adzuna-{country}",
            company=company, title=j.get("title",""), location=loc, url=url,
            description=_clean(j.get("description","")), posted=j.get("created")))
    return out
```

- [ ] Add a country-aware Adzuna fetch and fold it into `fetch_all`. Default countries
  include India and Germany:

```python
import os
ADZUNA_COUNTRIES = ["in", "de", "gb", "us"]   # India + Germany first

async def fetch_adzuna(client, query: str = "", countries=None) -> list[Job]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []  # opt-in: no key, no call
    jobs = []
    for c in (countries or ADZUNA_COUNTRIES):
        url = (f"https://api.adzuna.com/v1/api/jobs/{c}/search/1"
               f"?app_id={app_id}&app_key={app_key}&results_per_page=50"
               f"&max_days_old=30&what={query or 'engineer'}")
        try:
            r = await client.get(url); r.raise_for_status()
            jobs.extend(parse_adzuna(r.json(), c))
        except Exception:
            continue
    return jobs
```

  In `fetch_all`, after the no-key providers loop, also `jobs.extend(await fetch_adzuna(client, query, countries))`. Keep `fresher_only` filtering applied to the combined result. Add a `test_parse_adzuna` unit test against a trimmed `backend/tests/fixtures/agg_adzuna.json` fixture (assert `source` starts with `"adzuna-"`, real url/company).
- [ ] **Commit:** `git commit -am "feat: Adzuna multi-country provider (India/Germany/visa countries, opt-in key)"`

### Step 6: Visa-sponsorship signal + named niche sites (h1bvisajobs, TrueUp, Absolute Internship)

- [ ] **Sponsorship awareness.** The evaluator already emits `no_sponsorship` (Task 7).
  Add `experience.needs_sponsorship_ok(job, citizen_country="IN") -> bool` helper in a
  small `sources/visa.py`: returns True if the job is in the citizen's country (India),
  OR is remote, OR comes from a sponsor-friendly source (see below), OR its evaluation
  doesn't set `no_sponsorship`. This is a SIGNAL for ranking/filtering, not a hard gate.
  Unit-test it with a couple of Job cases (India job → True; US job flagged no_sponsorship
  → False; source `h1bvisajobs` → True).
- [ ] **Named niche sites as curated crawl sources.** Add to `aggregators.py` (or a new
  `sources/curated.py`) a registry used via the existing `crawl_adapter.fetch_jobs`:

```python
# Best-effort public-page crawl targets. Brittle (JS-heavy, markup changes) —
# per-source non-fatal; treated as a bonus on top of the reliable API providers.
CURATED_CRAWL_SOURCES = [
    {"company": "h1bvisajobs", "url": "https://www.h1bvisajobs.com/jobs",
     "sponsor_friendly": True},   # US roles from H1B-sponsoring employers
    {"company": "trueup",       "url": "https://www.trueup.io/jobs"},
    {"company": "absolute-internship", "url": "https://absoluteinternship.com/internships/"},
]
SPONSOR_FRIENDLY_SOURCES = {"h1bvisajobs"}
```

  Wire a `crawl_curated: bool = False` option into `/scan`: when true, iterate
  `CURATED_CRAWL_SOURCES` calling `crawl_adapter.fetch_jobs(url, company)`, tag jobs from
  `SPONSOR_FRIENDLY_SOURCES`, extend the results (per-source failures ignored).
- [ ] **Honesty caveat (put in the report and Task 13 docs):** these three sites have no
  public API and are JS-heavy; markdown-link extraction is best-effort and may capture
  noise or need per-site selectors later. They supplement — they do not replace — the
  reliable API providers (career-ops ATS + Adzuna + remote aggregators). Absolute
  Internship is a paid placement PROGRAM, not a standard job board, so yield may be low.
- [ ] **Run** `cd backend && python -m pytest -v` — full suite green (skips allowed).
- [ ] **Commit:** `git commit -am "feat: visa-sponsorship signal + curated niche crawl sources (h1bvisajobs/trueup/absolute-internship)"`

---

## Self-Review

**Spec coverage:**
- §1 purpose → Tasks 3–12 deliver upload→scan→rank→tailor→assisted-apply. ✓
- §4 source layer (b) multi-aggregator + fresher filter → Task 14. ✓
- §2 boundaries → `/apply` never submits (Task 10 test asserts); public sources only (Tasks 5–6). ✓
- §3 architecture → Next.js+FastAPI+career-ops subprocess+crawl4ai (Tasks 0,5,6,12). ✓
- §4 six components → resume ingest (3), source layer (5,6), eval (7), tailoring (8,9), assisted-apply (10,12), Apple frontend (12). ✓
- §5 data flow → mirrored by API endpoints (Task 10). ✓
- §6 error handling → per-source non-fatal + subprocess stderr surfaced (Tasks 5,10); OCR fallback to paste (frontend Task 12 Step 3 editable card). ✓
- §7 testing → unit parsers with fixtures (4,5,6), mocked-LLM units (3,7,8), integration smoke (11), frontend manual (12). ✓
- §8 prereqs, §9 deferred, §10 YAGNI → honored; deferred items absent from tasks. ✓

**Placeholder scan:** `_normalize_engine_results` (Task 5) and the CV template polish (Task 9) and frontend visuals (Task 12) are intentionally execution-time — each is gated on a prior characterization step (Task 4) or a named skill, not a vague "handle it." No `TBD`/`TODO` code steps.

**Type consistency:** `Job`, `Profile`, `Evaluation`, `TailoredDoc`, `job_id` signatures are identical across Tasks 1–12; `llm.complete_json(system,user,max_tokens)` used consistently; store function names match their call sites in Task 10.

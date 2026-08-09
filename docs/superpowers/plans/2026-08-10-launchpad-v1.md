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

## Self-Review

**Spec coverage:**
- §1 purpose → Tasks 3–12 deliver upload→scan→rank→tailor→assisted-apply. ✓
- §2 boundaries → `/apply` never submits (Task 10 test asserts); public sources only (Tasks 5–6). ✓
- §3 architecture → Next.js+FastAPI+career-ops subprocess+crawl4ai (Tasks 0,5,6,12). ✓
- §4 six components → resume ingest (3), source layer (5,6), eval (7), tailoring (8,9), assisted-apply (10,12), Apple frontend (12). ✓
- §5 data flow → mirrored by API endpoints (Task 10). ✓
- §6 error handling → per-source non-fatal + subprocess stderr surfaced (Tasks 5,10); OCR fallback to paste (frontend Task 12 Step 3 editable card). ✓
- §7 testing → unit parsers with fixtures (4,5,6), mocked-LLM units (3,7,8), integration smoke (11), frontend manual (12). ✓
- §8 prereqs, §9 deferred, §10 YAGNI → honored; deferred items absent from tasks. ✓

**Placeholder scan:** `_normalize_engine_results` (Task 5) and the CV template polish (Task 9) and frontend visuals (Task 12) are intentionally execution-time — each is gated on a prior characterization step (Task 4) or a named skill, not a vague "handle it." No `TBD`/`TODO` code steps.

**Type consistency:** `Job`, `Profile`, `Evaluation`, `TailoredDoc`, `job_id` signatures are identical across Tasks 1–12; `llm.complete_json(system,user,max_tokens)` used consistently; store function names match their call sites in Task 10.

# LaunchPad — Design Spec

**Date:** 2026-08-10
**Status:** Approved (brainstorming → writing-plans)
**Owner:** Pranav-Aditya016

---

## 1. Purpose

A personal, locally-run job-search portal that helps the user land a role. The user
uploads a resume once; the app scans many *public* job sources, ranks them by
reasoned fit (not keyword matching), flags scams and no-sponsorship postings,
generates a tailored CV + cover letter per job at scale, and offers a polished
**assisted-apply** flow (opens the real apply page; the human presses submit).

This is a filter, not a spray-and-pray tool. It never bypasses authentication and
never silently mass-submits applications.

## 2. Non-negotiable boundaries

These are decided and out of scope regardless of future requests:

- **No authentication bypass.** No "direct-login" style tooling, no scraping of
  login-gated content against a site's terms, no using a third party's credentials.
  Login-gated sources, if ever added, use the *user's own* browser session/cookies,
  opt-in, and are a later add-on — never v1.
- **No autonomous mass-submission.** The app generates tailored drafts at scale
  (100+), but a human reviews and submits each application. Assisted-apply opens the
  real page; it does not click submit. This mirrors career-ops' own stance
  ("never sends, submits, or clicks anything").

Rationale: both protect the user's real goal. Bot-submitted applications get
accounts banned and get candidates blacklisted by recruiters; a strong filter is
what actually lands the job (validated by the career-ops case study — 740+ jobs
evaluated, 100+ CVs, 1 role landed).

## 3. Architecture

```
Next.js (React + Tailwind)          ← Apple-design skill applied here
        │  REST / JSON
        ▼
FastAPI (Python)  — orchestrator, our own code
        ├─ career-ops engine (invoked as Node subprocesses; reads its data files)
        │     • scan-ats-full.mjs / scan.mjs      → portal scanning
        │     • openrouter-runner.mjs {scan,pipeline,evaluate,apply} → headless LLM pipeline
        │     • generate-pdf.mjs / build-cv-html.mjs → tailored ATS CV PDFs
        │     • generate-cover-letter.mjs          → cover letters
        │     • tracker.mjs / build-dashboard.mjs  → pipeline state
        │     • ollama-eval.mjs                     → local-model eval (future)
        ├─ resume ingestion  [NEW]  → markitdown (PDF/DOCX→text) + Claude structured extract
        ├─ crawl4ai fetcher  [NEW]  → extra public listing pages career-ops doesn't cover
        └─ data layer        → career-ops file-based tracker (DATA_CONTRACT.md) as source of truth
```

**Integration seam:** career-ops exposes ~50 standalone Node CLI scripts with npm
entry points and a documented file-based data contract. FastAPI shells out to these
scripts and consumes their JSON/data output. No fork of career-ops internals; we
treat it as an engine behind a stable subprocess boundary.

## 4. Components (each isolated, single-purpose)

1. **Resume Ingest** — `POST /resume`: upload PDF/DOCX → markitdown → text → Claude
   extracts a structured profile (identity, skills, roles, proof points, work-auth
   status). Output conforms to a schema informed by Google's Open Knowledge Format
   (OKF) review. *Deferred: Unlimited-OCR (GPU) and airllm (local large models).*
2. **Source layer** — career-ops portal scan (Greenhouse / Ashby / Lever / Wellfound /
   100+ preconfigured companies) **+** a crawl4ai adapter for extra public pages.
   Public sources only in v1.
3. **Ranking / evaluation** — career-ops A–G reasoning rubric, including Block G
   scam/ghost-job detection and the no-sponsorship / work-auth hard-blocker flag
   (covers the user's H1B concern).
4. **Tailoring at scale** — career-ops CV + cover-letter PDF pipeline, batched to
   produce 100+ tailored documents.
5. **Assisted apply** — UI surfaces the JD, the tailored PDF, and the apply link.
   One click opens the real apply page in a new tab; the human submits.
6. **Apple-designed frontend** — Next.js UI built with the
   `emilkowalski/skills/apple-design` skill (typography, motion, layout).

## 5. Data flow (happy path)

1. User uploads resume → structured profile stored.
2. User triggers a scan (target roles + locations) → source layer returns raw
   postings (career-ops scan + crawl4ai) → deduped into the tracker.
3. Evaluation runs (batched) → each posting gets an A–G report, a 1–5 score, a
   scam flag, and a work-auth flag.
4. For postings above threshold, tailoring generates a CV + cover-letter PDF.
5. Portal lists ranked jobs with score, flags, apply link, and download buttons.
6. User clicks assisted-apply → real page opens → user submits → marks status in
   tracker.

## 6. Error handling

- **Source failures** are per-source and non-fatal: a broken scraper/selector logs
  and the scan continues with the other sources (existing app already does this).
- **LLM/eval failures** are per-job and retried once; a failed job is surfaced with
  an error state, not dropped silently.
- **Subprocess failures** (career-ops) surface stderr to the API response and the
  activity log; the backend never assumes success.
- **OCR/parse failures** fall back to letting the user paste resume text manually.

## 7. Testing

- Unit: resume-extract schema validation; fit/flag parsing; crawl4ai adapter parsing
  (against saved HTML fixtures).
- Integration: FastAPI ↔ career-ops subprocess contract using a small fixture
  portal; end-to-end scan→eval→tailor on 2–3 sample jobs.
- Frontend: component render + the assisted-apply flow opens the correct URL and
  never auto-submits.

## 8. Prerequisites

Node ≥18, Python 3.11+, Playwright (career-ops), an LLM key (OpenRouter / OpenAI /
Anthropic / Ollama; the user's Anthropic path already exists). Runs locally.

## 9. Explicitly deferred (not v1)

- TencentDB-Agent-Memory — persistent agent memory; add after the core loop works.
- airllm + baidu/Unlimited-OCR — local large models / GPU OCR ("normal first").
- Panniantong/Agent-Reach — LinkedIn / company-contact research (uses user's own
  cookies); a research add-on after v1.
- 3b1b/manim — unrelated to a job portal.
- Multi-user, cloud DB, accounts — single local user in v1.

## 10. YAGNI / dropped for v1

No accounts, no cloud database, no auto-submit, no login-bypass, no local heavy
models. One local user, file-based state, Anthropic for reasoning.

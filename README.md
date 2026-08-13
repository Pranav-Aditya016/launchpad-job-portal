# LaunchPad

LaunchPad is a personal job-search portal: upload your resume once, and it scans a wide
range of public job boards, scores each role against your CV with LLM-driven reasoning
(not keyword matching), flags likely scams and no-sponsorship postings, tailors a CV and
cover letter per job, and gives you a one-click **assisted apply** — it opens the real
application page for you to submit yourself.

## Boundaries

- **Public, no-login sources only.** LaunchPad never logs into a job board or ATS on your
  behalf, and never bypasses authentication anywhere.
- **LaunchPad never submits an application for you.** The "Open apply page" button opens
  the real employer application page in a new browser tab; you review it and hit submit
  yourself. This is deliberate: bot-submitted applications get accounts banned and
  candidates silently filtered out by ATS fraud detection. LaunchPad's job is to get you
  to the door with the best possible material — walking through it is yours.

## Prerequisites

- **Node.js ≥ 18** (career-ops' `package.json` requires it)
- **Python ≥ 3.11**
- **git**
- **`ANTHROPIC_API_KEY`** — required for `/evaluate` (fit scoring) and `/tailor`
  (CV/cover-letter generation). Discovery/scanning (`/scan`) works fully **without** it.

## Setup

Run these from the repository root, in order.

### 1. Vendor the discovery engine (career-ops)

```powershell
pwsh scripts/setup-engine.ps1
```

This clones [`santifer/career-ops`](https://github.com/santifer/career-ops) into
`engine/career-ops` (vendored as plain files, no `.git`) and runs
`npm install --ignore-scripts` there — the `--ignore-scripts` skips career-ops' Playwright
Chromium download, which the reverse-ATS scanner doesn't need for a normal (non
`--liveness`) run.

If you'd rather do it manually:

```powershell
git clone --depth 1 https://github.com/santifer/career-ops.git engine/career-ops
Remove-Item -Recurse -Force engine/career-ops/.git
cd engine/career-ops
npm install --ignore-scripts
cd ../..
```

### 2. Backend

```powershell
cd backend
pip install -e ".[dev]"
cd ..
```

### 3. Frontend

```powershell
cd frontend
npm install
cd ..
```

### 4. Environment variables

Backend (set in your shell, or a `.env` the process picks up before you start uvicorn):

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes, for `/evaluate` and `/tailor` | Powers fit scoring and CV/cover-letter tailoring. `/scan` works without it. |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | No (opt-in) | Free key from [developer.adzuna.com](https://developer.adzuna.com/) — unlocks India/Germany/UK/US onshore listings via the Adzuna aggregator. If unset, Adzuna is silently skipped. |

Frontend — `frontend/.env.local` (already present in this repo):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Windows + PDF generation

The backend renders tailored-CV PDFs server-side with
[WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/), which needs the native
**GTK3 runtime** on Windows (Pango/Cairo, not a pure-Python dependency). **You do not need
this to use the app.** Without it:

- `import weasyprint` raises `OSError` at backend startup, which `app/api.py` catches —
  the API still starts and runs normally.
- `/tailor` still returns the tailored CV as markdown and the cover letter as text.
- The job page's **"Print / Save as PDF"** button uses the browser's own print dialog to
  produce a PDF from that markdown — no server-side rendering needed.

Installing GTK3 additionally enables server-side PDF *files* (the `pdf_url` /
`pdf_available` response fields and the in-page PDF preview). To enable it:

1. Install the GTK3 runtime for Windows:
   [GTK-for-Windows-Runtime-Environment-Installer releases](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)
2. See WeasyPrint's own Windows setup notes:
   [doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows)
3. Restart your terminal (and the backend) after installing so the new DLLs are on `PATH`.

## Running

```powershell
pwsh scripts/dev.ps1
```

This starts both servers. Or run them manually in two terminals:

```powershell
cd backend
python -m uvicorn app.api:app --reload --port 8000
```

```powershell
cd frontend
npm run dev
```

Then open **http://localhost:3000**.

## How to use it

1. **Upload your resume** on the home page (drag-and-drop, or paste raw text if parsing
   looks off). LaunchPad parses it into a structured profile (name, skills, target roles,
   experience).
2. **Review the parsed profile** — fix anything that looks thin or wrong before
   continuing; the profile drives both scanning and scoring.
3. Go to the **Dashboard**.
4. **Scan.** Set "Look back (days)" and hit "Scan for jobs". Two toggles:
   - **Fresher / entry-level only** (on by default) — filters to 0–2yr, internship,
     new-grad, and similarly early-career roles by title/description keywords
     (`app/sources/experience.py`). Turn it off to see everything a source returns.
   - **Include curated niche sources** (off by default) — adds h1bvisajobs, TrueUp, and
     Absolute Internship via best-effort crawling (see the Job sources table below for
     why this is opt-in).
5. **Evaluate all** — scores every unscored job against your profile with the LLM: a fit
   score, strengths/gaps, and scam / no-sponsorship flags. Requires `ANTHROPIC_API_KEY`.
6. **Open a job** to see the full evaluation, then:
   - **Tailor CV** — generates a CV and cover letter customized to that job (requires the
     job to be evaluated first).
   - **Open apply page** — opens the real employer application page in a new tab. You
     submit it yourself.

## Job sources

| Source | Mechanism | Coverage | Reliability |
|---|---|---|---|
| career-ops reverse-ATS scan | Vendored `scan-ats-full.mjs`, pure HTTP/JSON sweep | Greenhouse, Lever, Ashby, Workday, iCIMS — ~8,000 company boards | High — this is the primary, most reliable source |
| Remotive, Arbeitnow, RemoteOK, Jobicy, The Muse | Free public JSON APIs | Remote-friendly and general listings | High — official APIs, but each call is independently non-fatal so one provider being down never blocks the others |
| Adzuna | Official API, opt-in (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`) | India, Germany, UK, US onshore listings | High when configured; silently skipped otherwise |
| h1bvisajobs, TrueUp, Absolute Internship | `crawl4ai` markdown-link crawl, opt-in (`crawl_curated`) | Niche/visa-sponsor-friendly and internship listings | **Best-effort.** No public API, JS-heavy pages — extraction can pull navigation/footer noise alongside real listings. Absolute Internship is a paid placement program, not a standard board, so yield from it is expected to be low. These supplement, never replace, the sources above. |

Every per-source failure across all of these (career-ops, ad-hoc `crawl_urls`, curated
crawl, and each aggregator) is caught rather than failing the whole scan — a `/scan` call
always returns whatever succeeded, and reports what didn't in the response's `warnings`
list (e.g. `["careerops: RuntimeError: node not found"]`) so a failure is visible, not
silently swallowed.

## API reference

All endpoints live in `backend/app/api.py`.

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness check. |
| `POST /resume` | Upload a resume file (multipart `file`); parses and saves it as the profile. |
| `GET /profile` | Return the saved profile, or `null` if none uploaded. |
| `POST /scan` | Run discovery across all sources. Body: `ats: string[]?` (default `["greenhouse","lever","ashby","workday"]`), `since_days: int` (default `7`), `crawl_urls: {url, company}[]` (extra ad-hoc crawl targets), `aggregators: string[]?` (default all five), `fresher_only: bool` (default `true`), `crawl_curated: bool` (default `false`). Returns `{added, total, warnings}` — `warnings` is a list of short per-source failure strings (e.g. career-ops, a `crawl_urls` entry, or the aggregator leg failing); an empty list means every source that ran succeeded. |
| `GET /jobs` | List all stored jobs with their evaluation (if any), sorted by score descending. |
| `POST /evaluate` | Score jobs against the profile. Body: `job_ids: string[]?` (omit/`null` to evaluate all unscored jobs). Returns `{evaluated}`. Requires `ANTHROPIC_API_KEY`. |
| `POST /tailor/{job_id}` | Generate a tailored CV + cover letter for one evaluated job. Returns `{pdf_url, pdf_available, cover_letter, cv_markdown}`. Requires `ANTHROPIC_API_KEY`; `pdf_available` is `false` when WeasyPrint/GTK isn't installed. |
| `POST /apply/{job_id}` | Records that you applied and returns `{url}` — the real job URL — for the frontend to open. Never submits anything itself. |
| `GET /output/{job_id}.pdf` | Serves a previously rendered tailored-CV PDF. |

## Testing

```powershell
cd backend
python -m pytest
```

Current result on this machine (Windows, no GTK3 runtime installed):

```
34 passed, 3 skipped in 2.27s
```

The 3 skips are expected, not failures:

- **1 skip** — `tests/test_pdf.py::test_render_pdf` skips via
  `pytest.importorskip("weasyprint", exc_type=OSError)` because this machine has no GTK3
  runtime, so `import weasyprint` raises `OSError`. Install GTK3 (see above) to run it.
- **2 skips** — `tests/test_integration_aggregators.py` and
  `tests/test_integration_scan.py` are opt-in integration tests marked
  `@pytest.mark.integration` and skipped unless `RUN_INTEGRATION=1` is set, because they
  hit live network endpoints (the five public aggregator APIs, and a real `node
  scan-ats-full.mjs` invocation). Run them explicitly with:

  ```powershell
  $env:RUN_INTEGRATION=1
  python -m pytest -m integration -v
  ```

## Troubleshooting

- **`OSError` on `import weasyprint` / backend fails oddly around PDF rendering.** Expected
  without the GTK3 runtime — see "Windows + PDF generation" above. The rest of the app
  (including `/tailor`'s markdown output and the browser print-to-PDF flow) still works.
- **`/scan` returns 0 (or very few) jobs.** Try a larger `since_days` (widen the look-back
  window). Remember `fresher_only` filters aggressively by default — toggle it off to see
  everything. Individual aggregator APIs occasionally go down transiently; per-source
  failures are non-fatal, so a scan with one provider down still returns everything else.
- **`/evaluate` or `/tailor` return `500`.** Almost always a missing or invalid
  `ANTHROPIC_API_KEY` — `/scan` will still work fine without it, but scoring and tailoring
  need it.
- **First scan takes a long time.** career-ops' reverse-ATS sweep checks thousands of
  company boards (Greenhouse/Lever/Ashby/Workday) over HTTP; a first run of several
  minutes is normal, not a hang. The dashboard shows an elapsed-time indicator while it
  runs.

## Project layout

```
launchpad/
├── backend/            FastAPI app (Python)
│   └── app/
│       ├── api.py            all HTTP endpoints
│       ├── config.py         paths, LLM model config
│       ├── ingest/           resume parsing
│       ├── sources/          career-ops scan wrapper, aggregators, crawl, visa/experience filters
│       ├── evaluate/         LLM fit scoring + rubric
│       └── tailor/           CV/cover-letter generation + PDF rendering
├── frontend/           Next.js app (TypeScript)
│   └── app/                  upload → dashboard → job detail pages
├── engine/
│   └── career-ops/           vendored santifer/career-ops (gitignored contents beyond setup)
├── scripts/
│   ├── setup-engine.ps1      vendors + installs career-ops
│   └── dev.ps1                starts both dev servers
├── docs/                docs/specs for this build
└── launchpad_data/      gitignored runtime state — profile.json, jobs.json, evaluations/, output/
```

## Credits / licence

LaunchPad's discovery engine and scoring rubric are built on
[`santifer/career-ops`](https://github.com/santifer/career-ops) (MIT licence), vendored
into `engine/career-ops`. Niche-source crawling uses
[crawl4ai](https://github.com/unclecode/crawl4ai). Job data comes from the public APIs of
Remotive, Arbeitnow, RemoteOK, Jobicy, The Muse, and (opt-in) Adzuna, plus the ATS boards
career-ops sweeps directly (Greenhouse, Lever, Ashby, Workday, iCIMS).

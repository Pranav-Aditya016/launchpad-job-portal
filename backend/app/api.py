import asyncio
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import config, llm, store
from app.models import Profile
from app.evaluate import evaluator
from app.ingest import resume
from app.routes import (
    config as config_routes,
    connections as connections_routes,
    events as events_routes,
    queue as queue_routes,
    schedule as schedule_routes,
    sources as sources_routes,
)
from app.sources import aggregators, careerops_scan, crawl_adapter, experience, visa
from app.sources import registry
from app.tailor import writer

# `pdf` is either the weasyprint-backed module or None on a machine missing
# WeasyPrint's native GTK/Pango/Cairo stack — guarded once in app/tailor/__init__.py
# (a failed submodule import isn't cached in sys.modules, so re-guarding it here
# would re-run WeasyPrint's failing import and print its stderr banner again).
# `pdf` stays a module-level name here for monkeypatching; /tailor reports a
# clear 500 instead of crashing import when it's None.
from app.tailor import pdf

app = FastAPI(title="LaunchPad")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    """Never let an exception escape as a bare 500.

    FastAPI's default 500 is returned WITHOUT CORS headers, so a browser reports
    it as a network failure and the UI says "Can't reach the backend" — pointing
    the user at connectivity when the real fault is server-side. Returning JSON
    through the normal response path keeps CORS applied and shows the real error.
    """
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)[:300]}"},
    )

# Both loopback spellings: a browser may load the UI as localhost:3000 or
# 127.0.0.1:3000, and those are different Origins to CORS. Allowing only one
# makes every fetch fail with an opaque "backend not connected" in the UI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)

# Import every provider module so its @register runs before the first request.
registry.load_providers()

for _router in (
    config_routes.router, sources_routes.router, connections_routes.router,
    schedule_routes.router, queue_routes.router, events_routes.router,
):
    app.include_router(_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/resume")
async def upload_resume(file: UploadFile = File(...)):
    suffix = Path(file.filename or "resume").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        # resume.ingest does sync markitdown parsing + a sync Anthropic call;
        # run it off the event loop so a slow/large upload doesn't freeze
        # every other request for the duration of the call.
        try:
            profile = await asyncio.to_thread(resume.ingest, tmp_path)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            # Anything else (an unreadable/corrupt file, a missing markitdown
            # format extra, an OCR failure) must not escape as an unhandled
            # 500: FastAPI returns those WITHOUT CORS headers, so the browser
            # reports a network failure and the UI says "Can't reach the
            # backend" — pointing the user at the wrong problem entirely.
            detail = f"Couldn't read that resume file: {type(exc).__name__}: {str(exc)[:200]}"
            if "MissingDependency" in str(exc) or "MissingDependency" in type(exc).__name__:
                detail += (
                    " — this format needs an extra: pip install 'markitdown[all]'."
                    " You can also paste your resume text instead."
                )
            raise HTTPException(400, detail) from exc
        store.save_profile(profile)
    finally:
        tmp_path.unlink(missing_ok=True)
    return profile


@app.get("/profile")
def get_profile():
    return store.load_profile()


@app.put("/profile")
def put_profile(profile: Profile):
    """Save a profile directly — no LLM, no API key required.

    Two jobs: it persists edits the user makes on the review screen, and it is
    the keyless way to get started. Resume parsing needs ANTHROPIC_API_KEY, but
    job discovery does not, so a hand-filled profile is enough to scan and rank.
    """
    store.save_profile(profile)
    return profile


class CrawlUrl(BaseModel):
    url: str
    company: str


class ScanRequest(BaseModel):
    ats: list[str] | None = None
    since_days: int = 7
    crawl_urls: list[CrawlUrl] = []
    aggregators: list[str] | None = None
    fresher_only: bool = True
    crawl_curated: bool = False


def _short_error(prefix: str, e: Exception) -> str:
    return f"{prefix}: {type(e).__name__}: {str(e)[:120]}"


@app.post("/scan")
async def scan(req: ScanRequest = ScanRequest()):
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")

    jobs: list = []
    warnings: list[str] = []

    # career-ops reverse-ATS leg: runs a subprocess (Node) that can fail for
    # reasons outside our control (engine not vendored, Node missing, a
    # timeout, etc). Per spec §6 ("Source failures are per-source and
    # non-fatal") this must never take down the whole /scan request — catch
    # it, record a short warning, and keep going with whatever other sources
    # succeed.
    # An explicit empty `ats: []` means "skip the ATS sweep" — the fast path for
    # an aggregator-only scan that returns in seconds. `None` (the default) means
    # "use the default ATS set". Without this, [] would fall through run_scan's
    # `ats or DEFAULT_ATS` and silently sweep every board — the slowest possible
    # reading of a request that asked for none.
    if req.ats is None or len(req.ats) > 0:
        try:
            # run_scan shells out via subprocess.run(..., timeout=1200) — sync and
            # blocking. Run it in a worker thread so a multi-minute scan doesn't
            # freeze the event loop (and every other request) for its duration.
            jobs.extend(await asyncio.to_thread(careerops_scan.run_scan, profile, req.ats, req.since_days))
        except Exception as e:
            warnings.append(_short_error("careerops", e))

    # Ad-hoc crawl_urls the caller passed in: each is independently
    # non-fatal, same reasoning as the curated-source loop below.
    for cu in req.crawl_urls:
        try:
            jobs.extend(await crawl_adapter.fetch_jobs(cu.url, cu.company))
        except Exception as e:
            warnings.append(_short_error(f"crawl:{cu.url}", e))

    if req.crawl_curated:
        # Best-effort bonus sources (h1bvisajobs/trueup/absolute-internship) —
        # see the HONESTY comment on aggregators.CURATED_CRAWL_SOURCES: no
        # public API, JS-heavy, markdown-link extraction may be noisy. Each
        # site is independently non-fatal so one failing site never breaks
        # the rest of the scan. Default is False, so this never runs unless
        # the caller explicitly opts in.
        for src in aggregators.CURATED_CRAWL_SOURCES:
            try:
                curated_jobs = await crawl_adapter.fetch_jobs(src["url"], src["company"])
            except Exception as e:
                warnings.append(_short_error(f"crawl:{src['company']}", e))
                continue
            if src["company"] in aggregators.SPONSOR_FRIENDLY_SOURCES:
                # Tag so downstream visa.needs_sponsorship_ok recognizes
                # these as sponsor-friendly (source is otherwise "crawl4ai").
                for j in curated_jobs:
                    j.source = src["company"]
            jobs.extend(curated_jobs)

    if req.fresher_only:
        jobs = experience.experience_filter(jobs)

    try:
        agg_jobs = await aggregators.fetch_all(
            query=" ".join(profile.target_roles),
            providers=req.aggregators,
            fresher_only=req.fresher_only,
        )
    except Exception as e:
        # per-source failures are already swallowed inside fetch_all; this is a
        # final belt-and-suspenders guard so the aggregator leg can never break
        # an otherwise-successful career-ops/crawl scan (spec §6, non-fatal).
        agg_jobs = []
        warnings.append(_short_error("aggregators", e))
    jobs.extend(agg_jobs)

    added = store.upsert_jobs(jobs)
    return {"added": added, "total": len(store.load_jobs()), "warnings": warnings}


@app.get("/jobs")
def list_jobs():
    jobs = store.load_jobs()
    applied = store.applied_ids()
    result = []
    for j in jobs:
        ev = store.load_evaluation(j.id)
        d = j.model_dump()
        d["evaluation"] = ev.model_dump() if ev else None
        d["applied"] = j.id in applied
        # Visa-sponsorship SIGNAL (spec: user is an Indian citizen targeting
        # Germany/US/UK) — a primary ranking input, not a filter. See
        # app/sources/visa.py::needs_sponsorship_ok for the "not a hard gate"
        # contract.
        d["sponsorship_ok"] = visa.needs_sponsorship_ok(j, ev)
        result.append(d)

    def sort_key(d):
        ev = d["evaluation"]
        return (0, -ev["score"]) if ev else (1, 0)

    result.sort(key=sort_key)
    return result


class EvaluateRequest(BaseModel):
    job_ids: list[str] | None = None


@app.post("/evaluate")
def evaluate(req: EvaluateRequest = EvaluateRequest()):
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")

    jobs = store.load_jobs()
    if req.job_ids is not None:
        jobs = [j for j in jobs if j.id in req.job_ids]

    evaluated = 0
    failed = 0
    warnings: list[str] = []
    for j in jobs:
        if store.load_evaluation(j.id) is not None:
            continue
        try:
            e = evaluator.evaluate(profile, j)
        except RuntimeError as exc:
            # Config error (e.g. missing ANTHROPIC_API_KEY) — not a per-job
            # problem, it will fail identically for every remaining job.
            # Surface it immediately as a clean 400 instead of burning
            # through the whole batch first.
            raise HTTPException(400, str(exc)) from exc
        except Exception as e:
            failed += 1
            warnings.append(_short_error(f"evaluate:{j.id}", e))
            continue
        store.save_evaluation(e)
        evaluated += 1
    return {"evaluated": evaluated, "failed": failed, "warnings": warnings}


@app.post("/tailor/{job_id}")
def tailor(job_id: str):
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")

    job = next((j for j in store.load_jobs() if j.id == job_id), None)
    if job is None:
        raise HTTPException(404, "Job not found.")

    evaluation = store.load_evaluation(job_id)
    if evaluation is None:
        raise HTTPException(400, "Job has not been evaluated yet.")

    # The LLM tailoring is the core of this endpoint and only needs an LLM
    # call, not a PDF renderer — always produce it. PDF rendering is a
    # best-effort extra: attempt it only when the renderer imported
    # successfully, and never let a renderer failure (missing native GTK
    # libs, etc.) take down the whole request. See the `pdf` import guard
    # at the top of this module.
    try:
        doc = writer.tailor(profile, job, evaluation)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc

    pdf_url = None
    pdf_available = False
    if pdf is not None:
        try:
            pdf.render_cv_pdf(doc, config.OUTPUT_DIR / f"{job_id}.pdf")
        except Exception:
            pass
        else:
            pdf_url = f"/output/{job_id}.pdf"
            pdf_available = True

    return {
        "pdf_url": pdf_url,
        "cover_letter": doc.cover_letter,
        "cv_markdown": doc.cv_markdown,
        "pdf_available": pdf_available,
    }


@app.post("/apply/{job_id}")
def apply(job_id: str):
    # SAFETY: this endpoint MUST NEVER submit an application on the user's
    # behalf. It only records that the human applied and hands back the real
    # apply URL for them to open themselves.
    job = next((j for j in store.load_jobs() if j.id == job_id), None)
    if job is None:
        raise HTTPException(404, "Job not found.")

    store.mark_applied(job_id)
    return {"url": job.url}


@app.get("/output/{job_id}.pdf")
def get_output_pdf(job_id: str):
    path = config.OUTPUT_DIR / f"{job_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "PDF not found.")
    return FileResponse(path, media_type="application/pdf")

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import config, store
from app.evaluate import evaluator
from app.ingest import resume
from app.sources import aggregators, careerops_scan, crawl_adapter, experience
from app.tailor import writer

try:
    # WeasyPrint imports its native GTK/Pango/Cairo stack at import time.
    # On machines missing those native libs (e.g. this Windows dev box),
    # `import weasyprint` raises OSError rather than ImportError. We still
    # want the rest of the API (and its tests) to import and run fine, so
    # `pdf` stays a module-level name for monkeypatching but degrades to
    # None here — /tailor reports a clear 500 instead of crashing import.
    from app.tailor import pdf
except OSError:
    pdf = None

app = FastAPI(title="LaunchPad")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])


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
        profile = resume.ingest(tmp_path)
        store.save_profile(profile)
    finally:
        tmp_path.unlink(missing_ok=True)
    return profile


@app.get("/profile")
def get_profile():
    return store.load_profile()


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


@app.post("/scan")
async def scan(req: ScanRequest = ScanRequest()):
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")

    jobs = careerops_scan.run_scan(profile, req.ats, req.since_days)
    for cu in req.crawl_urls:
        jobs.extend(await crawl_adapter.fetch_jobs(cu.url, cu.company))

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
            except Exception:
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
    except Exception:
        # per-source failures are already swallowed inside fetch_all; this is a
        # final belt-and-suspenders guard so the aggregator leg can never break
        # an otherwise-successful career-ops/crawl scan (spec §6, non-fatal).
        agg_jobs = []
    jobs.extend(agg_jobs)

    added = store.upsert_jobs(jobs)
    return {"added": added, "total": len(store.load_jobs())}


@app.get("/jobs")
def list_jobs():
    jobs = store.load_jobs()
    result = []
    for j in jobs:
        ev = store.load_evaluation(j.id)
        d = j.model_dump()
        d["evaluation"] = ev.model_dump() if ev else None
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

    count = 0
    for j in jobs:
        if store.load_evaluation(j.id) is None:
            e = evaluator.evaluate(profile, j)
            store.save_evaluation(e)
            count += 1
    return {"evaluated": count}


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

    if pdf is None:
        raise HTTPException(500, "PDF rendering is unavailable in this environment.")

    doc = writer.tailor(profile, job, evaluation)
    pdf.render_cv_pdf(doc, config.OUTPUT_DIR / f"{job_id}.pdf")
    return {"pdf_url": f"/output/{job_id}.pdf", "cover_letter": doc.cover_letter}


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

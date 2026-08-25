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

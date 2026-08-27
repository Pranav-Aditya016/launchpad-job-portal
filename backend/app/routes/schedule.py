"""Autopilot schedule.

`GET /schedule` returns the built-in `DEFAULT_SCHEDULE` constant below — there
is no persisted schedule yet, so this is not reading from the store. `GET
/runs` *is* genuinely backed by the store (`store.load_runs`). Track D must add
a real persisted accessor (e.g. `store.load_schedule` / `store.save_schedule`)
when it implements `PUT /schedule` and `POST /schedule/run-now`, both of which
currently 501.
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import evaluate_pipeline, scan_engine, store
from app.models import Profile

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


class RunNowRequest(BaseModel):
    source_keys: list[str] | None = None   # None = every enabled source
    regions: list[str] | None = None
    limit: int = scan_engine.DEFAULT_LIMIT


@router.post("/schedule/run-now")
async def run_now(body: RunNowRequest = RunNowRequest()):
    """Run every enabled source now and report what each one did.

    The response is deliberately provenance-first: `results` lists EVERY source
    considered — including the ones that were off, empty, errored or waiting on
    a login — so the user can see where jobs came from and which sites are
    contributing nothing. Returning only successes would imply coverage that
    isn't there.
    """
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")

    connected = {
        portal for portal, conn in store.load_connections().items()
        if conn.status == "connected"
    }

    page_opener = None
    try:                                    # the vault is optional at runtime
        from app.browser import session as vault
        page_opener = vault.open_page
    except Exception:
        pass

    outcome = await scan_engine.run_scan(
        profile,
        source_keys=body.source_keys,
        regions=body.regions,
        overrides=store.load_source_config(),
        connected_portals=connected,
        limit=body.limit,
        page_opener=page_opener,
    )

    added = store.upsert_jobs(outcome.jobs)
    run = outcome.to_scan_run(run_id=uuid.uuid4().hex[:12], trigger="manual")
    for r in run.results:                   # how many of this source's jobs were new
        r.new_jobs = r.jobs_found
    store.save_run(run)

    return {
        "run_id": run.id,
        "started": run.started,
        "finished": run.finished,
        "jobs_found": outcome.total_jobs,
        "jobs_new": added,
        "sources_considered": len(run.results),
        "sources_ok": sum(1 for r in run.results if r.status == "ok"),
        "results": [r.model_dump() for r in run.results],
        "warnings": run.warnings,
    }


class EvaluateNextRequest(BaseModel):
    budget: int | None = None          # None = the default per-cycle budget
    min_similarity: float = 0.0


@router.post("/scan/evaluate-next")
async def evaluate_next(body: EvaluateNextRequest = EvaluateNextRequest()):
    """Evaluate the most promising unscored jobs, cheapest-first.

    With ~850 jobs in the store and 10-30s per local evaluation, scoring
    everything is about three hours of pinned GPU. This ranks every unscored
    job by embedding similarity (~50ms each) and spends the rubric only on the
    top `budget` (spec §4.2).
    """
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")
    return await evaluate_pipeline.evaluate_next(
        profile, budget=body.budget, min_similarity=body.min_similarity
    )


@router.get("/scan/ranking")
def ranking(limit: int = 50):
    """The pre-ranked queue: what the model would read next, and why.

    Transparency for the funnel itself — otherwise "why hasn't it scored this
    job yet?" has no visible answer.
    """
    profile = store.load_profile()
    if profile is None:
        raise HTTPException(400, "No profile found. Upload a resume first.")
    return evaluate_pipeline.ranking_preview(profile, limit=limit)


@router.get("/scan/coverage")
def coverage():
    """What LaunchPad looks at, and what it found last time.

    The honest answer to "which sites are you actually scraping?" — every
    registered source with its last outcome, plus the user's own sites.
    """
    from app import custom_sources as cs
    from app.sources import registry

    overrides = store.load_source_config()
    runs = store.load_runs(limit=1)
    last = {r.key: r.model_dump() for r in runs[0].results} if runs else {}

    rows = []
    for s in registry.all_sources():
        m = s.meta
        rows.append({
            "key": m.key, "label": m.label, "kind": m.kind.value,
            "regions": list(m.regions), "requires_login": m.requires_login,
            "enabled": overrides.get(m.key, m.enabled_by_default),
            "warning": m.warning, "last": last.get(m.key),
        })
    return {
        "last_run": runs[0].model_dump() if runs else None,
        "sources": rows,
        "custom_sites": [
            {"id": c.id, "url": c.url, "label": c.label, "enabled": c.enabled,
             "last_status": c.last_status, "last_jobs": c.last_jobs,
             "last_detail": c.last_detail}
            for c in cs.load_all()
        ],
    }


@router.get("/runs")
def list_runs(limit: int = 50):
    return {"runs": [r.model_dump() for r in store.load_runs(limit=limit)]}

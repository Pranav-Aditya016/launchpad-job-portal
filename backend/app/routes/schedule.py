"""Autopilot schedule.

`GET /schedule` returns the built-in `DEFAULT_SCHEDULE` constant below — there
is no persisted schedule yet, so this is not reading from the store. `GET
/runs` *is* genuinely backed by the store (`store.load_runs`). Track D must add
a real persisted accessor (e.g. `store.load_schedule` / `store.save_schedule`)
when it implements `PUT /schedule` and `POST /schedule/run-now`, both of which
currently 501.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store

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


@router.post("/schedule/run-now")
def run_now():
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.get("/runs")
def list_runs(limit: int = 50):
    return {"runs": [r.model_dump() for r in store.load_runs(limit=limit)]}

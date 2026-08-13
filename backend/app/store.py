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

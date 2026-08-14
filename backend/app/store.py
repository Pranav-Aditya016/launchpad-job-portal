"""File-based persistence for the single local user.

Two invariants, both learned the hard way:

**Writes are atomic.** A plain `write_text` truncates the target before writing,
so an interrupted or concurrent write leaves a 0-byte file. That happened to
`profile.json` in real use and every later read raised a pydantic
ValidationError — surfacing as an unhandled 500 and, because FastAPI returns
those without CORS headers, as "Can't reach the backend" in the UI. We write to
a temp file in the same directory and `os.replace` it into place, which is
atomic on POSIX and Windows.

**Reads tolerate corruption.** If a file is somehow still empty or unparseable,
readers treat it as absent rather than raising. Losing a cached scan and being
asked to re-upload is recoverable; a hard 500 on every request is not.
"""

import json
import os
import tempfile
from pathlib import Path

from app import config as cfg
from app.models import Evaluation, Job, Profile


def _p(name: str) -> Path:
    return cfg.DATA_DIR / name


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same directory as the target: os.replace is only atomic within a filesystem.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())  # durable before the rename
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_text(path: Path) -> str | None:
    """File contents, or None if missing/empty (treated as 'not written yet')."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def save_profile(p: Profile) -> None:
    _write_atomic(_p("profile.json"), p.model_dump_json(indent=2))


def load_profile() -> Profile | None:
    text = _read_text(_p("profile.json"))
    if text is None:
        return None
    try:
        return Profile.model_validate_json(text)
    except Exception:
        return None  # corrupt: behave as "no profile yet", don't 500 every request


def load_jobs() -> list[Job]:
    text = _read_text(_p("jobs.json"))
    if text is None:
        return []
    try:
        return [Job(**j) for j in json.loads(text)]
    except Exception:
        return []


def upsert_jobs(jobs: list[Job]) -> int:
    existing = {j.id: j for j in load_jobs()}
    added = 0
    for j in jobs:
        if j.id not in existing:
            existing[j.id] = j
            added += 1
    _write_atomic(
        _p("jobs.json"),
        json.dumps([j.model_dump() for j in existing.values()], indent=2),
    )
    return added


def save_evaluation(e: Evaluation) -> None:
    _write_atomic(cfg.EVAL_DIR / f"{e.job_id}.json", e.model_dump_json(indent=2))


def load_evaluation(job_id: str) -> Evaluation | None:
    text = _read_text(cfg.EVAL_DIR / f"{job_id}.json")
    if text is None:
        return None
    try:
        return Evaluation.model_validate_json(text)
    except Exception:
        return None


def applied_ids() -> set[str]:
    text = _read_text(_p("applied_log.json"))
    if text is None:
        return set()
    try:
        return set(json.loads(text))
    except Exception:
        return set()


def mark_applied(job_id: str) -> None:
    ids = applied_ids()
    ids.add(job_id)
    _write_atomic(_p("applied_log.json"), json.dumps(sorted(ids)))

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
import shutil
import tempfile
from pathlib import Path

from app import config as cfg
from app.models import Connection, Evaluation, Job, Profile, QueueItem, ScanRun


def _p(name: str) -> Path:
    return cfg.DATA_DIR / name


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkdir first: free_disk_gb() calls shutil.disk_usage(DATA_DIR), which raises
    # FileNotFoundError if that directory doesn't exist yet.
    assert_disk_headroom()
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
    """File contents, or None if missing/empty (treated as 'not written yet').

    Files written before this module specified an encoding were saved in the
    Windows default (cp1252), so a UTF-8-only read raises UnicodeDecodeError on
    an em-dash in a job description. Fall back rather than lose the data — new
    writes are always UTF-8, so these files heal on the next save.
    """
    if not path.exists():
        return None
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding).strip()
            return text or None
        except UnicodeDecodeError:
            continue
    return None


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


# --- v2 -------------------------------------------------------------------
#
# Same two invariants as v1: writes are atomic, reads tolerate corruption. A
# corrupt cache costs a rescan; a hard 500 on every request costs the product.

MAX_RUNS = 200          # spec §12.4 — bounded history
MIN_FREE_DISK_GB = 2.0  # spec §12.4 — never fill the system disk


def free_disk_gb() -> float:
    return shutil.disk_usage(str(cfg.DATA_DIR)).free / (1024 ** 3)


def assert_disk_headroom() -> None:
    """Refuse to write when the disk is nearly full.

    A skipped scan is recoverable. A full Windows system disk is not.

    Enforced centrally in `_write_atomic` (spec §12.4: "All writes abort if free
    disk is under 2 GB" — unconditionally, for every writer in this module, not
    just the v2 accessors). Do not re-add per-call-site invocations of this
    function elsewhere; that would just duplicate the check `_write_atomic`
    already makes on every write.
    """
    free = free_disk_gb()
    if free < MIN_FREE_DISK_GB:
        raise RuntimeError(
            f"Only {free:.1f} GB free on the LaunchPad data disk "
            f"(need {MIN_FREE_DISK_GB:.1f} GB). Free some space and rerun."
        )


def _read_json(name: str, default):
    text = _read_text(_p(name))
    if text is None:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def load_connections() -> dict[str, Connection]:
    """Portal -> Connection. Never contains a credential (spec §6.3)."""
    out: dict[str, Connection] = {}
    for raw in _read_json("connections.json", []):
        try:
            c = Connection(**raw)
        except Exception:
            continue   # one bad record must not hide the rest
        out[c.portal] = c
    return out


def save_connection(conn: Connection) -> None:
    conns = load_connections()
    conns[conn.portal] = conn
    _write_atomic(
        _p("connections.json"),
        json.dumps([c.model_dump() for c in conns.values()], indent=2),
    )


def delete_connection(portal: str) -> None:
    conns = load_connections()
    if conns.pop(portal, None) is None:
        return
    _write_atomic(
        _p("connections.json"),
        json.dumps([c.model_dump() for c in conns.values()], indent=2),
    )


def load_queue() -> list[QueueItem]:
    items = []
    for raw in _read_json("queue.json", []):
        try:
            items.append(QueueItem(**raw))
        except Exception:
            continue
    return items


def upsert_queue_item(item: QueueItem) -> None:
    """Insert or replace by job_id, preserving insertion order."""
    items = load_queue()
    for i, existing in enumerate(items):
        if existing.job_id == item.job_id:
            items[i] = item
            break
    else:
        items.append(item)
    _write_atomic(
        _p("queue.json"), json.dumps([i.model_dump() for i in items], indent=2)
    )


def _runs_path() -> Path:
    d = cfg.DATA_DIR / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "runs.json"


def save_run(run: ScanRun) -> None:
    runs = load_runs(limit=MAX_RUNS)
    runs = [r for r in runs if r.id != run.id]
    runs.insert(0, run)                       # newest first
    del runs[MAX_RUNS:]                       # bounded history
    _write_atomic(_runs_path(), json.dumps([r.model_dump() for r in runs], indent=2))


def load_runs(limit: int = 50) -> list[ScanRun]:
    text = _read_text(_runs_path())
    if text is None:
        return []
    try:
        raw = json.loads(text)
    except Exception:
        return []
    out = []
    for r in raw[:limit]:
        try:
            out.append(ScanRun(**r))
        except Exception:
            continue
    return out


def load_source_config() -> dict[str, bool]:
    """User's explicit per-source on/off overrides. Absent key = use the default."""
    raw = _read_json("sources.json", {})
    return {k: bool(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def set_source_enabled(key: str, enabled: bool) -> None:
    cfgmap = load_source_config()
    cfgmap[key] = bool(enabled)
    _write_atomic(_p("sources.json"), json.dumps(cfgmap, indent=2))


def load_embeddings() -> dict[str, list[float]]:
    raw = _read_json("embeddings.json", {})
    return raw if isinstance(raw, dict) else {}


def save_embeddings(vectors: dict[str, list[float]]) -> None:
    _write_atomic(_p("embeddings.json"), json.dumps(vectors))

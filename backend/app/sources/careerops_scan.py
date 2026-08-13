"""Wraps the vendored career-ops `scan-ats-full.mjs` reverse-ATS scanner.

`parse_scan_output` is a pure function operating on the NORMALIZED job shape
(`{company, title, location, url, posted, source, description}`) — the same
shape as `backend/tests/fixtures/scan_sample.json` — and is unit-tested with
no network/Node dependency.

`run_scan` is the impure orchestrator: it writes `portals.yml` (required by
the engine even for a reverse sweep — see task-4-report.md), invokes the
Node scanner with `--json`, and maps its RAW offer objects to the normalized
shape before delegating to `parse_scan_output`.
"""

import json
import subprocess
from pathlib import Path

from app import config as cfg
from app.models import Job, job_id
from app.sources.portals import write_portals_yml

DEFAULT_ATS = ["greenhouse", "lever", "ashby", "workday"]


def parse_scan_output(raw: str | Path) -> list[Job]:
    """Parse the NORMALIZED scan-output shape (str JSON or a Path to it) into Jobs."""
    data = json.loads(Path(raw).read_text() if isinstance(raw, Path) else raw)
    jobs = []
    for r in data:
        url = r.get("url", "")
        src = r.get("source", "careerops")
        company = r.get("company", "")
        jobs.append(
            Job(
                id=job_id(src, company, url),
                source=src,
                company=company,
                title=r.get("title", ""),
                location=r.get("location", ""),
                url=url,
                description=r.get("description", ""),
                posted=r.get("posted"),
            )
        )
    return jobs


def _normalize_raw_offers(raw_offers: list[dict]) -> list[dict]:
    """Map RAW `scan-ats-full.mjs --json` offer objects to the normalized shape.

    Per task-4-report.md ("Real fields observed"), each raw offer object emitted
    on stdout by `--json` has exactly these keys (verified against
    `scan-ats-full.mjs:1039-1049`):

        company, title, url, location, postedAt (YYYY-MM-DD string or null),
        dateStatus ("dated"/"unknown"), blacklisted (bool), note (string|null), source

    Mapping applied here (raw -> normalized):
        company    -> company
        title      -> title
        location   -> location
        url        -> url
        postedAt   -> posted
        source     -> source (observed value: "greenhouse-full")
        (none)     -> description = "" (task-4-report.md confirms no description
                      field exists anywhere in this data path for greenhouse;
                      other ATS sources were not exercised in Task 4, so we do
                      not assume one is present for them either)

    `dateStatus`, `blacklisted`, and `note` are not part of the normalized
    Job shape and are dropped.
    """
    normalized = []
    for offer in raw_offers:
        normalized.append(
            {
                "company": offer.get("company", ""),
                "title": offer.get("title", ""),
                "location": offer.get("location", ""),
                "url": offer.get("url", ""),
                "posted": offer.get("postedAt"),
                "source": offer.get("source", "careerops"),
                "description": "",
            }
        )
    return normalized


def run_scan(profile, ats: list[str] | None = None, since_days: int = 7) -> list[Job]:
    """Run the career-ops reverse-ATS scan for `profile` and return normalized Jobs.

    Writes `portals.yml` into ENGINE_DIR before invoking the scanner (required —
    see `write_portals_yml`/task-4-report.md), then runs `scan-ats-full.mjs
    --json` and parses its stdout, mapping RAW offer fields to the normalized
    shape per `_normalize_raw_offers` (sourced from task-4-report.md's
    characterization of the `--json` output).
    """
    ats = ats or DEFAULT_ATS
    write_portals_yml(profile, cfg.ENGINE_DIR / "portals.yml")

    result = subprocess.run(
        ["node", "scan-ats-full.mjs", "--ats", ",".join(ats), "--since", str(since_days), "--json"],
        cwd=cfg.ENGINE_DIR,
        capture_output=True,
        text=True,
        timeout=1200,
        check=True,
    )

    raw_offers = json.loads(result.stdout)
    normalized = _normalize_raw_offers(raw_offers)
    return parse_scan_output(json.dumps(normalized))

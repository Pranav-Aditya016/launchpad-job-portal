"""Writes the career-ops engine's `portals.yml` config from a LaunchPad Profile.

The vendored `scan-ats-full.mjs` (Task 4) hard-errors without a `portals.yml`
present in its working directory, even for a pure reverse/full-ATS sweep — it
only reads `title_filter`/`location_filter` (and other filter keys) from it,
not `tracked_companies` (see task-4-report.md).
"""

from pathlib import Path


def write_portals_yml(profile, dest: Path) -> None:
    """Render a minimal portals.yml for the given profile at `dest`."""
    titles = "|".join(r.strip() for r in profile.target_roles) or ".*"
    loc = profile.location or ""
    dest.write_text(
        f'title_filter: "{titles}"\n'
        f'location_filter: "{loc}"\n'
        "companies: []\n"
    )

"""Writes the career-ops engine's `portals.yml` config from a LaunchPad Profile.

The vendored `scan-ats-full.mjs` (Task 4) hard-errors without a `portals.yml`
present in its working directory, even for a pure reverse/full-ATS sweep — it
only reads `title_filter`/`location_filter` (and other filter keys) from it,
not `tracked_companies` (see task-4-report.md).
"""

import re
from pathlib import Path

import yaml


def write_portals_yml(profile, dest: Path) -> None:
    """Render a minimal portals.yml for the given profile at `dest`."""
    # title_filter is joined into a `|`-alternation regex, so any role
    # containing regex-special characters (e.g. "C++", "Node.js (backend)")
    # must be escaped first or it corrupts/crashes the downstream regex.
    titles = "|".join(re.escape(r.strip()) for r in profile.target_roles) or ".*"
    loc = profile.location or ""
    # Use a real YAML dumper instead of splicing values into a hand-written
    # quoted string — safe_dump escapes quotes/colons/newlines/etc for us, so
    # a role or location containing them can't break the file's syntax.
    data = {
        "title_filter": titles,
        "location_filter": loc,
        "companies": [],
    }
    dest.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))

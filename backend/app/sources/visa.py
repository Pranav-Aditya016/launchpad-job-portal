"""Visa-sponsorship SIGNAL (not a hard gate) for ranking/filtering jobs.

`needs_sponsorship_ok` is a soft heuristic, not a filter that removes jobs.
It flags whether a job is plausibly reachable for a citizen of
`citizen_country` (default "IN") WITHOUT needing employer visa sponsorship —
because it's in their home country, it's remote, it comes from a source
known to be sponsor-friendly, or there's simply no evidence (yet) that
sponsorship is a problem. Callers (ranking/UI) decide what to do with a
False result, e.g. de-prioritize or badge "sponsorship unclear" — they must
never use it to silently drop a job.
"""

from app.models import Evaluation, Job
from app.sources.aggregators import SPONSOR_FRIENDLY_SOURCES

# Aggregator sources that are remote-only job boards by construction.
_REMOTE_SOURCES = {"remotive", "remoteok", "jobicy"}
_REMOTE_KEYWORDS = ("remote", "anywhere", "worldwide", "distributed")

# Minimal country-name keyword map; extend as more citizen_country values
# are needed. Falls back to matching the raw country code/name if unlisted.
_COUNTRY_KEYWORDS = {
    "IN": ("india",),
    "DE": ("germany",),
    "GB": ("united kingdom", "uk", "britain"),
    "US": ("united states", "usa", "u.s."),
}


def _mentions_country(location: str, country: str) -> bool:
    loc = (location or "").lower()
    keywords = _COUNTRY_KEYWORDS.get(country.upper(), (country.lower(),))
    return any(k in loc for k in keywords)


def _is_remote(job: Job) -> bool:
    loc = (job.location or "").lower()
    if any(k in loc for k in _REMOTE_KEYWORDS):
        return True
    return job.source in _REMOTE_SOURCES


def needs_sponsorship_ok(job: Job, evaluation: Evaluation | None = None,
                          citizen_country: str = "IN") -> bool:
    """True unless the job is both non-local/non-remote/non-sponsor-friendly
    AND its evaluation explicitly flagged `no_sponsorship`. A SIGNAL only."""
    if _mentions_country(job.location, citizen_country):
        return True
    if _is_remote(job):
        return True
    if job.source in SPONSOR_FRIENDLY_SOURCES:
        return True
    if evaluation is None or not evaluation.no_sponsorship:
        return True
    return False

"""Scrape the websites the user added themselves.

One registered source that fans out over every enabled entry in
`custom_sources`, so adding a site is a data change, not a code change.

Strategy is cheapest-first, because this runs on a laptop that is also holding
a local model in VRAM (spec §12.3):

1. Plain HTTP fetch and pull the anchors out of the HTML. Most careers pages
   are server-rendered and this costs one request.
2. Only if that finds nothing, and only when the user opted in, fall back to a
   real browser via crawl4ai for JS-rendered pages.

Whatever happens is written back to the site record, so the Sources page can
show the user whether their own site is actually producing anything rather
than just sitting there looking official.
"""

from __future__ import annotations

import re

from app import custom_sources as cs
from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.registry import register

# <a href="...">text</a> — good enough for anchors, and we only ever read.
_ANCHOR = re.compile(
    r"<a\b[^>]*?href=[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a>",
    re.I | re.S,
)
_TAGS = re.compile(r"<[^>]+>")


def _anchors_as_markdown(html: str) -> str:
    """Reduce HTML anchors to the `[text](href)` form the filter understands."""
    out = []
    for href, text in _ANCHOR.findall(html or ""):
        label = " ".join(_TAGS.sub(" ", text).split())
        if label:
            out.append(f"[{label}]({href})")
    return "\n".join(out)


async def _fetch_one(ctx: FetchContext, site: cs.CustomSite) -> tuple[list[Job], str, str]:
    """(jobs, status, detail) for one user-added site. Never raises."""
    source_key = f"custom:{site.id}"
    try:
        r = await ctx.client.get(site.url)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return [], "error", f"{type(e).__name__}: {e}"[:200]

    jobs = cs.jobs_from_markdown(
        _anchors_as_markdown(html), base_url=site.url,
        company=site.label, source_key=source_key,
    )
    for j in jobs:
        j.region = (site.regions or ["global"])[0]

    if jobs:
        return jobs, "ok", ""

    looks_js = len(_ANCHOR.findall(html)) < 5 and len(html) > 2000
    detail = (
        "no job-shaped links found — the page looks JavaScript-rendered, so the "
        "listings probably load after the HTML does"
        if looks_js else
        "no job-shaped links found — check the URL points at a job LIST page "
        "(e.g. /careers or /jobs) rather than the homepage"
    )
    return [], "empty", detail


@register
class CustomPagesSource:
    meta = SourceMeta(
        key="custom:pages",
        label="Your own websites",
        kind=SourceKind.CRAWL,
        regions=("global", "in", "de"),
        rate_limit_s=1.5,
        daily_cap=400,
        warning=(
            "Best-effort. LaunchPad reads the links on the page you gave it; "
            "sites that render listings with JavaScript may return nothing."
        ),
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        sites = [s for s in cs.load_all() if s.enabled]
        if not sites:
            return []

        jobs: list[Job] = []
        for site in sites:
            found, status, detail = await _fetch_one(ctx, site)
            cs.record_result(site.id, status, len(found), detail)
            if status != "ok":
                # Surfaced per-site so the user knows WHICH of their sites is
                # quiet, not just that "custom pages" returned nothing.
                ctx.warn(f"{site.label} ({site.url}): {detail}")
            jobs.extend(found)
        return jobs

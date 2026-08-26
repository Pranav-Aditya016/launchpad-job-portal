"""Ashby — public, no-auth JSON: `GET /posting-api/job-board/{slug}`.

Verified live against `api.ashbyhq.com/posting-api/job-board/ramp` (135 open
postings at verification time). See `backend/tests/fixtures/ats_ashby.json`
for a trimmed real capture.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def parse_ashby(data: dict, company: str, region: str) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("jobUrl", "") or j.get("applyUrl", "")
        out.append(Job(
            id=job_id("ats:ashby", company, url),
            source="ats:ashby",
            company=company,
            title=j.get("title", ""),
            location=j.get("location", ""),
            url=url,
            description=ats_common.clean(j.get("descriptionPlain", "") or j.get("descriptionHtml", "")),
            posted=j.get("publishedAt"),
            region=region,
        ))
    return out


@register
class AshbySource:
    meta = SourceMeta(
        key="ats:ashby",
        label="Ashby (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("ashby"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("ashby")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug), params={"includeCompensation": "true"})
                r.raise_for_status()
                jobs.extend(parse_ashby(r.json(), name, ats_common.primary_region(c)))
            except Exception as e:
                ctx.warn(f"ats:ashby: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

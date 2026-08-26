"""Greenhouse — the single biggest ATS by tracked-employer share (~19-49%).

Public, no-auth JSON: `GET /v1/boards/{slug}/jobs?content=true`. Verified live
against `boards-api.greenhouse.io/v1/boards/databricks/jobs` (831 open postings
at verification time). See `backend/tests/fixtures/ats_greenhouse.json` for a
trimmed real capture.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def parse_greenhouse(data: dict, company: str, region: str) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("absolute_url", "")
        out.append(Job(
            id=job_id("ats:greenhouse", company, url),
            source="ats:greenhouse",
            company=company,
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=url,
            description=ats_common.clean(j.get("content", "")),
            posted=j.get("updated_at"),
            region=region,
        ))
    return out


@register
class GreenhouseSource:
    meta = SourceMeta(
        key="ats:greenhouse",
        label="Greenhouse (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("greenhouse"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("greenhouse")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug), params={"content": "true"})
                r.raise_for_status()
                jobs.extend(parse_greenhouse(r.json(), name, ats_common.primary_region(c)))
            except Exception as e:
                ctx.warn(f"ats:greenhouse: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

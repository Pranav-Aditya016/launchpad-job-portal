"""Workable — public, no-auth JSON widget: `GET /api/v1/widget/accounts/{slug}`.

Verified live against `apply.workable.com/api/v1/widget/accounts/huggingface`
(7 open postings at verification time). See
`backend/tests/fixtures/ats_workable.json` for a trimmed real capture.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://apply.workable.com/api/v1/widget/accounts/{slug}"


def parse_workable(data: dict, company: str, region: str) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("url", "") or j.get("shortlink", "")
        loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
        out.append(Job(
            id=job_id("ats:workable", company, url),
            source="ats:workable",
            company=company,
            title=j.get("title", ""),
            location=loc,
            url=url,
            description=ats_common.clean(j.get("description", "")),
            posted=j.get("published_on") or j.get("created_at"),
            region=region,
        ))
    return out


@register
class WorkableSource:
    meta = SourceMeta(
        key="ats:workable",
        label="Workable (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("workable"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("workable")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug), params={"details": "true"})
                r.raise_for_status()
                jobs.extend(parse_workable(r.json(), name, ats_common.primary_region(c)))
            except Exception as e:
                ctx.warn(f"ats:workable: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

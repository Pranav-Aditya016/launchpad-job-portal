"""Recruitee — public, no-auth JSON: `GET https://{slug}.recruitee.com/api/offers/`.

Verified live against `helloprint.recruitee.com/api/offers/` (4 open postings
at verification time). See `backend/tests/fixtures/ats_recruitee.json` for a
trimmed real capture.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://{slug}.recruitee.com/api/offers/"


def parse_recruitee(data: dict, company: str, region: str) -> list[Job]:
    out = []
    for j in data.get("offers", []):
        url = j.get("careers_apply_url", "") or j.get("careers_url", "")
        loc = j.get("location", "") or ", ".join(
            x for x in (j.get("city"), j.get("country")) if x
        )
        out.append(Job(
            id=job_id("ats:recruitee", company, url),
            source="ats:recruitee",
            company=company,
            title=j.get("title", ""),
            location=loc,
            url=url,
            description=ats_common.clean(j.get("description", "")),
            posted=j.get("published_at") or j.get("created_at"),
            region=region,
        ))
    return out


@register
class RecruiteeSource:
    meta = SourceMeta(
        key="ats:recruitee",
        label="Recruitee (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("recruitee"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("recruitee")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug))
                r.raise_for_status()
                jobs.extend(parse_recruitee(r.json(), name, ats_common.primary_region(c)))
            except Exception as e:
                ctx.warn(f"ats:recruitee: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

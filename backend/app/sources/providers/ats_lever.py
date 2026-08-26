"""Lever — public, no-auth JSON: `GET /v0/postings/{slug}?mode=json`.

Verified live against `api.lever.co/v0/postings/spotify` (89 open postings at
verification time). See `backend/tests/fixtures/ats_lever.json` for a trimmed
real capture.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://api.lever.co/v0/postings/{slug}"


def parse_lever(data: list, company: str, region: str) -> list[Job]:
    out = []
    for j in data:
        url = j.get("hostedUrl", "") or j.get("applyUrl", "")
        categories = j.get("categories") or {}
        out.append(Job(
            id=job_id("ats:lever", company, url),
            source="ats:lever",
            company=company,
            title=j.get("text", ""),
            location=categories.get("location", ""),
            url=url,
            description=ats_common.clean(j.get("descriptionPlain", "") or j.get("description", "")),
            posted=str(j.get("createdAt", "")) or None,
            region=region,
        ))
    return out


@register
class LeverSource:
    meta = SourceMeta(
        key="ats:lever",
        label="Lever (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("lever"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("lever")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug), params={"mode": "json"})
                r.raise_for_status()
                jobs.extend(parse_lever(r.json(), name, ats_common.primary_region(c)))
            except Exception as e:
                ctx.warn(f"ats:lever: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

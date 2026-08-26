"""SmartRecruiters — public, no-auth JSON: `GET /v1/companies/{slug}/postings`.

Verified live against `api.smartrecruiters.com/v1/companies/Sixt/postings`
(539 open postings at verification time). See
`backend/tests/fixtures/ats_smartrecruiters.json` for a trimmed real capture.

The postings LIST endpoint does not include the full job description (only
the single-posting detail endpoint does, and fetching that per-job would mean
N extra requests per company — too heavy for companies with 500+ postings).
Description is instead a compact synthesis of the metadata the list endpoint
does give us, same spirit as the Personio adapter.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"


def _describe(j: dict) -> str:
    bits = []
    for key in ("function", "department", "typeOfEmployment", "experienceLevel", "industry"):
        label = (j.get(key) or {}).get("label")
        if label:
            bits.append(label)
    return ats_common.clean(" · ".join(bits))


def parse_smartrecruiters(data: dict, company: str, region: str) -> list[Job]:
    out = []
    for j in data.get("content", []):
        identifier = (j.get("company") or {}).get("identifier", "")
        job_ref = j.get("id", "")
        url = f"https://jobs.smartrecruiters.com/{identifier}/{job_ref}" if identifier and job_ref else ""
        loc = j.get("location") or {}
        out.append(Job(
            id=job_id("ats:smartrecruiters", company, url),
            source="ats:smartrecruiters",
            company=company,
            title=j.get("name", ""),
            location=loc.get("fullLocation", "") or loc.get("city", ""),
            url=url,
            description=_describe(j),
            posted=j.get("releasedDate"),
            region=region,
        ))
    return out


@register
class SmartRecruitersSource:
    meta = SourceMeta(
        key="ats:smartrecruiters",
        label="SmartRecruiters (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("smartrecruiters"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("smartrecruiters")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug), params={"limit": 100})
                r.raise_for_status()
                jobs.extend(parse_smartrecruiters(r.json(), name, ats_common.primary_region(c)))
            except Exception as e:
                ctx.warn(f"ats:smartrecruiters: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

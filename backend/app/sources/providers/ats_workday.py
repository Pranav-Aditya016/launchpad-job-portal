"""Workday — POST JSON: `/wday/cxs/{tenant}/{site}/jobs`.

Workday is ~32% of enterprise-tech postings by the market-share note in the
brief, but there is no single URL shape: every tenant picks its own `wd{N}`
shard and its own `site` name (e.g. Accenture is `wd103` / `AccentureCareers`;
guessing either wrong gets HTTP 422, not a helpful error). That's why
companies.yml requires `wd_host` and `site` explicitly per company instead of
deriving them from the slug — only companies whose exact tenant/site pair was
found and hit live are included.

Verified live against `accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/
AccentureCareers/jobs` (2000+ postings at verification time — Workday caps
`total` reporting, the real count is larger). IBM and SAP were tried (both
explicitly requested) but their tenant/site pair could not be found within
the verification window: both companies' public careers pages are pure
client-side SPAs with no static reference to the Workday API path, and a
range of plausible `wd{N}`/site guesses for both returned 422. They are
NOT in companies.yml — guessing would mean a company card that always fails.

The `/jobs` list response has no description field (title, path, and a
human string like "Posted Today" only) — a real description would need one
more request per job, which doesn't scale for a tenant with thousands of
postings. Description is left to what the listing gives us via `bulletFields`.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://{slug}.{wd_host}.myworkdayjobs.com/wday/cxs/{slug}/{site}/jobs"
_PAGE_SIZE = 20


def parse_workday(data: dict, company: str, region: str, slug: str, wd_host: str, site: str) -> list[Job]:
    out = []
    for j in data.get("jobPostings", []):
        path = j.get("externalPath", "")
        url = f"https://{slug}.{wd_host}.myworkdayjobs.com/{site}{path}" if path else ""
        out.append(Job(
            id=job_id("ats:workday", company, url),
            source="ats:workday",
            company=company,
            title=j.get("title", ""),
            location=", ".join(str(b) for b in (j.get("bulletFields") or [])[1:]),
            url=url,
            description=ats_common.clean(" ".join(str(b) for b in (j.get("bulletFields") or []))),
            posted=j.get("postedOn"),
            region=region,
        ))
    return out


@register
class WorkdaySource:
    meta = SourceMeta(
        key="ats:workday",
        label="Workday (company career sites)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("workday"),
        rate_limit_s=2.5,
        daily_cap=500,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("workday")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            wd_host, site = c.get("wd_host", ""), c.get("site", "")
            if not (wd_host and site):
                ctx.warn(f"ats:workday: {name} ({slug}) missing wd_host/site in companies.yml")
                continue
            try:
                url = _BASE.format(slug=slug, wd_host=wd_host, site=site)
                r = await ctx.client.post(
                    url,
                    json={"limit": _PAGE_SIZE, "offset": 0, "appliedFacets": {}},
                )
                r.raise_for_status()
                jobs.extend(parse_workday(r.json(), name, ats_common.primary_region(c), slug, wd_host, site))
            except Exception as e:
                ctx.warn(f"ats:workday: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

"""Personio — public, no-auth JSON: `GET https://{slug}.jobs.personio.de/search.json`.

Big in Germany/DACH, which is why this platform is in scope at all. Verified
live against `medwing.jobs.personio.de/search.json` (13 open postings at
verification time). See `backend/tests/fixtures/ats_personio.json` for a
trimmed real capture.

Many companies that historically had a `{slug}.jobs.personio.de` subdomain
have since migrated to Personio's newer career-page product, whose subdomain
307-redirects to personio.com/personio.io marketing pages instead of serving
`search.json` — those slugs simply aren't usable with this adapter and were
excluded from companies.yml during verification, not included and hoped for.

`search.json` doesn't carry a job description field (it's consistently empty
in practice) or a canonical job URL, so both are built from what IS given:
description is synthesized from department/office/schedule/category, and the
URL follows Personio's documented `/job/{id}` pattern (verified live).
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_BASE = "https://{slug}.jobs.personio.de/search.json"


def _describe(j: dict) -> str:
    bits = []
    for key in ("department", "office", "schedule", "seniority", "category", "employment_type"):
        v = j.get(key)
        if v:
            bits.append(str(v))
    text = j.get("description") or ""
    if text:
        bits.append(text)
    return ats_common.clean(" · ".join(bits))


def parse_personio(data: list, company: str, region: str, slug: str) -> list[Job]:
    out = []
    for j in data:
        jid = j.get("id", "")
        url = f"https://{slug}.jobs.personio.de/job/{jid}" if jid else ""
        loc = j.get("office", "") or ", ".join(j.get("offices") or [])
        out.append(Job(
            id=job_id("ats:personio", company, url),
            source="ats:personio",
            company=company,
            title=j.get("name", ""),
            location=loc,
            url=url,
            description=_describe(j),
            posted=None,  # not present in the search.json shape
            region=region,
        ))
    return out


@register
class PersonioSource:
    meta = SourceMeta(
        key="ats:personio",
        label="Personio (company career sites, DACH-heavy)",
        kind=SourceKind.ATS,
        regions=ats_common.union_regions("personio"),
        rate_limit_s=1.5,
        daily_cap=1000,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        jobs: list[Job] = []
        companies = ats_common.companies_for("personio")
        for i, c in enumerate(companies):
            if len(jobs) >= ctx.limit:
                break
            slug, name = c.get("slug", ""), c.get("name", c.get("slug", ""))
            try:
                r = await ctx.client.get(_BASE.format(slug=slug))
                r.raise_for_status()
                jobs.extend(parse_personio(r.json(), name, ats_common.primary_region(c), slug))
            except Exception as e:
                ctx.warn(f"ats:personio: {name} ({slug}) failed: {e}")
            if i < len(companies) - 1:
                await ats_common.pace()
        return jobs[: ctx.limit]

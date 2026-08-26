"""Arbeitnow, behind the `Source` protocol. See `public_remotive.py` for why
this wraps `aggregators.parse_arbeitnow` unchanged rather than reimplementing
it — same job_id() compatibility reasoning applies here.
"""

from __future__ import annotations

from app.models import Job
from app.sources import aggregators
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.registry import register

_URL, _PARSE, _ = aggregators._ENDPOINTS["arbeitnow"]


@register
class ArbeitnowSource:
    meta = SourceMeta(
        key="public:arbeitnow",
        label="Arbeitnow",
        kind=SourceKind.PUBLIC,
        # Arbeitnow is a German-founded board skewed heavily toward EU/remote
        # postings, which is why it's in scope for this user at all.
        regions=("de", "global"),
        rate_limit_s=2.0,
        daily_cap=500,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        try:
            r = await ctx.client.get(_URL)
            r.raise_for_status()
            jobs = _PARSE(r.json())
        except Exception as e:
            ctx.warn(f"public:arbeitnow: {e}")
            return []
        return jobs[: ctx.limit]

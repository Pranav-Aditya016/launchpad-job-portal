"""The Muse, behind the `Source` protocol. See `public_remotive.py` for why
this wraps `aggregators.parse_themuse` unchanged.
"""

from __future__ import annotations

from app.models import Job
from app.sources import aggregators
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.registry import register

_URL, _PARSE, _ = aggregators._ENDPOINTS["themuse"]


@register
class TheMuseSource:
    meta = SourceMeta(
        key="public:themuse",
        label="The Muse",
        kind=SourceKind.PUBLIC,
        regions=("global",),
        rate_limit_s=2.0,
        daily_cap=500,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        try:
            r = await ctx.client.get(_URL)
            r.raise_for_status()
            jobs = _PARSE(r.json())
        except Exception as e:
            ctx.warn(f"public:themuse: {e}")
            return []
        return jobs[: ctx.limit]

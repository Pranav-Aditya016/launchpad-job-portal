"""Adzuna, behind the `Source` protocol.

Reuses `aggregators.fetch_adzuna` unchanged (env-var opt-in via
`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`, per-country non-fatal, India/Germany-first
country list) rather than reimplementing its request/parse logic.
"""

from __future__ import annotations

from app.models import Job
from app.sources import aggregators
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.registry import register


@register
class AdzunaSource:
    meta = SourceMeta(
        key="public:adzuna",
        label="Adzuna",
        kind=SourceKind.PUBLIC,
        regions=tuple(aggregators.ADZUNA_COUNTRIES),  # ("in", "de", "gb", "us")
        rate_limit_s=2.0,
        daily_cap=500,
        # Requires the user's own free ADZUNA_APP_ID/ADZUNA_APP_KEY; without
        # them fetch_adzuna() itself no-ops (returns []) rather than erroring,
        # so this stays a harmless no-op source until the user opts in.
        warning="Needs free ADZUNA_APP_ID/ADZUNA_APP_KEY env vars (developer.adzuna.com) — returns no jobs without them.",
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        query = ctx.queries[0] if ctx.queries else ""
        try:
            jobs = await aggregators.fetch_adzuna(ctx.client, query)
        except Exception as e:
            ctx.warn(f"public:adzuna: {e}")
            return []
        return jobs[: ctx.limit]

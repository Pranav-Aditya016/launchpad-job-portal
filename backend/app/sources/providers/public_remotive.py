"""Remotive, behind the `Source` protocol.

Reuses `aggregators.parse_remotive` and the existing endpoint URL unchanged —
`/scan` (v1) still imports `aggregators` directly and this wrapper must not
fork the parsing logic out from under it. `Job.source` stays `"remotive"`
(no prefix) so job IDs computed via `job_id()` are identical to what v1
already produces for the same real posting; only the registry key gets the
`public:` namespace.
"""

from __future__ import annotations

from app.models import Job
from app.sources import aggregators
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.registry import register

_URL, _PARSE, _ = aggregators._ENDPOINTS["remotive"]


@register
class RemotiveSource:
    meta = SourceMeta(
        key="public:remotive",
        label="Remotive",
        kind=SourceKind.PUBLIC,
        regions=("global",),
        rate_limit_s=2.0,
        daily_cap=500,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        url = _URL
        query = ctx.queries[0] if ctx.queries else ""
        if query:
            url = f"{url}?search={query}"
        try:
            r = await ctx.client.get(url)
            r.raise_for_status()
            jobs = _PARSE(r.json())
        except Exception as e:
            ctx.warn(f"public:remotive: {e}")
            return []
        return jobs[: ctx.limit]

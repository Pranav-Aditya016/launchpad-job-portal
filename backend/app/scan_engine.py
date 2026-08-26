"""Run the registered sources and record exactly what each one did.

This is what makes the source registry real. Before it, 27 sources were
registered and none were ever called — `/scan` ran the v1 aggregator path, so
the Sources page listed sites that were never actually queried.

Two guarantees, both load-bearing:

**Isolation.** A source that raises, hangs, or returns garbage costs you that
source and nothing else. Every fetch is wrapped, timed and capped (spec §7).

**Provenance.** Every source produces a `SourceResult` whether it succeeded,
returned nothing, errored, was switched off, or is waiting on a login. The
user can then see where each job came from and — just as important — which
sites are silently contributing nothing.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.models import Job, Profile, ScanRun, SourceResult
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceUnavailable

# One source must never be able to stall the whole cycle (spec §12.2).
PER_SOURCE_TIMEOUT_S = 90.0
DEFAULT_LIMIT = 100


@dataclass
class ScanOutcome:
    """Everything one scan produced. `results` is the provenance record."""

    jobs: list[Job] = field(default_factory=list)
    results: list[SourceResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started: str = ""
    finished: str = ""

    @property
    def total_jobs(self) -> int:
        return len(self.jobs)

    @property
    def per_source(self) -> dict[str, int]:
        return {r.key: r.jobs_found for r in self.results}

    def to_scan_run(self, run_id: str, trigger: str = "manual") -> ScanRun:
        return ScanRun(
            id=run_id, started=self.started, finished=self.finished,
            trigger=trigger, per_source=self.per_source,
            warnings=self.warnings, results=self.results,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _queries(profile: Profile) -> list[str]:
    roles = [r for r in (profile.target_roles or []) if r.strip()]
    return roles[:6] or ["engineer"]


class _HostLimiter:
    """Serialise requests per host and honour each source's `rate_limit_s`.

    Enforced here rather than in each adapter so a careless adapter cannot
    hammer a host — this protects the user's own IP and accounts as much as
    the target site (spec §12.5).
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last: dict[str, float] = {}

    async def wait(self, target: str, delay: float) -> None:
        host = urlparse(target).netloc or target
        async with self._locks[host]:
            gap = time.monotonic() - self._last.get(host, 0.0)
            if gap < delay:
                await asyncio.sleep(delay - gap)
            self._last[host] = time.monotonic()


def _select(source_keys, regions, overrides):
    """Which sources this scan considers, and why each was included."""
    chosen = []
    for src in registry.all_sources():
        meta = src.meta
        if source_keys is not None and meta.key not in source_keys:
            continue
        if regions and not (set(regions) & set(meta.regions)):
            continue
        enabled = overrides.get(meta.key, meta.enabled_by_default)
        chosen.append((src, enabled))
    return chosen


async def _run_one(src, enabled, ctx_factory, limiter, connected_portals) -> tuple[SourceResult, list[Job]]:
    meta = src.meta
    result = SourceResult(
        key=meta.key, label=meta.label, kind=meta.kind.value,
        target=meta.logged_in_probe or meta.login_url or "",
    )

    if not enabled:
        result.status = "disabled"
        result.detail = "switched off — turn it on from the Sources page"
        return result, []

    # A portal the user hasn't connected is a normal state, not a fault.
    if meta.kind is SourceKind.PORTAL and meta.key not in connected_portals:
        result.status = "needs_login"
        result.detail = "not connected yet — connect it from the Connections page"
        return result, []

    ctx = ctx_factory()
    started = time.monotonic()
    try:
        await limiter.wait(meta.login_url or meta.key, meta.rate_limit_s)
        jobs = await asyncio.wait_for(src.fetch(ctx), timeout=PER_SOURCE_TIMEOUT_S)
        jobs = list(jobs or [])[: meta.daily_cap]
        for j in jobs:
            if not j.region and meta.regions:
                j.region = meta.regions[0]
        result.jobs_found = len(jobs)
        result.status = "ok" if jobs else "empty"
        if not jobs:
            result.detail = (
                "returned no postings — either nothing matched, or the site's "
                "layout changed and the adapter needs updating"
            )
        return result, jobs
    except SourceUnavailable as e:
        result.status = "needs_login"
        result.detail = str(e)[:300]
        return result, []
    except asyncio.TimeoutError:
        result.status = "error"
        result.detail = f"timed out after {PER_SOURCE_TIMEOUT_S:.0f}s"
        return result, []
    except Exception as e:                      # noqa: BLE001 — isolation is the point
        result.status = "error"
        result.detail = f"{type(e).__name__}: {e}"[:300]
        return result, []
    finally:
        result.duration_s = round(time.monotonic() - started, 2)
        ctx_warnings = getattr(ctx, "warnings", [])
        if ctx_warnings:
            result.detail = (result.detail + " " + " | ".join(ctx_warnings)).strip()[:300]


async def run_scan(
    profile: Profile,
    *,
    source_keys: list[str] | None = None,
    regions: list[str] | None = None,
    overrides: dict[str, bool] | None = None,
    connected_portals: set[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    page_opener=None,
) -> ScanOutcome:
    """Run every selected source concurrently and return jobs + provenance."""
    registry.load_providers()
    overrides = overrides or {}
    connected_portals = connected_portals or set()
    limiter = _HostLimiter()
    outcome = ScanOutcome(started=_now())

    selected = _select(source_keys, regions, overrides)
    contexts: list[FetchContext] = []

    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True,
        headers={"User-Agent": "LaunchPad/2.0 (personal job search)"},
    ) as client:

        def ctx_factory() -> FetchContext:
            ctx = FetchContext(profile=profile, queries=_queries(profile),
                               client=client, page_opener=page_opener, limit=limit)
            contexts.append(ctx)
            return ctx

        pairs = await asyncio.gather(*[
            _run_one(src, enabled, ctx_factory, limiter, connected_portals)
            for src, enabled in selected
        ])

    for result, jobs in pairs:
        outcome.results.append(result)
        outcome.jobs.extend(jobs)
    for ctx in contexts:
        outcome.warnings.extend(ctx.warnings)

    outcome.finished = _now()
    return outcome

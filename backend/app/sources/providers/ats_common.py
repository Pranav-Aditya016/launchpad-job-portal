"""Shared plumbing for the ATS provider adapters.

Not itself a `Source` — no `@register` here — but it matches the `ats_*.py`
ownership glob (Track B), so the YAML loader and the handful of tiny helpers
every ATS adapter needs live in one place instead of being copy-pasted into
all eight of them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from app.sources.aggregators import _clean

# Reused as-is: the aggregators module already has a battle-tested
# entity-unescape-then-strip-tags helper. No reason to write a second one.
clean = _clean

COMPANIES_PATH = Path(__file__).resolve().parent.parent / "companies.yml"

_companies_cache: list[dict[str, Any]] | None = None

# Courtesy pause between successive per-company requests inside ONE adapter's
# fetch() call. `SourceMeta.rate_limit_s` (enforced by the scheduler, Track D)
# paces how often a whole source runs; it says nothing about the N HTTP calls
# one fetch() makes across N configured companies, so each adapter adds this
# small delay itself rather than firing every company request back-to-back.
COMPANY_DELAY_S = 0.15


def _load_all_companies() -> list[dict[str, Any]]:
    global _companies_cache
    if _companies_cache is not None:
        return _companies_cache
    if not COMPANIES_PATH.exists():
        _companies_cache = []
        return _companies_cache
    with open(COMPANIES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    _companies_cache = data if isinstance(data, list) else []
    return _companies_cache


def companies_for(ats: str) -> list[dict[str, Any]]:
    """Every companies.yml entry for one ATS platform, in file order."""
    return [c for c in _load_all_companies() if c.get("ats") == ats]


def primary_region(company: dict[str, Any]) -> str:
    regions = company.get("regions") or ["global"]
    return str(regions[0])


def union_regions(ats: str) -> tuple[str, ...]:
    """Every distinct region companies.yml declares for one ATS.

    Used for `SourceMeta.regions` so the UI's per-source region badge reflects
    the actual companies configured, not a guess.
    """
    seen: list[str] = []
    for c in companies_for(ats):
        for r in c.get("regions") or ["global"]:
            r = str(r)
            if r not in seen:
                seen.append(r)
    return tuple(seen) or ("global",)


async def pace() -> None:
    """Await the shared inter-company courtesy delay."""
    await asyncio.sleep(COMPANY_DELAY_S)

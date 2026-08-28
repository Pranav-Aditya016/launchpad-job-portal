"""The registry as the UI sees it, plus the user's own websites.

`GET /sources` is the transparency surface: it lists **every** source, whether
it is on, and what happened to it in the last scan. Listing only the sources
that worked would quietly imply coverage the user does not have.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import custom_sources as cs
from app import region as region_mod
from app import store
from app.sources import registry

router = APIRouter()


class SourceToggle(BaseModel):
    enabled: bool


class CustomSiteIn(BaseModel):
    url: str
    label: str = ""
    regions: list[str] | None = None
    notes: str = ""


def _last_results() -> dict[str, dict]:
    """Per-source outcome from the most recent run, keyed by source key."""
    runs = store.load_runs(limit=1)
    if not runs:
        return {}
    return {r.key: r.model_dump() for r in runs[0].results}


@router.get("/regions")
def list_regions():
    """The complete region list for the dashboard filter.

    Served from a fixed list rather than derived from whatever jobs happen to
    be stored: a filter built from present data can only ever offer the regions
    you already have, so "India" would vanish on any day nothing Indian was
    scraped — exactly when you most want to notice.
    """
    return {
        "regions": [{"code": c, "label": l} for c, l in region_mod.ALL_REGIONS]
        + [{"code": "", "label": "Unspecified"}]
    }


@router.get("/sources")
def list_sources():
    overrides = store.load_source_config()
    last = _last_results()
    sources = []
    for s in registry.all_sources():
        m = s.meta
        sources.append({
            "key": m.key,
            "label": m.label,
            "kind": m.kind.value,
            "regions": list(m.regions),
            "requires_login": m.requires_login,
            "enabled": overrides.get(m.key, m.enabled_by_default),
            "warning": m.warning,
            # Transparency: what this source actually did last time.
            "last": last.get(m.key),
        })
    return {
        "sources": sources,
        "counts": {
            "total": len(sources),
            "enabled": sum(1 for s in sources if s["enabled"]),
            "by_kind": {
                k: sum(1 for s in sources if s["kind"] == k)
                for k in sorted({s["kind"] for s in sources})
            },
        },
    }


@router.put("/sources/{key}")
def toggle_source(key: str, body: SourceToggle):
    if registry.get(key) is None:
        raise HTTPException(status_code=404, detail=f"unknown source {key!r}")
    store.set_source_enabled(key, body.enabled)
    return {"key": key, "enabled": body.enabled}


# --- the user's own websites ------------------------------------------------

@router.get("/sources/custom")
def list_custom_sites():
    sites = cs.load_all()
    return {
        "sites": [
            {
                "id": s.id, "url": s.url, "label": s.label, "regions": s.regions,
                "enabled": s.enabled, "notes": s.notes,
                "last_status": s.last_status, "last_jobs": s.last_jobs,
                "last_detail": s.last_detail,
            }
            for s in sites
        ]
    }


@router.post("/sources/custom")
def add_custom_site(body: CustomSiteIn):
    """Add a website to scrape. Rejects anything that isn't an http(s) URL —
    these get handed to a fetcher later, so the scheme is a security boundary."""
    try:
        site = cs.add(body.url, label=body.label, regions=body.regions, notes=body.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"id": site.id, "url": site.url, "label": site.label,
            "regions": site.regions, "enabled": site.enabled}


@router.put("/sources/custom/{site_id}")
def toggle_custom_site(site_id: str, body: SourceToggle):
    if not cs.set_enabled(site_id, body.enabled):
        raise HTTPException(status_code=404, detail=f"unknown site {site_id!r}")
    return {"id": site_id, "enabled": body.enabled}


@router.delete("/sources/custom/{site_id}")
def delete_custom_site(site_id: str):
    if not cs.remove(site_id):
        raise HTTPException(status_code=404, detail=f"unknown site {site_id!r}")
    return {"id": site_id, "deleted": True}

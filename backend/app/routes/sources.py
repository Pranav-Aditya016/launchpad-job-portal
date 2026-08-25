"""GET /sources, PUT /sources/{key} — the registry, as the UI sees it."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.sources import registry

router = APIRouter()


class SourceToggle(BaseModel):
    enabled: bool


@router.get("/sources")
def list_sources():
    overrides = store.load_source_config()
    return {
        "sources": [
            {
                "key": s.meta.key,
                "label": s.meta.label,
                "kind": s.meta.kind.value,
                "regions": list(s.meta.regions),
                "requires_login": s.meta.requires_login,
                "enabled": overrides.get(s.meta.key, s.meta.enabled_by_default),
                "warning": s.meta.warning,
            }
            for s in registry.all_sources()
        ]
    }


@router.put("/sources/{key}")
def toggle_source(key: str, body: SourceToggle):
    if registry.get(key) is None:
        raise HTTPException(status_code=404, detail=f"unknown source {key!r}")
    store.set_source_enabled(key, body.enabled)
    return {"key": key, "enabled": body.enabled}

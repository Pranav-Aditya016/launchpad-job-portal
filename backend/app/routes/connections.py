"""Login-gated portal connections.

GET is real (it just reads the store). The three action routes return 501 until
Track C lands the session vault — deliberately, so a stub can never masquerade as
a working feature.

BOUNDARY (spec §2): nothing here accepts a username, password or OTP. The user
logs in themselves in a real browser window; we persist only the browser profile.
"""

from fastapi import APIRouter, HTTPException

from app import store
from app.sources import registry
from app.sources.base import SourceKind

router = APIRouter()

_NOT_YET = "Session vault not implemented yet (Track C)."


@router.get("/connections")
def list_connections():
    """Every login-gated source, joined with its stored status."""
    saved = store.load_connections()
    out = []
    for s in registry.all_sources():
        if s.meta.kind is not SourceKind.PORTAL:
            continue
        conn = saved.get(s.meta.key)
        out.append({
            "portal": s.meta.key,
            "label": s.meta.label,
            "login_url": s.meta.login_url,
            "status": conn.status if conn else "disconnected",
            "last_verified": conn.last_verified if conn else None,
            "note": conn.note if conn else "",
            "warning": s.meta.warning,
        })
    return {"connections": out}


@router.post("/connections/{portal}/login")
def start_login(portal: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.post("/connections/{portal}/verify")
def verify(portal: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)


@router.delete("/connections/{portal}")
def disconnect(portal: str):
    raise HTTPException(status_code=501, detail=_NOT_YET)

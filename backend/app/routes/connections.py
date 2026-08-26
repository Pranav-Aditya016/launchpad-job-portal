"""Login-gated portal connections.

GET is real (it just reads the store). The three action routes are now backed
by the session vault (`app.browser.session`): `login` opens a real, visible
browser window at the portal's own login page and returns immediately; the
user logs in themselves. `verify` opens the saved profile headless and checks
whether the session still holds. `disconnect` deletes the profile — a real
logout.

BOUNDARY (spec §2, §6.3): nothing here accepts a username, password or OTP.
The user logs in themselves in a real browser window; we persist only the
browser profile. Every action degrades to a stored `expired`/`blocked`
`Connection` on failure — a missing browser, a locked profile, a portal
redesign — rather than raising a 500 (spec §7).
"""

from fastapi import APIRouter, HTTPException

from app import store
from app.browser import session
from app.models import Connection
from app.sources import registry
from app.sources.base import SourceKind

router = APIRouter()


def _portal_source(portal: str):
    registry.load_providers()
    src = registry.get(portal)
    if src is None or src.meta.kind is not SourceKind.PORTAL:
        return None
    return src


def _serialize(portal: str, src, conn: Connection | None) -> dict:
    return {
        "portal": portal,
        "label": src.meta.label if src else portal,
        "login_url": src.meta.login_url if src else "",
        "status": conn.status if conn else "disconnected",
        "last_verified": conn.last_verified if conn else None,
        "note": conn.note if conn else "",
        "warning": src.meta.warning if src else "",
    }


@router.get("/connections")
def list_connections():
    """Every login-gated source, joined with its stored status."""
    saved = store.load_connections()
    out = []
    for s in registry.all_sources():
        if s.meta.kind is not SourceKind.PORTAL:
            continue
        out.append(_serialize(s.meta.key, s, saved.get(s.meta.key)))
    return {"connections": out}


@router.post("/connections/{portal}/login")
async def start_login(portal: str):
    src = _portal_source(portal)
    if src is None:
        raise HTTPException(status_code=404, detail=f"unknown portal '{portal}'")
    try:
        conn = await session.open_login_window(portal)
    except Exception as e:
        # Degrade, never 500 (spec §7): record the failure and carry on.
        conn = Connection(portal=portal, status="expired", note=f"could not start login: {e}"[:300])
        store.save_connection(conn)
    return _serialize(portal, src, conn)


@router.post("/connections/{portal}/verify")
async def verify(portal: str):
    src = _portal_source(portal)
    if src is None:
        raise HTTPException(status_code=404, detail=f"unknown portal '{portal}'")
    try:
        conn = await session.verify(portal)
    except Exception as e:  # session.verify already degrades internally; belt and braces
        conn = Connection(portal=portal, status="expired", note=f"verify failed: {e}"[:300])
        store.save_connection(conn)
    return _serialize(portal, src, conn)


@router.delete("/connections/{portal}")
async def disconnect(portal: str):
    src = _portal_source(portal)
    if src is None:
        raise HTTPException(status_code=404, detail=f"unknown portal '{portal}'")
    try:
        await session.disconnect(portal)
    except Exception as e:
        # Even a failed cleanup must not 500 — surface it as a note instead.
        store.save_connection(Connection(portal=portal, status="expired", note=f"disconnect failed: {e}"[:300]))
    return _serialize(portal, src, store.load_connections().get(portal))

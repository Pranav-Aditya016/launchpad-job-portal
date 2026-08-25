"""GET /events — SSE scan progress.

Track 0 ships a heartbeat-only stream so Track E can wire the UI's live indicator
immediately. Track D replaces the generator with real pipeline events.
"""

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


async def _heartbeat():
    while True:
        yield {"event": "heartbeat", "data": json.dumps({"status": "idle"})}
        await asyncio.sleep(15)


@router.get("/events")
async def events():
    return EventSourceResponse(_heartbeat())

"""Notification / progress streaming (design Section 5.10, TDD-17). Owner: Utkarsh.

Server-Sent Events (SSE) stream of job progress with resume via ?after=eventId (design Section 10.3).
Reads from the event bus job log so late/reconnecting clients replay missed events.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from apps import bus

router = APIRouter(prefix="/v1/stream", tags=["notifications"])


@router.get("/jobs/{job_id}")
async def stream_job(job_id: str, after: int = 0):
    async def gen():
        last = after
        # Replay everything already logged, then poll for new events briefly.
        for _ in range(300):  # ~30s max for the scaffold
            events = bus.replay(job_id, last)
            for e in events:
                last = e.event_id
                data = {"eventId": e.event_id, "subject": e.subject, **e.payload}
                yield f"id: {e.event_id}\ndata: {json.dumps(data)}\n\n"
                if e.payload.get("stage") == "done" or e.subject == "jobs.completed":
                    return
            await asyncio.sleep(0.1)

    return StreamingResponse(gen(), media_type="text/event-stream")

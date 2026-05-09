from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    pool = getattr(request.app.state, "pool", None)
    in_flight = len(pool._tasks) if pool else 0
    return {"status": "ok", "in_flight": in_flight}

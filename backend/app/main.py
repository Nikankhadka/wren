from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import platform, public, tenants
from app.core import db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create the wren_app pool on startup, close it on shutdown.

    Guarded against double-create: tests that already created a pool pointed at
    wren_test (backend/tests/conftest.py) drive the app without running this
    lifespan (httpx's ASGITransport does not send lifespan events on its own),
    but the guard keeps this safe even if that ever changes.
    """
    created_here = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_here = True
    try:
        yield
    finally:
        if created_here:
            await db.close_pool()


app = FastAPI(title="Wren", version="0.1.0", lifespan=lifespan)
app.include_router(tenants.router)
app.include_router(platform.router)
app.include_router(public.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

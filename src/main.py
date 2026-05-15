"""FastAPI app entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.api.routes import forge, industries, packs
from src.config import get_settings
from src.services.forge_engine import ForgeEngine
from src.services.pack_registry import PackRegistry
from src.utils.tracing import CorrelationIdMiddleware, configure_logging

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    log.info("app.start", env=s.app_env)

    app.state.forge_engine = ForgeEngine()
    app.state.pack_registry = PackRegistry()

    yield

    log.info("app.shutdown")


app = FastAPI(
    title="MicroApp-VerticalForge",
    description="Industry Vertical Pack generator for LumApps Agent Hub",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)

app.include_router(forge.router)
app.include_router(packs.router)
app.include_router(industries.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", tags=["meta"], include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": "MicroApp-VerticalForge",
        "version": app.version,
        "docs": "/docs",
    }

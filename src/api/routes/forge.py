"""Forge endpoints — submit / poll / stream / cancel / publish."""
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from src.auth.deps import require_scope
from src.auth.oidc import Principal
from src.models.forge import ForgeJob, ForgeRequest, ForgeStatus
from src.models.pack import VerticalPack
from src.services.forge_engine import ForgeEngine
from src.services.pack_registry import DuplicateVersionError

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/forge", tags=["forge"])


def _engine(request: Request) -> ForgeEngine:
    return request.app.state.forge_engine


# ---------------------------------------------------------------- jobs


@router.post(
    "/jobs",
    response_model=ForgeJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a forge job",
)
async def submit_job(
    payload: ForgeRequest,
    background: BackgroundTasks,
    request: Request,
    principal: Principal = Depends(require_scope("forge:write")),
) -> ForgeJob:
    engine = _engine(request)
    job = ForgeJob(request=payload, correlation_id=request.state.correlation_id)
    engine.save(job)

    background.add_task(_run_in_background, engine, job)
    log.info("forge.submitted", job_id=job.job_id, industry=payload.target_industry.value,
             by=principal.subject)
    return job


async def _run_in_background(engine: ForgeEngine, job: ForgeJob) -> None:
    try:
        await engine.run(job)
    except Exception:  # noqa: BLE001
        log.exception("forge.background.crash", job_id=job.job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=ForgeJob,
    responses={404: {"description": "Job not found"}},
    summary="Poll a forge job",
)
async def get_job(
    job_id: str,
    request: Request,
    principal: Principal = Depends(require_scope("forge:read")),
) -> ForgeJob:
    job = _engine(request).get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.get(
    "/jobs/{job_id}/stream",
    summary="SSE feed of stage updates",
)
async def stream_job(
    job_id: str,
    request: Request,
    principal: Principal = Depends(require_scope("forge:read")),
):
    engine = _engine(request)
    if engine.get(job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")

    async def gen():
        q = engine.queue(job_id)
        try:
            while True:
                event = await q.get()
                if await request.is_disconnected():
                    return
                yield {"event": event.type, "data": json.dumps(event.model_dump(mode="json"))}
                if event.type in ("done", "stage.failed", "canceled"):
                    return
        except asyncio.CancelledError:
            log.info("forge.stream.cancelled", job_id=job_id)
            raise

    return EventSourceResponse(gen())


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=ForgeJob,
    summary="Cancel a running forge job",
)
async def cancel_job(
    job_id: str,
    request: Request,
    principal: Principal = Depends(require_scope("forge:write")),
) -> ForgeJob:
    engine = _engine(request)
    job = engine.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.status in (ForgeStatus.SUCCEEDED, ForgeStatus.FAILED, ForgeStatus.CANCELED):
        return job  # idempotent
    engine.cancel(job_id)
    log.info("forge.cancelled", job_id=job_id, by=principal.subject)
    return job


# ---------------------------------------------------------------- publish


@router.post(
    "/jobs/{job_id}/publish",
    response_model=VerticalPack,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Pack version already exists"},
        412: {"description": "Job not yet succeeded"},
    },
    summary="Publish a completed forge job's pack to the library",
)
async def publish_pack(
    job_id: str,
    request: Request,
    principal: Principal = Depends(require_scope("pack:publish")),
) -> VerticalPack:
    engine = _engine(request)
    registry = request.app.state.pack_registry

    job = engine.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.status != ForgeStatus.SUCCEEDED or job.manifest is None:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED,
                            detail=f"job not ready · current state: {job.status.value}")

    try:
        pack = registry.publish(job.manifest)
    except DuplicateVersionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    job.pack_id = pack.pack_id
    log.info("pack.published", pack_id=pack.pack_id, name=pack.manifest.name,
             version=pack.manifest.version, by=principal.subject)
    return pack

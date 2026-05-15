"""Forge engine — drives the pipeline.

The four pipeline stages are real DAG nodes. The per-stage *logic* is stubbed
(AST parsing, governance application, signing) and clearly marked with
`TODO(real-impl)` comments. The driver, status updates, eventing, and error
handling are implemented.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import structlog

from src.config import get_settings
from src.models.events import ForgeEvent
from src.models.forge import ForgeJob, ForgeStage, ForgeStatus, StageResult
from src.models.pack import INDUSTRY_CUSTOMER_COUNT, ManifestParam, PackManifest

log = structlog.get_logger(__name__)

PIPELINE: list[ForgeStage] = [
    ForgeStage.INGEST,
    ForgeStage.ABSTRACT,
    ForgeStage.GOVERN,
    ForgeStage.PACK,
]


class ForgeEngine:
    """Runs forge jobs. Holds in-memory job state + per-job event queues."""

    def __init__(self) -> None:
        self._jobs: dict[str, ForgeJob] = {}
        self._queues: dict[str, asyncio.Queue[ForgeEvent]] = {}
        self._cancel_flags: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------ storage

    def save(self, job: ForgeJob) -> None:
        self._jobs[job.job_id] = job
        self._queues.setdefault(job.job_id, asyncio.Queue(maxsize=128))
        self._cancel_flags.setdefault(job.job_id, asyncio.Event())

    def get(self, job_id: str) -> ForgeJob | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        flag = self._cancel_flags.get(job_id)
        if flag is None:
            return False
        flag.set()
        return True

    def queue(self, job_id: str) -> asyncio.Queue[ForgeEvent]:
        return self._queues.setdefault(job_id, asyncio.Queue(maxsize=128))

    # ------------------------------------------------------------ pipeline

    async def run(self, job: ForgeJob) -> ForgeJob:
        """Execute the full pipeline. Updates the job in place."""
        job.status = ForgeStatus.RUNNING
        job.updated_at = datetime.now(timezone.utc)
        cancel = self._cancel_flags[job.job_id]
        cid = job.correlation_id or ""

        try:
            for stage in PIPELINE:
                if cancel.is_set():
                    job.status = ForgeStatus.CANCELED
                    await self._emit(ForgeEvent(
                        type="canceled", job_id=job.job_id, stage=stage,
                        message="job canceled by user", correlation_id=cid,
                    ))
                    return job

                await self._emit(ForgeEvent(
                    type="stage.start", job_id=job.job_id, stage=stage,
                    message=f"stage {stage.value} starting", correlation_id=cid,
                ))
                result = await self._run_stage(stage, job)
                job.stages.append(result)

                if result.status == ForgeStatus.FAILED:
                    job.status = ForgeStatus.FAILED
                    job.error = result.detail
                    await self._emit(ForgeEvent(
                        type="stage.failed", job_id=job.job_id, stage=stage,
                        message=result.detail, correlation_id=cid,
                    ))
                    return job

                await self._emit(ForgeEvent(
                    type="stage.complete", job_id=job.job_id, stage=stage,
                    message=f"stage {stage.value} done in {result.duration_ms}ms",
                    correlation_id=cid, payload={"duration_ms": result.duration_ms},
                ))

            # All stages OK → build the manifest
            job.manifest = self._build_manifest(job)
            job.status = ForgeStatus.SUCCEEDED
            await self._emit(ForgeEvent(
                type="done", job_id=job.job_id,
                message=f"forge complete · {len(job.stages)} stages",
                correlation_id=cid,
                payload={
                    "params": len(job.manifest.params),
                    "target_customers": INDUSTRY_CUSTOMER_COUNT[job.request.target_industry],
                },
            ))
        finally:
            job.updated_at = datetime.now(timezone.utc)

        return job

    # ------------------------------------------------------------ stage drivers

    async def _run_stage(self, stage: ForgeStage, job: ForgeJob) -> StageResult:
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            match stage:
                case ForgeStage.INGEST:
                    detail = await self._ingest(job)
                case ForgeStage.ABSTRACT:
                    detail = await self._abstract(job)
                case ForgeStage.GOVERN:
                    detail = await self._govern(job)
                case ForgeStage.PACK:
                    detail = await self._pack(job)
        except Exception as exc:  # noqa: BLE001
            log.exception("forge.stage.failed", stage=stage.value, job_id=job.job_id)
            return StageResult(
                stage=stage, status=ForgeStatus.FAILED,
                started_at=started, duration_ms=int((time.perf_counter() - t0) * 1000),
                detail=f"{type(exc).__name__}: {exc}",
            )
        return StageResult(
            stage=stage, status=ForgeStatus.SUCCEEDED,
            started_at=started, duration_ms=int((time.perf_counter() - t0) * 1000),
            detail=detail,
        )

    # ------------------------------------------------------------ stage stubs

    async def _ingest(self, job: ForgeJob) -> str:
        # TODO(real-impl): fetch the source Micro-app bundle from object storage,
        # validate the manifest signature, unzip into a working directory.
        await asyncio.sleep(0.2)
        return f"ingested source {job.request.source_micro_app_id}"

    async def _abstract(self, job: ForgeJob) -> str:
        # TODO(real-impl): walk the AST of the source bundle, identify
        # customer-specific literals (tenant URLs, cost centers, channel IDs),
        # replace with `{{ param.* }}` placeholders, collect ManifestParam list.
        await asyncio.sleep(0.4)
        return "extracted 14 templatized parameters · 240 LOC abstracted"

    async def _govern(self, job: ForgeJob) -> str:
        # TODO(real-impl): apply governance policy — OIDC schema injection,
        # RBAC inheritance rules, audit logging hooks, GDPR data-residency
        # annotations, rate-limit middleware wiring.
        await asyncio.sleep(0.3)
        rules = sum([
            job.request.governance.oidc_per_tenant,
            job.request.governance.rbac_inherit,
            job.request.governance.audit_soc2,
            job.request.governance.gdpr_eu_residency,
            job.request.governance.rate_limit_per_tenant_per_min is not None,
        ])
        return f"applied {rules} governance rules"

    async def _pack(self, job: ForgeJob) -> str:
        # TODO(real-impl): bundle abstracted code + manifest into a .pack
        # archive, sign with KMS-managed key, upload to the registry bucket.
        await asyncio.sleep(0.25)
        return "packaged & signed · ready for publish"

    # ------------------------------------------------------------ helpers

    def _build_manifest(self, job: ForgeJob) -> PackManifest:
        """Synthesize the manifest from the request + (in real impl) AST output."""
        manifest = PackManifest(
            name=job.request.target_pack_name,
            version=job.request.target_pack_version,
            industry=job.request.target_industry,
            description=job.request.description or f"Forged from {job.request.source_micro_app_id}",
            params=_stub_params_for(job),
            governance=job.request.governance,
            source_micro_app_id=job.request.source_micro_app_id,
        )
        manifest.signature = sign_manifest(manifest)
        return manifest

    async def _emit(self, event: ForgeEvent) -> None:
        q = self._queues.get(event.job_id)
        if q is None:
            return
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("forge.queue.full", job_id=event.job_id)


def _stub_params_for(job: ForgeJob) -> list[ManifestParam]:
    """Placeholder param list. Real impl gets these from the AST abstraction step."""
    return [
        ManifestParam(name="tenant_workday_url", type="url", description="Tenant Workday base URL"),
        ManifestParam(name="cost_center_code", type="string", description="Cost center for new hires"),
        ManifestParam(name="it_equipment_sku", type="enum", default="MacBookPro-M3-14",
                      description="Default device SKU"),
        ManifestParam(name="comms_channel_id", type="string", description="Teams/Slack channel for announcements"),
    ]


def sign_manifest(manifest: PackManifest) -> str:
    """HMAC-SHA256 over the canonical JSON of the manifest body.

    In production this is a KMS sign call; here we use a shared secret so the
    demo is self-contained.
    """
    body = manifest.model_copy(update={"signature": None}).model_dump_json(by_alias=True)
    key = get_settings().pack_signing_secret.encode()
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()

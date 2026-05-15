"""Forge-side models: jobs, stages, status."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.pack import GovernanceConfig, Industry, PackManifest


class ForgeStage(str, Enum):
    INGEST = "ingest"
    ABSTRACT = "abstract"
    GOVERN = "govern"
    PACK = "pack"


class ForgeStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class ForgeRequest(BaseModel):
    """Inbound payload to start a forge job."""
    source_micro_app_id: str = Field(..., description="ID of the custom Micro-app to abstract")
    target_industry: Industry
    target_pack_name: str = Field(..., pattern=r"^[a-z][a-z0-9-]{2,40}$")
    target_pack_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    description: str = ""


class StageResult(BaseModel):
    stage: ForgeStage
    status: ForgeStatus
    started_at: datetime
    duration_ms: int
    detail: str = ""


class ForgeJob(BaseModel):
    """A forge run from request to finished pack."""
    job_id: str = Field(default_factory=lambda: f"forge-{uuid4().hex[:12]}")
    request: ForgeRequest
    status: ForgeStatus = ForgeStatus.QUEUED
    stages: list[StageResult] = Field(default_factory=list)
    manifest: PackManifest | None = None  # populated when status == SUCCEEDED
    pack_id: str | None = None  # set when published
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    correlation_id: str | None = None

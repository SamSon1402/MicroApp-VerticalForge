"""SSE event for forge stream."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src.models.forge import ForgeStage


class ForgeEvent(BaseModel):
    type: Literal["stage.start", "stage.complete", "stage.failed", "done", "canceled"]
    job_id: str
    stage: ForgeStage | None = None
    message: str
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = Field(default_factory=dict)

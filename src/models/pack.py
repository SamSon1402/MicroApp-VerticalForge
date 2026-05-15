"""Pack-side domain models: Industry, GovernanceConfig, Manifest, VerticalPack."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Industry(str, Enum):
    RETAIL = "retail"
    HOSPITALITY = "hospitality"
    MANUFACTURING = "manufacturing"
    TECHNOLOGY = "technology"


# Customer count is hardcoded for the demo; in prod this comes from the tenant DB.
INDUSTRY_CUSTOMER_COUNT: dict[Industry, int] = {
    Industry.RETAIL: 12,
    Industry.HOSPITALITY: 8,
    Industry.MANUFACTURING: 15,
    Industry.TECHNOLOGY: 21,
}


class GovernanceConfig(BaseModel):
    """Policy switches applied to a forged pack. Defaults are 'enterprise-safe'."""
    oidc_per_tenant: bool = True
    rbac_inherit: bool = True
    audit_soc2: bool = True
    gdpr_eu_residency: bool = True
    rate_limit_per_tenant_per_min: int | None = Field(default=None, ge=1, le=10_000)


class ManifestParam(BaseModel):
    """One templatized parameter extracted from the source Micro-app."""
    name: str  # e.g. "tenant_workday_url"
    type: str  # "string" | "url" | "secret" | "enum"
    required: bool = True
    default: str | None = None
    description: str = ""


class PackManifest(BaseModel):
    """The compiled artifact: schema, params, governance, version."""
    name: str = Field(..., pattern=r"^[a-z][a-z0-9-]{2,40}$")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    industry: Industry
    description: str
    params: list[ManifestParam] = Field(default_factory=list)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    source_micro_app_id: str
    forged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signature: str | None = None  # HMAC over the manifest body; set on publish


class VerticalPack(BaseModel):
    """A published pack stored in the library."""
    pack_id: str
    manifest: PackManifest
    published: bool = False
    deploy_count: int = 0
    rating: float | None = None  # populated from telemetry once deployed


class PackDeployment(BaseModel):
    """One tenant install of a pack."""
    pack_id: str
    tenant_id: str
    deployed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    params: dict[str, str] = Field(default_factory=dict)  # filled in per tenant

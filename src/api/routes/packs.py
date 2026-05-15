"""Pack library routes — list / get / deploy / customers."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.auth.deps import require_scope
from src.auth.oidc import Principal
from src.models.pack import Industry, PackDeployment, VerticalPack

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/packs", tags=["packs"])


class DeployRequest(BaseModel):
    tenant_ids: list[str] = Field(..., min_length=1, max_length=100)
    params: dict[str, str] = Field(default_factory=dict,
                                   description="Param values supplied per-deploy")


class DeployResponse(BaseModel):
    pack_id: str
    deployments: list[PackDeployment]


@router.get("", response_model=list[VerticalPack], summary="List packs (optional industry filter)")
async def list_packs(
    request: Request,
    industry: Industry | None = None,
    principal: Principal = Depends(require_scope("pack:read")),
) -> list[VerticalPack]:
    return request.app.state.pack_registry.list_packs(industry=industry)


@router.get(
    "/{pack_id}",
    response_model=VerticalPack,
    responses={404: {"description": "Pack not found"}},
    summary="Get pack manifest + metadata",
)
async def get_pack(
    pack_id: str,
    request: Request,
    principal: Principal = Depends(require_scope("pack:read")),
) -> VerticalPack:
    pack = request.app.state.pack_registry.get(pack_id)
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pack not found")
    return pack


@router.post(
    "/{pack_id}/deploy",
    response_model=DeployResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deploy pack to one or more tenants",
)
async def deploy_pack(
    pack_id: str,
    payload: DeployRequest,
    request: Request,
    principal: Principal = Depends(require_scope("pack:deploy")),
) -> DeployResponse:
    registry = request.app.state.pack_registry
    if registry.get(pack_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pack not found")

    deployments = [
        registry.deploy(pack_id, tenant_id, payload.params) for tenant_id in payload.tenant_ids
    ]
    log.info("pack.deployed", pack_id=pack_id, count=len(deployments), by=principal.subject)
    return DeployResponse(pack_id=pack_id, deployments=deployments)


@router.get(
    "/{pack_id}/customers",
    response_model=list[PackDeployment],
    summary="List tenants the pack is deployed to",
)
async def pack_customers(
    pack_id: str,
    request: Request,
    principal: Principal = Depends(require_scope("pack:read")),
) -> list[PackDeployment]:
    registry = request.app.state.pack_registry
    if registry.get(pack_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pack not found")
    return registry.deployments_for(pack_id)

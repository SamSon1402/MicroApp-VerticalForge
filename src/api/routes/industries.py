"""Industries catalog — list supported industries and their target customer counts."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth.deps import require_user
from src.auth.oidc import Principal
from src.models.pack import INDUSTRY_CUSTOMER_COUNT, Industry

router = APIRouter(prefix="/api/industries", tags=["catalog"])


class IndustryEntry(BaseModel):
    id: Industry
    label: str
    customer_count: int


@router.get("", response_model=list[IndustryEntry], summary="List supported industries")
async def list_industries(
    _: Principal = Depends(require_user),
) -> list[IndustryEntry]:
    labels = {
        Industry.RETAIL: "Retail",
        Industry.HOSPITALITY: "Hospitality",
        Industry.MANUFACTURING: "Manufacturing",
        Industry.TECHNOLOGY: "Technology",
    }
    return [
        IndustryEntry(id=ind, label=labels[ind], customer_count=cnt)
        for ind, cnt in INDUSTRY_CUSTOMER_COUNT.items()
    ]

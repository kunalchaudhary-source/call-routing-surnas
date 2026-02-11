from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, validator

from backend.services.leads import upsert_call_lead

router = APIRouter(prefix="/call-context", tags=["call-context"])

ALLOWED_CATEGORIES = {
    "necklace",
    "bangles",
    "bracelets",
    "earrings",
    "curated combination",
    "accessories",
}


class CallContextPayload(BaseModel):
    call_sid: str = Field(..., min_length=10)
    page_context: Literal["home", "product"] = "home"
    currency: Literal["INR", "USD", "EUR", "AED"] = "INR"
    user_type: Literal["guest", "identified"] = "guest"
    customer_id: Optional[str] = None
    product_id: Optional[str] = None
    product_category: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator("product_category")
    def _normalize_category(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CATEGORIES:
            raise ValueError("Unsupported category")
        return normalized


class CallContextResponse(BaseModel):
    lead_id: str
    preferred_language: str


@router.post("", response_model=CallContextResponse)
async def register_call_context(payload: CallContextPayload) -> CallContextResponse:
    lead = upsert_call_lead(payload.dict())
    return CallContextResponse(lead_id=str(lead.id), preferred_language=lead.preferred_language or "en-IN")

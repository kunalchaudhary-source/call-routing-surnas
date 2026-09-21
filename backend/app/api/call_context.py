"""API route for web callers to register browser session context."""

from fastapi import APIRouter
from app.models.schemas import CallContextPayload, CallContextResponse
from app.services.lead_service import upsert_call_lead

router = APIRouter(prefix="/call-context", tags=["call-context"])


@router.post("", response_model=CallContextResponse)
async def register_call_context(payload: CallContextPayload) -> CallContextResponse:
    lead = upsert_call_lead(payload.dict(exclude_none=True))
    return CallContextResponse(
        lead_id=str(lead.id),
        preferred_language=lead.preferred_language or "en-IN",
    )

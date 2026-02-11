from fastapi import APIRouter

from .voice import router as voice
from .call_context import router as call_context_router
from .twilio_adapter import router as twilio_router

router = APIRouter()

router.include_router(voice)
router.include_router(call_context_router)
router.include_router(twilio_router)


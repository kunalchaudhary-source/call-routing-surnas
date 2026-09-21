"""API routers package."""

from fastapi import APIRouter

from app.api.plivo import router as plivo_router
from app.api.twilio import router as twilio_router
from app.api.admin import router as admin_router
from app.api.call_context import router as call_context_router
from app.api.health import router as health_router

router = APIRouter()

# Telephony routes: Plivo under /api/plivo and /plivo
router.include_router(plivo_router, prefix="/api/plivo")
router.include_router(plivo_router, prefix="/plivo")

# Telephony routes: Twilio under root (/voice) and /twilio
router.include_router(twilio_router)

# Admin, Call context, and Health
router.include_router(admin_router)
router.include_router(call_context_router)
router.include_router(health_router)

__all__ = ["router"]

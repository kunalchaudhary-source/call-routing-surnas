from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse

from backend.routes.voice import voice as voice_endpoint, voice_category_name as voice_category_endpoint
from backend.services.logger import log_event


router = APIRouter(prefix="/twilio")


@router.post("/incoming-call")
async def incoming_call(request: Request) -> Response:
    """Compatibility endpoint for older Twilio webhook URL names."""
    # Delegate to the main voice handler
    return await voice_endpoint(request)


@router.post("/incoming-call/category")
async def incoming_call_category(request: Request) -> Response:
    return await voice_category_endpoint(request)


@router.post("/call-status")
async def call_status(request: Request):
    form = await request.form()
    log_event(None, "TWILIO_CALL_STATUS", {"form": dict(form)})
    return JSONResponse({"status": "ok"})


@router.post("/error-log")
async def error_log(request: Request):
    form = await request.form()
    log_event(None, "TWILIO_ERROR_LOG", {"form": dict(form)})
    return JSONResponse({"status": "ok"})


@router.post("/fallback")
async def fallback(request: Request):
    """Fallback webhook for Twilio: treat like an incoming call when primary
    webhook fails. Logs the form and delegates to the main `voice` handler so
    callers still receive IVR TwiML.
    """
    form = await request.form()
    log_event(None, "TWILIO_FALLBACK", {"form": dict(form)})
    # Delegate to the main voice handler (same behavior as /incoming-call)
    return await voice_endpoint(request)

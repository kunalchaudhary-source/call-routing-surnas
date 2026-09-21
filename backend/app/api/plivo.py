"""Plivo voice IVR webhook routes (India phone routing).

Provides complete IVR flow for Indian phone calls:
1. Greeting + Menu
2. Name collection + profanity check
3. Flow continuation (Product / Category / Order Status)
4. Description collection & Cloud Run CRM lead synchronization
5. Outbound agent connection via Plivo <Dial> with verified caller ID.
"""

from fastapi import APIRouter, Request, Response

from app.providers.plivo_provider import PlivoProvider, PlivoXmlDocument
from app.services.dialog_engine import DialogEngine
from app.services.calls_service import ensure_call_from_plivo
from app.services.lead_service import link_lead_to_call
from app.core.logger import log_event

router = APIRouter(tags=["plivo"])

provider = PlivoProvider()
engine = DialogEngine(provider=provider, base_route_prefix="/api/plivo")


async def _extract_metadata(request: Request) -> dict:
    form = await request.form() if request.method == "POST" else request.query_params
    meta = provider.extract_call_metadata(dict(form))
    call = ensure_call_from_plivo(form)
    if call and meta.get("call_sid"):
        link_lead_to_call(meta["call_sid"], call.id)
    return meta


@router.api_route("/voice", methods=["GET", "POST"])
@router.api_route("/incoming-call", methods=["GET", "POST"])
@router.api_route("/answer", methods=["GET", "POST"])
async def plivo_entry(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_incoming_call(request, meta)


@router.api_route("/voice/intent", methods=["GET", "POST"])
async def plivo_intent(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_intent(request, meta)


@router.api_route("/voice/name", methods=["GET", "POST"])
async def plivo_name(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_name(request, meta)


@router.api_route("/voice/name-fallback", methods=["GET", "POST"])
async def plivo_name_fallback(request: Request) -> Response:
    meta = await _extract_metadata(request)
    log_event(meta.get("call_sid"), "CALLER_NAME_SKIPPED", {})
    return engine.continue_after_name(request, meta)


@router.api_route("/voice/assist-type", methods=["GET", "POST"])
async def plivo_assist_type(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_assist_type(request, meta)


@router.api_route("/voice/product-id", methods=["GET", "POST"])
async def plivo_product_id(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_product_id(request, meta)


@router.api_route("/voice/product-category", methods=["GET", "POST"])
async def plivo_product_category(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_category(request, meta)


@router.api_route("/voice/price-product", methods=["GET", "POST"])
async def plivo_price_product(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_product_id(request, meta)


@router.api_route("/voice/order-status-id", methods=["GET", "POST"])
async def plivo_order_status_id(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_order_status_id(request, meta)


@router.api_route("/voice/description", methods=["GET", "POST"])
async def plivo_description(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_description(request, meta)


@router.api_route("/voice/dial-agent", methods=["GET", "POST"])
async def plivo_dial_agent(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.connect_to_agent(request, meta)


@router.api_route("/voice/dial-complete", methods=["GET", "POST"])
async def plivo_dial_complete(request: Request) -> Response:
    form = await request.form() if request.method == "POST" else request.query_params
    raw_form = dict(form)
    meta = provider.extract_call_metadata(raw_form)
    return engine.handle_dial_complete(request, meta, raw_form)


@router.api_route("/call-status", methods=["GET", "POST"])
@router.api_route("/hangup", methods=["GET", "POST"])
@router.api_route("/status", methods=["GET", "POST"])
async def plivo_call_status(request: Request):
    form = await request.form() if request.method == "POST" else request.query_params
    call_uuid = form.get("CallUUID") or form.get("CallSid")
    log_event(call_uuid, "PLIVO_CALL_STATUS", {"form": dict(form)})
    return {"status": "ok"}


@router.api_route("/fallback", methods=["GET", "POST"])
async def plivo_fallback(request: Request) -> Response:
    meta = await _extract_metadata(request)
    log_event(meta.get("call_sid"), "PLIVO_FALLBACK_TRIGGERED", {"metadata": meta})
    return engine.handle_incoming_call(request, meta)

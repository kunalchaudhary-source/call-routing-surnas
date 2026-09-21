"""Twilio voice IVR webhook routes (US phone routing).

Provides complete IVR flow for US phone calls:
1. Greeting + Menu
2. Name collection + profanity check
3. Flow continuation (Product / Category / Order Status)
4. Description collection & Cloud Run CRM lead synchronization
5. Outbound agent connection via Twilio <Dial>
"""

from fastapi import APIRouter, Request, Response
from twilio.twiml.voice_response import VoiceResponse

from app.providers.twilio_provider import TwilioProvider
from app.services.dialog_engine import DialogEngine
from app.services.calls_service import ensure_call_from_twilio
from app.services.lead_service import link_lead_to_call
from app.core.logger import log_event

router = APIRouter(tags=["twilio"])

provider = TwilioProvider()
engine = DialogEngine(provider=provider, base_route_prefix="")


async def _extract_metadata(request: Request) -> dict:
    form = await request.form() if request.method == "POST" else request.query_params
    meta = provider.extract_call_metadata(dict(form))
    call = ensure_call_from_twilio(form)
    if call and meta.get("call_sid"):
        link_lead_to_call(meta["call_sid"], call.id)
    return meta


@router.api_route("/voice", methods=["GET", "POST"])
@router.api_route("/twilio/voice", methods=["GET", "POST"])
@router.api_route("/twilio/incoming-call", methods=["GET", "POST"])
async def twilio_entry(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_incoming_call(request, meta)


@router.api_route("/voice/intent", methods=["GET", "POST"])
@router.api_route("/twilio/voice/intent", methods=["GET", "POST"])
async def twilio_intent(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_intent(request, meta)


@router.api_route("/voice/name", methods=["GET", "POST"])
@router.api_route("/twilio/voice/name", methods=["GET", "POST"])
async def twilio_name(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_name(request, meta)


@router.api_route("/voice/name-fallback", methods=["GET", "POST"])
@router.api_route("/twilio/voice/name-fallback", methods=["GET", "POST"])
async def twilio_name_fallback(request: Request) -> Response:
    meta = await _extract_metadata(request)
    log_event(meta.get("call_sid"), "CALLER_NAME_SKIPPED", {})
    return engine.continue_after_name(request, meta)


@router.api_route("/voice/assist-type", methods=["GET", "POST"])
@router.api_route("/twilio/voice/assist-type", methods=["GET", "POST"])
async def twilio_assist_type(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_assist_type(request, meta)


@router.api_route("/voice/product-id", methods=["GET", "POST"])
@router.api_route("/twilio/voice/product-id", methods=["GET", "POST"])
async def twilio_product_id(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_product_id(request, meta)


@router.api_route("/voice/product-category", methods=["GET", "POST"])
@router.api_route("/twilio/voice/product-category", methods=["GET", "POST"])
async def twilio_product_category(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_category(request, meta)


@router.api_route("/voice/price-product", methods=["GET", "POST"])
@router.api_route("/twilio/voice/price-product", methods=["GET", "POST"])
async def twilio_price_product(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_product_id(request, meta)


@router.api_route("/voice/order-status-id", methods=["GET", "POST"])
@router.api_route("/twilio/voice/order-status-id", methods=["GET", "POST"])
async def twilio_order_status_id(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_order_status_id(request, meta)


@router.api_route("/voice/description", methods=["GET", "POST"])
@router.api_route("/twilio/voice/description", methods=["GET", "POST"])
async def twilio_description(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.handle_description(request, meta)


@router.api_route("/voice/dial-agent", methods=["GET", "POST"])
@router.api_route("/twilio/voice/dial-agent", methods=["GET", "POST"])
async def twilio_dial_agent(request: Request) -> Response:
    meta = await _extract_metadata(request)
    return engine.connect_to_agent(request, meta)


@router.api_route("/voice/dial-complete", methods=["GET", "POST"])
@router.api_route("/twilio/voice/dial-complete", methods=["GET", "POST"])
async def twilio_dial_complete(request: Request) -> Response:
    form = await request.form() if request.method == "POST" else request.query_params
    raw_form = dict(form)
    meta = provider.extract_call_metadata(raw_form)
    return engine.handle_dial_complete(request, meta, raw_form)

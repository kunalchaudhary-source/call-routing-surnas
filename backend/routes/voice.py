"""Voice IVR routes for Twilio webhook handling.

New simplified flow:
1. Greeting → Menu (General Inquiry / Try Near You / Price Request)
2. General Inquiry or Try Near You → Product vs Category → Collect info → Connect
3. Price Request → Collect Product Name → Connect
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Request, Response
from twilio.twiml.voice_response import Gather, VoiceResponse, Dial
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from backend.config import get_settings
from backend.services import config_service
from backend.services import gemini_service
from backend.services.agent_selector import get_agent_candidates
from backend.services.calls import ensure_call_from_twilio
from backend.services.leads import (
    derive_language_from_lead,
    get_lead_by_call_sid,
    link_lead_to_call,
    record_category_selection,
    record_intent,
    record_assist_type,
    record_product_id,
    record_description,
    record_full_interaction,
    record_caller_name,
    get_caller_name,
    get_caller_intent,
    get_caller_description,
)
from backend.services.logger import log_event, logger as event_logger
from backend.services.twilio_service import get_verified_numbers
from backend.services.crm_service import create_lead_in_crm


router = APIRouter()

settings = get_settings()

# Voice configuration
VOICE_NAME = "Polly.Aditi"
LANGUAGE_CODE = "en-IN"
SPEECH_RECOGNITION_LANGUAGE = "en-IN"


def say_slow(container, text: str, voice: str = VOICE_NAME, language: str = LANGUAGE_CODE, pause_len: float = 0.5):
    """Speak `text` in smaller chunks with short pauses to sound slower and clearer.

    `container` can be a `VoiceResponse` or `Gather` instance (both support `say` and `pause`).
    """
    if not text:
        return
    import re
    # Normalize whitespace
    t = re.sub(r"\s+", " ", text).strip()
    # Split into sentence-like chunks first
    chunks = re.split(r'(?<=[\.!?])\s+', t)
    # Twilio <Pause> requires an integer `length`; ceil fractional seconds to the
    # next integer to avoid invalid XML (Twilio will warn otherwise).
    import math
    try:
        pause_int = math.ceil(pause_len)
        if pause_int < 1:
            pause_int = 1
    except Exception:
        pause_int = 1
    for chunk in chunks:
        if not chunk:
            continue
        # If chunk long, also split on commas for breath points
        sub = [c.strip() for c in chunk.split(",") if c.strip()]
        for piece in sub:
            try:
                container.say(piece, voice=voice, language=language)
            except Exception:
                # Fallback: try without voice/lang
                try:
                    container.say(piece)
                except Exception:
                    pass
            # Insert a short pause to slow pacing
            try:
                container.pause(length=pause_int)
            except Exception:
                # some containers may not support pause; ignore
                pass


# The IVR only accepts these category values (speech synonyms are mapped to these).
ALLOWED_IVR_CATEGORIES = (
    "necklace",
    "bangles",
    "bracelets",
    "earrings",
    "rings",
    "accessories",
    "curated combination",
    "men jewellery",
    "vintage diamonds",
)

_CATEGORY_HINTS = (
    "necklace, necklaces, bangles, bracelets, earrings, rings, accessories, curated combination, men jewellery, vintage diamonds"
)

# Twilio REST client for status lookups
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _get_prompt(key: str) -> str:
    """Fetch IVR prompt from config and optionally filter it through Gemini."""
    text = config_service.get_ivr_prompt(key)
    try:
        return gemini_service.filter_text_if_enabled(text)
    except Exception:
        return text


def _normalize_transcript(text: str | None) -> str:
    """Normalize speech transcript for matching."""
    if not text:
        return ""
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _resolve_category(speech: str | None) -> str | None:
    """Resolve a spoken category into one of the allowed canonical categories."""
    transcript = _normalize_transcript(speech)
    if not transcript:
        return None

    # Apply configurable misheard corrections (e.g., jhumka -> earrings)
    transcript = _normalize_transcript(config_service.correct_misheard_words(transcript))

    # Direct contains-match mapping (longer phrases first)
    variants_to_canonical: dict[str, str] = {
        "curated combination": "curated combination",
        "curated combinations": "curated combination",
        "curated combo": "curated combination",
        "men jewellery": "men jewellery",
        "mens jewellery": "men jewellery",
        "men jewelry": "men jewellery",
        "mens jewelry": "men jewellery",
        "gents jewellery": "men jewellery",
        "gents jewelry": "men jewellery",
        "necklace": "necklace",
        "necklaces": "necklace",
        "bangle": "bangles",
        "bangles": "bangles",
        "bracelet": "bracelets",
        "bracelets": "bracelets",
        "earring": "earrings",
        "earrings": "earrings",
        "ring": "rings",
        "rings": "rings",
        "accessory": "accessories",
        "accessories": "accessories",
        "vintage diamonds": "vintage diamonds",
        "vintage diamond": "vintage diamonds",
        "diamond": "vintage diamonds",
        "diamonds": "vintage diamonds",
    }

    for variant in sorted(variants_to_canonical.keys(), key=len, reverse=True):
        if variant in transcript:
            canonical = variants_to_canonical[variant]
            return canonical if canonical in ALLOWED_IVR_CATEGORIES else None

    return None


# ==================== ENTRY POINT ====================

@router.post("/voice")
async def voice(request: Request) -> Response:
    """Entry point for Twilio Voice webhook - greeting + main menu."""
    form = await request.form()

    call_sid = form.get("CallSid")
    caller_country = form.get("CallerCountry")
    from_number = form.get("From")

    # Create/update call record
    call = ensure_call_from_twilio(form)
    if call:
        link_lead_to_call(call_sid, call.id)

    log_event(call_sid, "CALL_RECEIVED", {
        "from": from_number,
        "caller_country": caller_country,
    })

    # Build greeting + menu prompt
    response = VoiceResponse()
    
    # Say greeting
    greeting = config_service.get_voice_greeting(LANGUAGE_CODE)
    say_slow(response, greeting, voice=VOICE_NAME, language=LANGUAGE_CODE)
    
    # Gather for intent selection (speech only, no DTMF required)
    gather = Gather(
        input="speech",
        action="/voice/intent",
        speech_timeout="auto",
        barge_in=True,
        speech_model="phone_call",
        language=SPEECH_RECOGNITION_LANGUAGE,
        timeout=8,
        hints="general inquiry, try near you, price request, general, inquiry, store, price, pricing",
    )
    menu_text = _get_prompt("menu")
    log_event(call_sid, "IVR_SAY", {"prompt": "menu", "message": menu_text})
    say_slow(gather, menu_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.append(gather)
    
    # If no input, reprompt
    say_slow(response, _get_prompt("reprompt"), voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.redirect("/voice")
    
    return Response(content=str(response), media_type="application/xml")


# ==================== INTENT SELECTION ====================

@router.post("/voice/intent")
async def voice_intent(request: Request) -> Response:
    """Handle the initial intent choice: general inquiry / try near you / price request.
    
    After capturing intent, ask for caller's name before continuing.
    """
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    log_event(call_sid, "INTENT_SPEECH_RECEIVED", {"speech": speech_result})

    intent = _resolve_intent(speech_result)
    
    if not intent:
        # Could not determine intent - play "invalid" and reprompt menu.
        log_event(call_sid, "INTENT_NOT_RECOGNIZED", {"speech": speech_result})
        record_intent(call_sid, "unknown")

        response = VoiceResponse()

        invalid_text = _get_prompt("invalid")
        log_event(call_sid, "IVR_SAY", {"prompt": "invalid", "message": invalid_text})
        say_slow(response, invalid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)

        gather = Gather(
            input="speech",
            action="/voice/intent",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints="general inquiry, try near you, price request, general, inquiry, store, price, pricing",
        )
        menu_text = _get_prompt("menu")
        log_event(call_sid, "IVR_SAY", {"prompt": "menu", "message": menu_text})
        say_slow(gather, menu_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        # If still no input, loop back to /voice
        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        say_slow(response, reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice")
        return Response(content=str(response), media_type="application/xml")

    # Persist choice
    record_intent(call_sid, intent)
    log_event(call_sid, "INTENT_SELECTED", {"intent": intent, "speech": speech_result})

    # Ask for caller's name before continuing
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice/name",
        speech_timeout="auto",
        barge_in=True,
        speech_model="phone_call",
        language=SPEECH_RECOGNITION_LANGUAGE,
        timeout=8,
    )
    name_text = _get_prompt("name_prompt")
    log_event(call_sid, "IVR_SAY", {"prompt": "name_prompt", "message": name_text})
    say_slow(gather, name_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.append(gather)
    
    # If no name provided, continue anyway
    response.redirect("/voice/name-fallback")
    return Response(content=str(response), media_type="application/xml")


# ==================== NAME COLLECTION ====================

@router.post("/voice/name")
async def voice_name(request: Request) -> Response:
    """Collect caller's name and continue based on their selected intent."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    caller_name = (speech_result or "").strip()
    
    if caller_name:
        # Run profanity/safety check via Gemini (or fallback blacklist)
        try:
            profane = gemini_service.is_profane(caller_name)
        except Exception:
            profane = False

        if profane:
            # Log and re-ask name using configurable prompt
            log_event(call_sid, "CALLER_NAME_PROFANITY_REJECTED", {"name": caller_name})
            response = VoiceResponse()
            # Speak the configured prompt
            bad_name_text = _get_prompt("name_profanity_failed_prompt")
            log_event(call_sid, "IVR_SAY", {"prompt": "name_profanity_failed_prompt", "message": bad_name_text})
            gather = Gather(
                input="speech",
                action="/voice/name",
                speech_timeout="auto",
                barge_in=True,
                speech_model="phone_call",
                language=SPEECH_RECOGNITION_LANGUAGE,
                timeout=8,
            )
            say_slow(gather, bad_name_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
            response.append(gather)
            # If still no valid name, fall back to name-fallback which continues the flow
            response.redirect("/voice/name-fallback")
            return Response(content=str(response), media_type="application/xml")

        # Acceptable name
        record_caller_name(call_sid, caller_name)
        log_event(call_sid, "CALLER_NAME_CAPTURED", {"name": caller_name})
    else:
        log_event(call_sid, "CALLER_NAME_NOT_PROVIDED", {})

    # Get the stored intent and continue with appropriate flow
    return await _continue_after_name(call_sid, from_number)


@router.post("/voice/name-fallback")
async def voice_name_fallback(request: Request) -> Response:
    """Continue without name if caller didn't provide one."""
    form = await request.form()
    call_sid = form.get("CallSid")
    from_number = form.get("From")

    log_event(call_sid, "CALLER_NAME_SKIPPED", {})
    return await _continue_after_name(call_sid, from_number)


async def _continue_after_name(call_sid: str, from_number: str | None) -> Response:
    """Continue the IVR flow based on stored intent after name collection."""
    lead = get_lead_by_call_sid(call_sid)
    intent = lead.extra_metadata.get("intent") if lead and lead.extra_metadata else None

    log_event(call_sid, "INTENT_LOOKUP_AFTER_NAME", {
        "intent": intent,
        "has_lead": bool(lead),
        "has_extra_metadata": bool(getattr(lead, "extra_metadata", None)),
    })

    response = VoiceResponse()
    
    if intent in ("general_inquiry", "store"):
        # Ask product vs category
        gather = Gather(
            input="speech",
            action="/voice/assist-type",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints="product, category, specific product, product category, item, type",
        )
        assist_text = _get_prompt("assist_type_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "assist_type_prompt", "message": assist_text})
        say_slow(gather, assist_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)
        
        # If no input, reprompt and re-run this step (do not connect)
        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        say_slow(response, reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/name-fallback")
        return Response(content=str(response), media_type="application/xml")

    # price_request - ask for product name directly (no separate category question)
    if intent == "price_request":
        gather = Gather(
            input="speech",
            action="/voice/price-product",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=10,
        )
        pid_text = _get_prompt("price_product_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "price_product_prompt", "message": pid_text})
        say_slow(gather, pid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        # If no input, reprompt and re-run this step (do not connect)
        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        say_slow(response, reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/name-fallback")
        return Response(content=str(response), media_type="application/xml")

    # Unknown intent - connect to default agent
    return _connect_to_default_agent(call_sid, from_number)


def _resolve_intent(speech: str | None) -> str | None:
    """Resolve initial intent from speech.

    Returns one of: "general_inquiry", "store", "price_request", or None
    """
    transcript = _normalize_transcript(speech)
    if not transcript:
        return None
    
    # price keywords
    if any(k in transcript for k in ("price", "pricing", "cost", "rate", "price request")):
        return "price_request"
    
    # store/try near you keywords
    if any(k in transcript for k in ("store", "near", "nearby", "near you", "try near you", "try near", "location")):
        return "store"
    
    # general inquiry keywords
    if any(k in transcript for k in ("general", "inquiry", "enquiry", "help", "assist", "assistance", "general inquiry")):
        return "general_inquiry"
    
    return None


# ==================== ASSIST TYPE (PRODUCT VS CATEGORY) ====================

@router.post("/voice/assist-type")
async def voice_assist_type(request: Request) -> Response:
    """Handle whether caller wants product-level help or category-level help."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    log_event(call_sid, "ASSIST_TYPE_SPEECH_RECEIVED", {"speech": speech_result})

    choice = _resolve_assist_type(speech_result)
    
    if not choice:
        # Could not determine - play invalid and re-ask
        log_event(call_sid, "ASSIST_TYPE_NOT_RECOGNIZED", {"speech": speech_result})

        response = VoiceResponse()
        invalid_text = _get_prompt("invalid")
        log_event(call_sid, "IVR_SAY", {"prompt": "invalid", "message": invalid_text})
        say_slow(response, invalid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)

        gather = Gather(
            input="speech",
            action="/voice/assist-type",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints="product, category, specific product, product category, item, type",
        )
        assist_text = _get_prompt("assist_type_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "assist_type_prompt", "message": assist_text})
        say_slow(gather, assist_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        say_slow(response, reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/name-fallback")
        return Response(content=str(response), media_type="application/xml")

    record_assist_type(call_sid, choice)
    log_event(call_sid, "ASSIST_TYPE_SELECTED", {"assist_type": choice})

    response = VoiceResponse()
    
    if choice == "product":
        # Directly ask for product name (no category follow-up)
        gather = Gather(
            input="speech",
            action="/voice/product-id",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=10,
        )
        pid_text = _get_prompt("product_id_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "product_id_prompt", "message": pid_text})
        say_slow(gather, pid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        # If no input, reprompt and retry
        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        say_slow(response, reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/name-fallback")
        return Response(content=str(response), media_type="application/xml")

    # category - ask for category name
    gather = Gather(
        input="speech",
        action="/voice/category-name",
        speech_timeout="auto",
        barge_in=True,
        speech_model="phone_call",
        language=SPEECH_RECOGNITION_LANGUAGE,
        timeout=8,
        hints=_CATEGORY_HINTS,
    )
    cat_text = _get_prompt("category_prompt")
    log_event(call_sid, "IVR_SAY", {"prompt": "category_prompt", "message": cat_text})
    say_slow(gather, cat_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.append(gather)
    
    # If no input, reprompt and retry
    reprompt_text = _get_prompt("reprompt")
    log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
    say_slow(response, reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.redirect("/voice/name-fallback")
    return Response(content=str(response), media_type="application/xml")


def _resolve_assist_type(speech: str | None) -> str | None:
    """Resolve whether caller wants product-level or category-level assistance."""
    transcript = _normalize_transcript(speech)
    if not transcript:
        return None

    # Prefer category when both tokens are present (e.g., "product category")
    has_product = any(k in transcript for k in ("product", "id", "item", "sku", "specific"))
    has_category = any(k in transcript for k in ("category", "categories", "type", "kind"))

    if has_category and has_product:
        return "category"
    if has_category:
        return "category"
    if has_product:
        return "product"
    return None


def _infer_category_from_product_name(call_sid: str, product_name: str) -> None:
    """Infer and store category from a spoken product name, if not already set.

    Uses the same category resolver as explicit category questions and only
    writes selected_category if we can confidently map into ALLOWED_IVR_CATEGORIES.
    """
    from backend.services.leads import get_lead_by_call_sid as _get_lead, record_category_selection as _record_cat

    if not product_name:
        return

    lead = _get_lead(call_sid)
    existing = getattr(lead, "selected_category", None) if lead else None
    if existing:
        return

    # First try the rule-based resolver
    resolved = _resolve_category(product_name)
    # If rule-based didn't resolve, try the Gemini classifier
    if not resolved:
        try:
            from backend.services import gemini_service
            allowed = [
                "necklace",
                "bangles",
                "bracelets",
                "earrings",
                "curated combination",
                "accessories",
                "men jewellery",
                "rings",
                "vintage diamonds",
            ]
            gemini_cat = gemini_service.infer_category_from_product(product_name, allowed)
            if gemini_cat:
                resolved = gemini_cat
        except Exception:
            resolved = None

    if resolved:
        _record_cat(call_sid, resolved)
        log_event(call_sid, "CATEGORY_INFERRED_FROM_PRODUCT_NAME", {"category": resolved, "raw_product_name": product_name})


# ==================== PRODUCT NAME COLLECTION ====================

@router.post("/voice/product-id")
async def voice_product_id(request: Request) -> Response:
    """Collect product name and connect to agent."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    product_name = (speech_result or "").strip()

    if product_name:
        # store product name (we reuse the product_id column)
        record_product_id(call_sid, product_name)
        _infer_category_from_product_name(call_sid, product_name)
        log_event(call_sid, "PRODUCT_NAME_CAPTURED", {"product_name": product_name})
    else:
        log_event(call_sid, "PRODUCT_NAME_NOT_PROVIDED", {})

        # Re-ask product name (do not connect).
        # Note: For Twilio <Gather>, when there's no speech, Twilio typically does NOT
        # call the action URL and instead continues to the next verb. In our flows,
        # the "reprompt" is spoken after <Gather> before redirecting back here.
        # To avoid callers hearing "reprompt" twice, we don't speak it again here.
        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action="/voice/product-id",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=10,
        )
        pid_text = _get_prompt("product_id_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "product_id_prompt", "message": pid_text})
        say_slow(gather, pid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text_2 = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text_2})
        say_slow(response, reprompt_text_2, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/product-id")
        return Response(content=str(response), media_type="application/xml")

    # Directly route to agent and sync CRM using collected data
    lead = get_lead_by_call_sid(call_sid)
    category = getattr(lead, "selected_category", None)
    currency = getattr(lead, "currency", None)

    _sync_crm_lead_for_call(call_sid, from_number, None)

    response = VoiceResponse()
    _append_dial_instruction(response, call_sid, category, currency, from_number)
    return Response(content=str(response), media_type="application/xml")


@router.post("/voice/product-category")
async def voice_product_category(request: Request) -> Response:
    """Capture the category for a product (general or price) and then ask for product name.

    This is invoked after the caller has already indicated they want product-level help
    (either via General Inquiry / Try Near You, or via Price Request).
    """
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    raw_category = (speech_result or "").strip()
    resolved_category = _resolve_category(raw_category)

    if resolved_category:
        record_category_selection(call_sid, resolved_category)
        log_event(call_sid, "PRODUCT_CATEGORY_CAPTURED", {"category": resolved_category, "raw": raw_category})
    elif raw_category:
        # Spoken input present, but not in allowed list
        log_event(call_sid, "PRODUCT_CATEGORY_NOT_RECOGNIZED", {"speech": raw_category, "allowed": list(ALLOWED_IVR_CATEGORIES)})

        response = VoiceResponse()
        invalid_text = _get_prompt("invalid")
        log_event(call_sid, "IVR_SAY", {"prompt": "invalid", "message": invalid_text})
        response.say(invalid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)

        gather = Gather(
            input="speech",
            action="/voice/product-category",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints=_CATEGORY_HINTS,
        )
        followup_text = _get_prompt("product_category_followup_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "product_category_followup_prompt", "message": followup_text})
        gather.say(followup_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        response.say(reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/product-category")
        return Response(content=str(response), media_type="application/xml")
    else:
        log_event(call_sid, "PRODUCT_CATEGORY_NOT_PROVIDED", {})

        # Re-ask category follow-up (do not proceed). Avoid speaking "reprompt" here
        # to prevent duplicate "reprompt" when reached via <Redirect> after a no-input.
        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action="/voice/product-category",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints=_CATEGORY_HINTS,
        )
        followup_text = _get_prompt("product_category_followup_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "product_category_followup_prompt", "message": followup_text})
        gather.say(followup_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text_2 = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text_2})
        response.say(reprompt_text_2, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/product-category")
        return Response(content=str(response), media_type="application/xml")

    # Next ask for product name (same prompt key used today)
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice/product-id",
        speech_timeout="auto",
        barge_in=True,
        speech_model="phone_call",
        language=SPEECH_RECOGNITION_LANGUAGE,
        timeout=10,
    )
    pid_text = _get_prompt("product_id_prompt")
    log_event(call_sid, "IVR_SAY", {"prompt": "product_id_prompt", "message": pid_text})
    gather.say(pid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.append(gather)

    # If no input, reprompt and retry product name
    reprompt_text = _get_prompt("reprompt")
    log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
    response.say(reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    response.redirect("/voice/product-id")
    return Response(content=str(response), media_type="application/xml")


# ==================== PRICE PRODUCT COLLECTION ====================

@router.post("/voice/price-product")
async def voice_price_product(request: Request) -> Response:
    """Collect product name for pricing and connect to agent."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    product_name = (speech_result or "").strip()
    
    if product_name:
        record_product_id(call_sid, product_name)
        _infer_category_from_product_name(call_sid, product_name)
        log_event(call_sid, "PRICE_PRODUCT_NAME_CAPTURED", {"product_name": product_name})
    else:
        log_event(call_sid, "PRICE_PRODUCT_NAME_NOT_PROVIDED", {})

        # Retry instead of dialing an agent on no/empty input
        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action="/voice/price-product",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=10,
        )
        pid_text = _get_prompt("product_id_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "product_id_prompt", "message": pid_text})
        gather.say(pid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        response.say(reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/price-product")
        return Response(content=str(response), media_type="application/xml")

    # Directly route to agent and sync CRM using collected data
    lead = get_lead_by_call_sid(call_sid)
    category = getattr(lead, "selected_category", None)
    currency = getattr(lead, "currency", None)

    _sync_crm_lead_for_call(call_sid, from_number, None)

    response = VoiceResponse()
    _append_dial_instruction(response, call_sid, category, currency, from_number)
    return Response(content=str(response), media_type="application/xml")


# ==================== CATEGORY NAME COLLECTION ====================

@router.post("/voice/category-name")
async def voice_category_name(request: Request) -> Response:
    """Collect category name and connect to agent."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    raw_category = (speech_result or "").strip()
    resolved_category = _resolve_category(raw_category)

    if resolved_category:
        record_category_selection(call_sid, resolved_category)
        log_event(call_sid, "CATEGORY_NAME_CAPTURED", {"category": resolved_category, "raw": raw_category})
    elif raw_category:
        log_event(call_sid, "CATEGORY_NAME_NOT_RECOGNIZED", {"speech": raw_category, "allowed": list(ALLOWED_IVR_CATEGORIES)})

        response = VoiceResponse()
        invalid_text = _get_prompt("invalid")
        log_event(call_sid, "IVR_SAY", {"prompt": "invalid", "message": invalid_text})
        response.say(invalid_text, voice=VOICE_NAME, language=LANGUAGE_CODE)

        gather = Gather(
            input="speech",
            action="/voice/category-name",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints=_CATEGORY_HINTS,
        )
        cat_text = _get_prompt("category_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "category_prompt", "message": cat_text})
        gather.say(cat_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text})
        response.say(reprompt_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/category-name")
        return Response(content=str(response), media_type="application/xml")
    else:
        log_event(call_sid, "CATEGORY_NAME_NOT_PROVIDED", {})

        # Re-ask category question (do not connect). Avoid speaking "reprompt" here
        # to prevent duplicate "reprompt" when reached via <Redirect> after a no-input.
        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action="/voice/category-name",
            speech_timeout="auto",
            barge_in=True,
            speech_model="phone_call",
            language=SPEECH_RECOGNITION_LANGUAGE,
            timeout=8,
            hints=_CATEGORY_HINTS,
        )
        cat_text = _get_prompt("category_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "category_prompt", "message": cat_text})
        gather.say(cat_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.append(gather)

        reprompt_text_2 = _get_prompt("reprompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "reprompt", "message": reprompt_text_2})
        response.say(reprompt_text_2, voice=VOICE_NAME, language=LANGUAGE_CODE)
        response.redirect("/voice/category-name")
        return Response(content=str(response), media_type="application/xml")

    # Directly route to agent and sync CRM using collected data
    lead = get_lead_by_call_sid(call_sid)
    selected_category = resolved_category if resolved_category else getattr(lead, "selected_category", None)

    # Ensure CRM lead is sent even if /voice/description is never hit
    _sync_crm_lead_for_call(call_sid, from_number, None)

    response = VoiceResponse()
    _append_dial_instruction(response, call_sid, selected_category, getattr(lead, "currency", None), from_number)
    return Response(content=str(response), media_type="application/xml")


# ==================== DESCRIPTION COLLECTION ====================

@router.post("/voice/description")
async def voice_description(request: Request) -> Response:
    """Collect caller description, create CRM lead, and connect to agent."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    description = (speech_result or "").strip()
    
    if description:
        record_description(call_sid, description)
        log_event(call_sid, "CALLER_DESCRIPTION_CAPTURED", {"description": description})

    # Get all collected lead data
    lead = get_lead_by_call_sid(call_sid)
    category = getattr(lead, "selected_category", None)
    product_id = getattr(lead, "product_id", None)
    
    # Get stored data from extra_metadata
    caller_name = None
    intent = None
    caller_description = description
    if lead and lead.extra_metadata:
        caller_name = lead.extra_metadata.get("caller_name")
        intent = lead.extra_metadata.get("intent")
        if not caller_description:
            caller_description = lead.extra_metadata.get("caller_description")

    # Create/update CRM lead before routing
    _sync_crm_lead_for_call(call_sid, from_number, caller_description)

    # Connect to agent
    response = VoiceResponse()
    _append_dial_instruction(response, call_sid, category, getattr(lead, "currency", None), from_number)
    return Response(content=str(response), media_type="application/xml")


# ==================== HELPER FUNCTIONS ====================

def _sync_crm_lead_for_call(call_sid: str, from_number: str | None, override_description: str | None = None) -> None:
    """Ensure a single CRM lead is created for this call using stored answers.

    Called right before routing to a human so that all collected IVR data
    (intent, name, category/product, description) is sent to CRM.
    """
    # Avoid duplicate CRM leads: if we've already synced one for this call, skip
    from backend.db import SessionLocal
    from backend.models.db_models import Call, CallEvent
    from datetime import datetime

    db = SessionLocal()
    try:
        call = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
        if call:
            existing = db.query(CallEvent).filter(
                CallEvent.call_id == call.id,
                CallEvent.event_type.in_(["CRM_LEAD_CREATED", "CRM_LEAD_SYNCED"]),
            ).first()
            if existing:
                return
    except Exception:
        # If we can't check, continue and attempt to create
        pass
    finally:
        db.close()

    # Gather latest lead data
    lead = get_lead_by_call_sid(call_sid)
    category = getattr(lead, "selected_category", None)
    product_id = getattr(lead, "product_id", None)

    caller_name = None
    intent = None
    caller_description = override_description
    if lead and lead.extra_metadata:
        caller_name = lead.extra_metadata.get("caller_name")
        intent = lead.extra_metadata.get("intent")
        if not caller_description:
            caller_description = lead.extra_metadata.get("caller_description")

    # Fallback: if caller_name is still missing, read it from the last
    # CALLER_NAME_CAPTURED event for this call so CRM always sees the name
    if not caller_name:
        from backend.db import SessionLocal as _SessionLocal
        from backend.models.db_models import Call as _Call, CallEvent as _CallEvent
        db2 = _SessionLocal()
        try:
            call_row = db2.query(_Call).filter_by(twilio_call_sid=call_sid).one_or_none()
            q = db2.query(_CallEvent).filter(_CallEvent.event_type == "CALLER_NAME_CAPTURED")
            if call_row:
                q = q.filter(_CallEvent.call_id == call_row.id)
            q = q.order_by(_CallEvent.created_at.desc())
            ev = q.first()
            if ev and isinstance(ev.event_payload, dict):
                caller_name = ev.event_payload.get("name") or caller_name
        finally:
            db2.close()

    try:
        crm_lead_id = create_lead_in_crm(
            call_sid=call_sid,
            caller_name=caller_name,
            mobile_phone=from_number,
            intent=intent,
            product_id=product_id,
            category=category,
            description=caller_description,
        )
        if crm_lead_id:
            log_event(call_sid, "CRM_LEAD_SYNCED", {"lead_id": crm_lead_id})
            try:
                event_logger.info(f"CRM_LEAD_SENT: call_sid={call_sid} lead_id={crm_lead_id}")
            except Exception:
                # Last-resort console hint
                print({"call_sid": call_sid, "event": "CRM_LEAD_SENT", "lead_id": crm_lead_id})
    except Exception as e:
        log_event(call_sid, "CRM_LEAD_ERROR", {"error": str(e)})

def _connect_to_default_agent(call_sid: str, from_number: str | None) -> Response:
    """Connect to default agent when no specific category/intent is selected.
    
    Other than persisting to Postgres, this path does NOT create a CRM lead.
    """
    log_event(call_sid, "CONNECTING_TO_DEFAULT_AGENT", {})

    response = VoiceResponse()
    conn_text = _get_prompt("connecting")
    log_event(call_sid, "IVR_SAY", {"prompt": "connecting", "message": conn_text})
    response.say(conn_text, voice=VOICE_NAME, language=LANGUAGE_CODE)
    _append_dial_instruction(response, call_sid, None, None, from_number)
    return Response(content=str(response), media_type="application/xml")


def _append_dial_instruction(
    response: VoiceResponse,
    call_sid: str,
    category: str | None,
    currency: str | None,
    incoming_number: str | None = None,
) -> None:
    """Append dial instruction to connect to appropriate agent."""
    # Get an ordered list of candidate phone numbers to try
    candidates = get_agent_candidates(category, currency, limit=5)
    log_event(call_sid, "ROUTING_CANDIDATES", {"category": category, "currency": currency, "candidates": candidates})

    if not candidates:
        # No agents configured
        log_event(call_sid, "NO_AGENT_CONFIGURED", {"category": category, "currency": currency})
        response.say(
            _get_prompt("no_agent"),
            voice=VOICE_NAME,
            language=LANGUAGE_CODE,
        )
        return

    # Filter to verified numbers if configured
    verified = getattr(settings, "VERIFIED_OUTBOUND_NUMBERS", [])
    if not verified:
        verified = get_verified_numbers()

    if verified:
        filtered = [c for c in candidates if c in verified]
        log_event(call_sid, "FILTERED_ROUTING_CANDIDATES", {"before": candidates, "after": filtered})
        candidates = filtered

    if not candidates:
        response.say(
            _get_prompt("no_agent"),
            voice=VOICE_NAME,
            language=LANGUAGE_CODE,
        )
        return

    # Announce connection
    response.say(_get_prompt("connecting"), voice=VOICE_NAME, language=LANGUAGE_CODE)

    # Choose caller ID
    caller_id = _get_caller_id(candidates, incoming_number)
    log_event(call_sid, "DIAL_ATTEMPT", {"candidates": candidates, "timeout": 20, "caller_id": caller_id})
    try:
        event_logger.info(f"ROUTING_BEGIN: call_sid={call_sid} candidates={candidates} caller_id={caller_id}")
    except Exception:
        print({"call_sid": call_sid, "event": "ROUTING_BEGIN", "candidates": candidates, "caller_id": caller_id})

    # Build dial instruction
    # Include action callback so we can log status after the dial finishes
    dial = Dial(timeout=20, callerId=caller_id, action="/voice/dial-complete", method="POST") if caller_id else Dial(timeout=20, action="/voice/dial-complete", method="POST")
    for num in candidates:
        dial.number(num)

    response.append(dial)


@router.post("/voice/dial-complete")
async def voice_dial_complete(request: Request) -> Response:
    """Twilio calls this after <Dial> finishes to report status.

    Logs which agent number was connected, status, and duration.
    """
    form = await request.form()
    call_sid = form.get("CallSid")
    dial_call_sid = form.get("DialCallSid")
    dial_status = form.get("DialCallStatus")
    dial_duration = form.get("DialCallDuration")

    to_number = None
    try:
        if dial_call_sid:
            c = twilio_client.calls(dial_call_sid).fetch()
            to_number = getattr(c, "to", None)
    except TwilioRestException as tre:
        log_event(call_sid, "TWILIO_DIAL_CALL_FETCH_FAILED", {"status": tre.status, "code": tre.code, "msg": str(tre), "dial_call_sid": dial_call_sid})
    except Exception as exc:
        log_event(call_sid, "TWILIO_DIAL_CALL_FETCH_ERROR", {"error": str(exc), "dial_call_sid": dial_call_sid})

    # Try to map number to agent in DB
    agent_info = None
    if to_number:
        try:
            from backend.db import SessionLocal
            from backend.models.db_models import Agent
            db = SessionLocal()
            try:
                # Query for agent by phone number. Use defensive logic in case
                # duplicate rows exist (MultipleResultsFound) — pick the first and log.
                try:
                    agent = db.query(Agent).filter(Agent.phone_number == to_number).one_or_none()
                except Exception as multi_exc:
                    # Fall back to fetching all matches and choose the first
                    try:
                        rows = db.query(Agent).filter(Agent.phone_number == to_number).all()
                        if rows:
                            agent = rows[0]
                            log_event(call_sid, "AGENT_LOOKUP_MULTIPLE", {"phone_number": to_number, "count": len(rows)})
                        else:
                            agent = None
                    except Exception:
                        agent = None

                if agent:
                    agent_info = {"agent_id": agent.id, "name": agent.name, "region": agent.region, "phone_number": agent.phone_number}
            finally:
                db.close()
        except Exception as exc:
            log_event(call_sid, "AGENT_LOOKUP_ERROR", {"error": str(exc), "phone_number": to_number})

    log_event(call_sid, "DIAL_COMPLETED", {
        "dial_call_sid": dial_call_sid,
        "status": dial_status,
        "duration": dial_duration,
        "to": to_number,
        "agent": agent_info,
    })

    # No further IVR action — this is just a logging callback
    return Response(content=str(VoiceResponse()), media_type="application/xml")


def _get_caller_id(candidates: list[str], incoming_number: str | None) -> str | None:
    """Determine the best caller ID to use for outbound dialing."""
    try:
        available_verified = getattr(settings, "VERIFIED_OUTBOUND_NUMBERS", []) or get_verified_numbers()
    except Exception:
        available_verified = []

    # Exclude the incoming caller's number
    if incoming_number and available_verified:
        available_verified = [v for v in available_verified if v != incoming_number]

    # Exclude candidates (don't dial same number as caller ID)
    if available_verified:
        available_verified = [v for v in available_verified if v not in candidates]

    # Prefer explicit TWILIO_CALLER_ID
    preferred = getattr(settings, "TWILIO_CALLER_ID", None)
    if preferred and available_verified and preferred in available_verified and preferred not in candidates:
        return preferred

    # Use first available verified number matching candidate country
    if available_verified and candidates:
        def _country_prefix(num: str) -> str:
            if not num or not num.startswith("+"):
                return ""
            if num.startswith("+91"):
                return "+91"
            if num.startswith("+1"):
                return "+1"
            return num[:3]

        cand_pref = _country_prefix(candidates[0])
        match = next((v for v in available_verified if _country_prefix(v) == cand_pref), None)
        return match or available_verified[0]

    return None

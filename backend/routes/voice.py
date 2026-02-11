from __future__ import annotations

import re

from fastapi import APIRouter, Request, Response
from twilio.twiml.voice_response import Gather, VoiceResponse, Dial

from backend.config import get_settings
from backend.services import config_service
from backend.services.agent_selector import pick_agent, get_agent_candidates
from backend.services.calls import ensure_call_from_twilio
from backend.services.leads import (
    derive_language_from_lead,
    get_lead_by_call_sid,
    link_lead_to_call,
    record_category_selection,
)
from backend.services.logger import log_event
from backend.services.twilio_service import get_verified_numbers


router = APIRouter()

settings = get_settings()

CATEGORY_BY_DIGIT = {
    "1": "necklace",
    "2": "bangles",
    "3": "bracelets",
    "4": "earrings",
    "5": "curated combination",
    "6": "accessories",
}

CATEGORY_KEYWORDS = {
    "necklace": ["necklace", "necklaces", "haar"],
    "bangles": ["bangle", "bangles", "kada"],
    "bracelets": ["bracelet", "bracelets"],
    "earrings": ["earring", "earrings", "jhumka", "chandbali"],
    "curated combination": ["curated", "combination", "set", "combo"],
    "accessories": ["accessory", "accessories", "maang tikka", "kamarband"],
}

CATEGORY_LABELS = {
    "necklace": "necklaces",
    "bangles": "bangles",
    "bracelets": "bracelets",
    "earrings": "earrings",
    "curated combination": "curated combinations",
    "accessories": "accessories",
}

SPOKEN_NUMBER_ALIASES = {
    "1": ["1", "one", "won", "wan", "ek"],
    "2": ["2", "two", "too", "tu", "do"],
    "3": ["3", "three", "tree", "teen", "tin"],
    "4": ["4", "four", "for", "phor", "char", "chaar"],
    "5": ["5", "five", "faiv", "paanch", "panch"],
    "6": ["6", "six", "sicks", "che", "chhe", "cheh"],
}

VOICE_BY_LANGUAGE = {
    "hi-IN": "Polly.Aditi",
    "en-IN": "Polly.Aditi",
}

SPEECH_RECOGNITION_LANGUAGE = "en-IN"


@router.post("/voice")
async def voice(request: Request) -> Response:
    """Entry point for Twilio Voice webhook."""
    form = await request.form()

    call_sid = form.get("CallSid")
    caller_country = form.get("CallerCountry")
    from_number = form.get("From")

    call = ensure_call_from_twilio(form)
    if call:
        link_lead_to_call(call_sid, call.id)

    lead = get_lead_by_call_sid(call_sid)
    # IVR should always speak in English; human agents may switch to Hindi as needed.
    language_code = "en-IN"
    # Force Indian-accented Polly voice for IVR
    voice_name = "Polly.Aditi"

    log_event(call_sid, "CALL_RECEIVED", {
        "from": from_number,
        "caller_country": caller_country,
        "lead_context": {
            "page_context": getattr(lead, "page_context", None),
            "currency": getattr(lead, "currency", None),
            "user_type": getattr(lead, "user_type", None),
        },
    })

    # If website already told us the product/category, skip menu and connect straight away
    if lead and lead.page_context == "product" and lead.selected_category:
        log_event(call_sid, "DIRECT_CONNECT", {
            "category": lead.selected_category,
            "currency": lead.currency,
        })
        response = VoiceResponse()
        response.say(
            _confirmation_prompt(lead.selected_category, language_code),
            voice=voice_name,
            language=language_code,
        )
        _append_dial_instruction(response, call_sid, lead.selected_category, lead.currency, language_code, from_number)
        return Response(content=str(response), media_type="application/xml")

    return Response(
        content=str(_build_category_prompt(language_code, voice_name)),
        media_type="application/xml",
    )


@router.post("/voice/category")
async def voice_category(request: Request) -> Response:
    """Handle category selection from DTMF or speech and connect to an agent."""
    form = await request.form()
    call_sid = form.get("CallSid")
    digits = form.get("Digits")
    speech_result = form.get("SpeechResult")
    from_number = form.get("From")

    lead = get_lead_by_call_sid(call_sid)
    # IVR should always speak in English; human agents may switch to Hindi as needed.
    language_code = "en-IN"
    # Force Indian-accented Polly voice for IVR
    voice_name = "Polly.Aditi"

    category = _resolve_category(digits, speech_result)

    if not category:
        log_event(call_sid, "INVALID_SELECTION", {"digits": digits, "speech": speech_result})
        response = _build_category_prompt(language_code, voice_name)
        response.say(
            config_service.get_ivr_prompt("invalid"),
            voice=voice_name,
            language=language_code,
        )
        response.redirect("/voice")
        return Response(content=str(response), media_type="application/xml")

    record_category_selection(call_sid, category)
    log_event(call_sid, "CATEGORY_SELECTED", {"category": category, "digits": digits, "speech": speech_result})

    response = VoiceResponse()
    response.say(
        _confirmation_prompt(category, language_code),
        voice=voice_name,
        language=language_code,
    )
    _append_dial_instruction(
        response,
        call_sid,
        category,
        getattr(lead, "currency", None),
        language_code,
        from_number,
    )

    return Response(content=str(response), media_type="application/xml")


def _build_category_prompt(language_code: str, voice_name: str) -> VoiceResponse:
    response = VoiceResponse()
    response.say(config_service.get_voice_greeting(language_code), voice=voice_name, language=language_code)
    gather = Gather(
        input="dtmf speech",
        action="/voice/category",
        speech_timeout="auto",
        barge_in=True,
        speech_model="phone_call",
        language=SPEECH_RECOGNITION_LANGUAGE,
        timeout=6,
        hints="necklace bangle bracelet earring curated combination accessorie man jewellery ring Vintage diamond",
    )
    gather.say(config_service.get_ivr_prompt("menu"), voice=voice_name, language=language_code)
    response.append(gather)
    response.say(config_service.get_ivr_prompt("reprompt"), voice=voice_name, language=language_code)
    return response


def _append_dial_instruction(
    response: VoiceResponse,
    call_sid: str,
    category: str,
    currency: str | None,
    language_code: str | None,
    incoming_number: str | None = None,
) -> None:
    # Get an ordered list of candidate phone numbers to try
    candidates = get_agent_candidates(category, currency, limit=5)
    log_event(call_sid, "ROUTING_CANDIDATES", {"category": category, "currency": currency, "candidates": candidates})

    if not candidates:
        # Fallback to single pick
        agent, target_number = pick_agent(category, currency)
        response.dial(target_number)
        return

    # If operator configured verified-only outbound numbers (useful for Twilio trial accounts),
    # filter candidates to avoid dialing unverified numbers that will fail immediately.
    verified = getattr(settings, "VERIFIED_OUTBOUND_NUMBERS", [])
    if not verified:
        # No explicit list configured; try fetching verified numbers from Twilio account
        verified = get_verified_numbers()

    if verified:
        filtered = [c for c in candidates if c in verified]
        log_event(call_sid, "FILTERED_ROUTING_CANDIDATES", {"before": candidates, "after": filtered})
        candidates = filtered

    # If after filtering there are no dialable targets, inform the caller instead of attempting dial
    if not candidates:
        response.say(
            _copy({
                "en-IN": "Sorry — we cannot connect your call right now. Please try again later.",
            }, language_code or "en-IN"),
            voice=VOICE_BY_LANGUAGE.get(language_code or "en-IN"),
            language=language_code or "en-IN",
        )
        return

    # Announce connection attempt and use a 20s timeout so Twilio moves to the next candidate
    CONNECTING_PROMPTS = {
        "en-IN": "Please wait while we connect you to our expert.",
    }
    response.say(
        _copy(CONNECTING_PROMPTS, language_code or "en-IN"),
        voice=VOICE_BY_LANGUAGE.get(language_code or "en-IN"),
        language=language_code or "en-IN",
    )

    # Build a Dial that times out after 20 seconds per attempt and tries candidates sequentially
    # Choose a callerId (a Twilio-owned/verified number) to use as the outbound Caller ID.
    caller_id = None
    try:
        available_verified = getattr(settings, "VERIFIED_OUTBOUND_NUMBERS", []) or get_verified_numbers()
    except Exception:
        available_verified = []

    # Never consider the inbound caller's number as a valid callerId
    if incoming_number and available_verified:
        available_verified = [v for v in available_verified if v != incoming_number]

    # Avoid using one of the dial candidates as the outbound callerId —
    # callerId should be an account-owned number that is NOT the same as
    # the destination we're dialing (Twilio may reject a callerId that
    # equals the callee or that is DNO-listed).
    if available_verified:
        available_verified = [v for v in available_verified if v not in candidates]

    # Log available verified numbers for debugging purposes
    log_event(call_sid, "AVAILABLE_VERIFIED", {"available_verified": available_verified})

    def _country_prefix(num: str) -> str:
        if not num or not num.startswith("+"):
            return ""
        # crude country prefix detection for common cases
        if num.startswith("+91"):
            return "+91"
        if num.startswith("+1"):
            return "+1"
        return num[:3]

    # prefer a verified callerId that matches the first candidate's country
    if available_verified:
        cand_pref = _country_prefix(candidates[0])
        match = next((v for v in available_verified if _country_prefix(v) == cand_pref), None)
        candidate_choice = match or available_verified[0]
        # If the chosen candidate_choice accidentally equals a destination
        # (shouldn't after filtering above), guard and fall back to None.
        if candidate_choice in candidates:
            caller_id = None
            log_event(call_sid, "CALLER_ID_CHOSEN", {"caller_id": None, "reason": "chosen_verified_matches_candidate; falling_back"})
        else:
            caller_id = candidate_choice
            log_event(call_sid, "CALLER_ID_CHOSEN", {"caller_id": caller_id, "reason": "matched_by_country_or_first_available"})
    else:
        log_event(call_sid, "CALLER_ID_CHOSEN", {"caller_id": None, "reason": "no_available_verified_numbers_after_filtering"})

    dial = Dial(timeout=20, callerId=caller_id) if caller_id else Dial(timeout=20)
    for num in candidates:
        dial.number(num)

    log_event(call_sid, "DIAL_ATTEMPT", {"candidates": candidates, "timeout": 20, "caller_id": caller_id})

    response.append(dial)


def _copy(mapping: dict[str, str], language_code: str) -> str:
    return mapping.get(language_code, mapping["en-IN"])


def _resolve_category(digits: str | None, speech: str | None) -> str | None:
    # If caller pressed a key, prefer it
    if digits and digits in CATEGORY_BY_DIGIT:
        return CATEGORY_BY_DIGIT[digits]

    transcript = _normalize_transcript(speech)

    # Check for spoken number tokens
    tokens = transcript.split()
    for token in tokens:
        for digit, aliases in SPOKEN_NUMBER_ALIASES.items():
            if token in aliases:
                return CATEGORY_BY_DIGIT.get(digit)

    # Look for phrases like "option one" or "number 3"
    for digit, aliases in SPOKEN_NUMBER_ALIASES.items():
        for alias in aliases:
            if alias and alias in transcript:
                return CATEGORY_BY_DIGIT.get(digit)

    # Fallback: look for category keywords in the transcript
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in transcript for keyword in keywords):
            return category
    return None


def _normalize_transcript(text: str | None) -> str:
    if not text:
        return ""
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _confirmation_prompt(category: str, language_code: str) -> str:
    template = config_service.get_ivr_prompt("confirmation")
    label = CATEGORY_LABELS.get(category, category)
    return template.replace("{{category}}", label)

"""Provider-agnostic IVR Dialog Engine.

Coordinates caller state transitions, STT intent resolution, profanity moderation,
lead recording, Cloud Run CRM synchronization, and agent routing.
"""

from typing import Any, Dict, Optional
import re
from fastapi import Request, Response

from app.core.config import get_settings
from app.core.logger import log_event, logger
from app.providers.base import BaseTelephonyProvider
from app.services import config_service, gemini_service
from app.services.crm_service import create_lead_in_crm
from app.services.agent_service import get_agent_candidates
from app.services.order_service import get_order_status_for_phone
from app.services.lead_service import (
    get_lead_by_call_sid,
    record_category_selection,
    record_intent,
    record_assist_type,
    record_product_id,
    record_description,
    record_caller_name,
    get_caller_name,
    get_caller_intent,
    get_caller_description,
)

settings = get_settings()

ALLOWED_CATEGORIES = (
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


class DialogEngine:
    """Orchestrates IVR dialog flows for any BaseTelephonyProvider."""

    def __init__(self, provider: BaseTelephonyProvider, base_route_prefix: str = "/api/plivo"):
        self.provider = provider
        self.prefix = base_route_prefix.rstrip("/")

    def _url(self, request: Request, path: str) -> str:
        """Helper to format action URL using provider rules."""
        full_path = f"{self.prefix}{path}" if path.startswith("/") else f"{self.prefix}/{path}"
        return self.provider.format_action_url(request, full_path)

    def _get_prompt(self, key: str) -> str:
        """Fetch IVR prompt with fallback and optional AI rewrite."""
        text = config_service.get_ivr_prompt(key)
        try:
            return gemini_service.filter_text_if_enabled(text)
        except Exception:
            return text

    def _normalize_transcript(self, text: Optional[str]) -> str:
        if not text:
            return ""
        lowered = text.lower()
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    def resolve_intent(self, speech: Optional[str]) -> Optional[str]:
        """Resolve initial intent from speech or DTMF digits."""
        transcript = self._normalize_transcript(speech)
        if not transcript:
            return None

        # DTMF digits / spoken numbers
        if transcript in ("1", "one"):
            return "try_near_you"
        if transcript in ("2", "two"):
            return "price_request"
        if transcript in ("3", "three"):
            return "general_inquiry"
        if transcript in ("4", "four"):
            return "order_status"

        # Try Near You keywords
        if any(k in transcript for k in ("try near you", "near you", "try near", "store", "location", "visit", "showroom", "outlet")):
            return "try_near_you"
        # Price request keywords
        if any(k in transcript for k in ("price", "pricing", "cost", "rate", "rates", "price request", "request price", "quote")):
            return "price_request"
        # General inquiry keywords
        if any(k in transcript for k in ("general", "inquiry", "enquiry", "help", "assist", "assistance", "question", "info")):
            return "general_inquiry"
        # Order status keywords
        if any(k in transcript for k in ("order", "order status", "track", "tracking", "where is my order", "status")):
            return "order_status"

        return None

    def resolve_assist_type(self, speech: Optional[str]) -> Optional[str]:
        """Resolve whether caller wants 'product' or 'category'."""
        transcript = self._normalize_transcript(speech)
        if not transcript:
            return None

        if transcript in ("1", "one") or any(k in transcript for k in ("specific", "product", "item", "piece", "particular")):
            return "product"
        if transcript in ("2", "two") or any(k in transcript for k in ("category", "categories", "collection", "type", "general", "range")):
            return "category"
        return None

    def resolve_category(self, speech: Optional[str]) -> Optional[str]:
        """Resolve spoken category with misheard word replacement."""
        transcript = self._normalize_transcript(speech)
        if not transcript:
            return None

        transcript = self._normalize_transcript(config_service.correct_misheard_words(transcript))

        variants: Dict[str, str] = {
            "curated combination": "curated combination",
            "curated combinations": "curated combination",
            "curated combo": "curated combination",
            "men jewellery": "men jewellery",
            "mens jewellery": "men jewellery",
            "men jewelry": "men jewellery",
            "mens jewelry": "men jewellery",
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

        for variant in sorted(variants.keys(), key=len, reverse=True):
            if variant in transcript:
                return variants[variant]
        return None

    def infer_category_from_product_name(self, call_sid: Optional[str], product_name: str) -> None:
        """Attempt to deduce category from product title."""
        if not call_sid or not product_name:
            return
        cat = self.resolve_category(product_name)
        if cat:
            record_category_selection(call_sid, cat)

    # ==================== DIALOG FLOW HANDLERS ====================

    def handle_incoming_call(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Greeting + main menu."""
        call_sid = metadata.get("call_sid")
        from_number = metadata.get("from_number")

        log_event(call_sid, f"{self.provider.name.upper()}_CALL_RECEIVED", {
            "from": from_number,
            "call_sid": call_sid,
            "provider": self.provider.name,
        })

        greeting = config_service.get_voice_greeting("en-IN")
        menu_text = self._get_prompt("menu")
        prompt_text = f"{greeting} {menu_text}".strip()
        log_event(call_sid, "IVR_SAY", {"prompt": "menu", "message": prompt_text})

        action_url = self._url(request, "/voice/intent")
        hints = "general inquiry, try near you, price request, order status, general, store, price, order, 1, 2, 3, 4"
        doc = self.provider.build_speech_prompt(
            prompt_text=prompt_text,
            action_url=action_url,
            hints=hints,
            timeout=5,
            redirect_fallback_url=self._url(request, "/voice"),
        )
        return self.provider.render_response(doc)

    def handle_intent(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Evaluate intent speech result."""
        call_sid = metadata.get("call_sid")
        speech = metadata.get("speech_result")

        log_event(call_sid, "INTENT_SPEECH_RECEIVED", {"speech": speech, "provider": self.provider.name})
        intent = self.resolve_intent(speech)

        if not intent:
            log_event(call_sid, "INTENT_NOT_RECOGNIZED", {"speech": speech})
            if call_sid:
                record_intent(call_sid, "unknown")

            invalid_text = self._get_prompt("invalid")
            menu_text = self._get_prompt("menu")
            combined = f"{invalid_text} {menu_text}".strip()
            log_event(call_sid, "IVR_SAY", {"prompt": "invalid", "message": combined})

            doc = self.provider.build_speech_prompt(
                prompt_text=combined,
                action_url=self._url(request, "/voice/intent"),
                hints="general inquiry, try near you, price request, order status, general, store, price, order, 1, 2, 3, 4",
                timeout=5,
                redirect_fallback_url=self._url(request, "/voice"),
            )
            return self.provider.render_response(doc)

        if call_sid:
            record_intent(call_sid, intent)
        log_event(call_sid, "INTENT_SELECTED", {"intent": intent, "speech": speech})

        # Prompt for name
        name_prompt = self._get_prompt("name_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "name_prompt", "message": name_prompt})

        doc = self.provider.build_speech_prompt(
            prompt_text=name_prompt,
            action_url=self._url(request, "/voice/name"),
            timeout=5,
            redirect_fallback_url=self._url(request, "/voice/name-fallback"),
        )
        return self.provider.render_response(doc)

    def handle_name(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Validate caller name and proceed."""
        call_sid = metadata.get("call_sid")
        caller_name = (metadata.get("speech_result") or "").strip()

        if caller_name:
            try:
                profane = gemini_service.is_profane(caller_name)
            except Exception:
                profane = False

            if profane:
                log_event(call_sid, "CALLER_NAME_PROFANITY_REJECTED", {"name": caller_name})
                bad_name_text = self._get_prompt("name_profanity_failed_prompt")
                log_event(call_sid, "IVR_SAY", {"prompt": "name_profanity_failed_prompt", "message": bad_name_text})

                doc = self.provider.build_speech_prompt(
                    prompt_text=bad_name_text,
                    action_url=self._url(request, "/voice/name"),
                    timeout=5,
                    redirect_fallback_url=self._url(request, "/voice/name-fallback"),
                )
                return self.provider.render_response(doc)

            if call_sid:
                record_caller_name(call_sid, caller_name)
            log_event(call_sid, "CALLER_NAME_CAPTURED", {"name": caller_name})
        else:
            log_event(call_sid, "CALLER_NAME_NOT_PROVIDED", {})

        return self.continue_after_name(request, metadata)

    def continue_after_name(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Route to appropriate next step based on intent."""
        call_sid = metadata.get("call_sid")
        from_number = metadata.get("from_number")

        lead = get_lead_by_call_sid(call_sid) if call_sid else None
        intent = lead.extra_metadata.get("intent") if lead and lead.extra_metadata else None

        # Price Request
        if intent == "price_request":
            prompt = self._get_prompt("price_request_prompt")
            log_event(call_sid, "IVR_SAY", {"prompt": "price_request_prompt", "message": prompt})
            doc = self.provider.build_speech_prompt(
                prompt_text=prompt,
                action_url=self._url(request, "/voice/price-product"),
                timeout=5,
                redirect_fallback_url=self._url(request, "/voice/dial-agent"),
            )
            return self.provider.render_response(doc)

        # Order Status
        if intent == "order_status":
            prompt = self._get_prompt("order_status_prompt")
            log_event(call_sid, "IVR_SAY", {"prompt": "order_status_prompt", "message": prompt})
            doc = self.provider.build_speech_prompt(
                prompt_text=prompt,
                action_url=self._url(request, "/voice/order-status-id"),
                hints="order, tracking, status, number",
                timeout=5,
                redirect_fallback_url=self._url(request, "/voice/dial-agent"),
            )
            return self.provider.render_response(doc)

        # General Inquiry / Store -> Ask Product vs Category
        prompt = self._get_prompt("assist_type_prompt")
        log_event(call_sid, "IVR_SAY", {"prompt": "assist_type_prompt", "message": prompt})
        doc = self.provider.build_speech_prompt(
            prompt_text=prompt,
            action_url=self._url(request, "/voice/assist-type"),
            hints="product, category, specific product, product category, item, type, 1, 2",
            timeout=5,
            redirect_fallback_url=self._url(request, "/voice/name-fallback"),
        )
        return self.provider.render_response(doc)

    def handle_assist_type(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Branch between product ID collection and category collection."""
        call_sid = metadata.get("call_sid")
        speech = metadata.get("speech_result")

        choice = self.resolve_assist_type(speech)
        if not choice:
            invalid_text = self._get_prompt("invalid")
            assist_text = self._get_prompt("assist_type_prompt")
            combined = f"{invalid_text} {assist_text}".strip()

            doc = self.provider.build_speech_prompt(
                prompt_text=combined,
                action_url=self._url(request, "/voice/assist-type"),
                hints="product, category, specific product, product category, item, type, 1, 2",
                timeout=5,
                redirect_fallback_url=self._url(request, "/voice/name-fallback"),
            )
            return self.provider.render_response(doc)

        if call_sid:
            record_assist_type(call_sid, choice)
        log_event(call_sid, "ASSIST_TYPE_SELECTED", {"assist_type": choice})

        if choice == "product":
            prompt = self._get_prompt("product_id_prompt")
            action = self._url(request, "/voice/product-id")
            hints = None
        else:
            prompt = self._get_prompt("category_menu_prompt")
            action = self._url(request, "/voice/product-category")
            hints = "necklace, necklaces, bangles, bracelets, earrings, rings, accessories, curated combination, men jewellery, vintage diamonds"

        doc = self.provider.build_speech_prompt(
            prompt_text=prompt,
            action_url=action,
            hints=hints,
            timeout=5,
            redirect_fallback_url=self._url(request, "/voice/dial-agent"),
        )
        return self.provider.render_response(doc)

    def handle_product_id(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Capture product name and transfer to agent."""
        call_sid = metadata.get("call_sid")
        speech = (metadata.get("speech_result") or "").strip()

        if call_sid and speech:
            record_product_id(call_sid, speech)
            self.infer_category_from_product_name(call_sid, speech)

        log_event(call_sid, "PRODUCT_ID_CAPTURED", {"product_id": speech})
        return self.connect_to_agent(request, metadata)

    def handle_category(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Capture category and prompt for description."""
        call_sid = metadata.get("call_sid")
        speech = metadata.get("speech_result")

        category = self.resolve_category(speech) or "accessories"
        if call_sid:
            record_category_selection(call_sid, category)
        log_event(call_sid, "CATEGORY_RESOLVED", {"category": category, "speech": speech})

        prompt = self._get_prompt("description_prompt")
        doc = self.provider.build_speech_prompt(
            prompt_text=prompt,
            action_url=self._url(request, "/voice/description"),
            timeout=5,
            redirect_fallback_url=self._url(request, "/voice/dial-agent"),
        )
        return self.provider.render_response(doc)

    def handle_description(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Capture description and connect to agent."""
        call_sid = metadata.get("call_sid")
        speech = (metadata.get("speech_result") or "").strip()

        if call_sid and speech:
            record_description(call_sid, speech)
        log_event(call_sid, "DESCRIPTION_CAPTURED", {"description": speech})

        return self.connect_to_agent(request, metadata)

    def handle_order_status_id(self, request: Request, metadata: Dict[str, Any]) -> Response:
        """Check order status and announce."""
        call_sid = metadata.get("call_sid")
        from_number = metadata.get("from_number")

        status = get_order_status_for_phone(from_number, call_sid)
        if status == "shipped":
            msg = self._get_prompt("order_status_shipped")
        elif status == "no_orders":
            msg = self._get_prompt("order_status_no_orders")
            doc = self.provider.build_hangup(message=msg)
            return self.provider.render_response(doc)
        else:
            msg = self._get_prompt("order_status_not_ready")

        return self.connect_to_agent(request, metadata, announce_message=msg)

    def connect_to_agent(
        self,
        request: Request,
        metadata: Dict[str, Any],
        announce_message: Optional[str] = None,
    ) -> Response:
        """Push lead to Cloud Run CRM microservice and bridge call to available human agent."""
        call_sid = metadata.get("call_sid")
        from_number = metadata.get("from_number")

        lead = get_lead_by_call_sid(call_sid) if call_sid else None
        category = getattr(lead, "selected_category", None) if lead else None
        product_id = getattr(lead, "product_id", None) if lead else None

        caller_name = get_caller_name(call_sid) if call_sid else None
        intent = get_caller_intent(call_sid) if call_sid else None
        caller_desc = get_caller_description(call_sid) if call_sid else None

        # 1. Delegate lead sync to Cloud Run microservice
        currency = "INR" if self.provider.name == "plivo" else "USD"
        if call_sid:
            try:
                crm_lead_id = create_lead_in_crm(
                    call_sid=call_sid,
                    caller_name=caller_name,
                    mobile_phone=from_number,
                    intent=intent,
                    product_id=product_id,
                    category=category,
                    description=caller_desc,
                    currency=currency,
                )
                if crm_lead_id:
                    log_event(call_sid, "CRM_LEAD_SYNCED", {"lead_id": crm_lead_id, "provider": self.provider.name})
            except Exception as exc:
                log_event(call_sid, "CRM_LEAD_ERROR", {"error": str(exc), "provider": self.provider.name})

        # 2. Candidate agents
        candidates = get_agent_candidates(category, currency=currency, limit=5)

        log_event(call_sid, "ROUTING_CANDIDATES", {
            "category": category,
            "currency": currency,
            "candidates": candidates,
            "provider": self.provider.name,
        })

        if not candidates:
            no_agent_text = self._get_prompt("no_agent")
            doc = self.provider.build_hangup(message=no_agent_text)
            return self.provider.render_response(doc)

        connecting_text = self._get_prompt("connecting")
        if announce_message:
            connecting_text = f"{announce_message} {connecting_text}".strip()

        # Caller ID
        if self.provider.name == "plivo":
            caller_id = getattr(settings, "PLIVO_PHONE_NUMBER", None)
        else:
            caller_id = getattr(settings, "TWILIO_CALLER_ID", None)

        timeout = getattr(settings, "AGENT_DIAL_TIMEOUT", 120)
        action_url = self._url(request, "/voice/dial-complete")

        doc = self.provider.build_dial(
            numbers=candidates,
            caller_id=caller_id,
            action_url=action_url,
            timeout=timeout,
            announce_message=connecting_text,
        )
        return self.provider.render_response(doc)

    def handle_dial_complete(
        self,
        request: Request,
        metadata: Dict[str, Any],
        raw_form: Dict[str, Any],
    ) -> Response:
        """Handle completion of outbound agent dial.

        If dial was answered and completed:
            Gracefully hang up the call.
        If customer service does not answer within the 2-minute wait (or is busy/failed):
            Speak user-specified fallback message and hang up gracefully, preventing error 4010.
        """
        call_sid = metadata.get("call_sid") or raw_form.get("CallUUID") or raw_form.get("DialALegUUID")
        dial_status = (raw_form.get("DialStatus") or raw_form.get("dial_status") or "").lower()
        hangup_cause = raw_form.get("DialHangupCause") or raw_form.get("HangupCause") or ""
        bleg_uuid = raw_form.get("DialBLegUUID") or ""

        log_event(call_sid, f"{self.provider.name.upper()}_DIAL_COMPLETED", {
            "dial_status": dial_status,
            "hangup_cause": hangup_cause,
            "bleg_uuid": bleg_uuid,
            "provider": self.provider.name,
        })

        if dial_status == "completed":
            doc = self.provider.build_hangup()
            return self.provider.render_response(doc)

        fallback_msg = "We will revert back to you in a short time. Thank you for the call."
        log_event(call_sid, "IVR_SAY", {"prompt": "agent_unanswered_fallback", "message": fallback_msg})
        doc = self.provider.build_hangup(message=fallback_msg)
        return self.provider.render_response(doc)

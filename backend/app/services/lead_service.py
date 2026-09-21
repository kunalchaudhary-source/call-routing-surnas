"""Utilities for capturing and tracking lead metadata during calls."""

from typing import Any, Dict, Optional

from app.core.database import SessionLocal
from app.models.db_models import Call, CallLead

LANGUAGE_BY_CURRENCY = {
    "INR": "hi-IN",
    "USD": "en-IN",
    "EUR": "en-IN",
    "AED": "en-IN",
}
DEFAULT_LANGUAGE = "en-IN"


def _language_for_currency(currency: Optional[str]) -> str:
    if not currency:
        return DEFAULT_LANGUAGE
    return LANGUAGE_BY_CURRENCY.get(currency.upper(), DEFAULT_LANGUAGE)


def upsert_call_lead(payload: Dict[str, Any]) -> CallLead:
    """Create or update a CallLead row with website or API provided context."""
    call_sid = payload["call_sid"]
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        if not lead.call_id:
            call = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
            if call:
                lead.call_id = call.id

        lead.page_context = payload.get("page_context", lead.page_context or "home")
        if payload.get("currency"):
            lead.currency = payload["currency"].upper()
        lead.user_type = payload.get("user_type", lead.user_type)
        lead.customer_id = payload.get("customer_id", lead.customer_id)
        lead.product_id = payload.get("product_id", lead.product_id)

        # Protect reserved IVR keys during website context updates
        if "metadata" in payload and payload.get("metadata") is not None:
            incoming_meta = payload.get("metadata") or {}
            existing_meta = lead.extra_metadata or {}
            reserved_keys = {"intent", "caller_name", "assist_type", "caller_description"}
            merged = dict(existing_meta)
            for key, value in incoming_meta.items():
                if key in reserved_keys and merged.get(key) is not None:
                    continue
                merged[key] = value
            lead.extra_metadata = merged

        incoming_category = payload.get("product_category")
        if incoming_category:
            lead.selected_category = incoming_category.lower()

        if payload.get("preferred_language"):
            lead.preferred_language = payload["preferred_language"]
        elif lead.currency:
            lead.preferred_language = _language_for_currency(lead.currency)
        elif not lead.preferred_language:
            lead.preferred_language = DEFAULT_LANGUAGE

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def get_lead_by_call_sid(call_sid: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        return db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
    finally:
        db.close()


def record_category_selection(call_sid: str, category: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            return None
        lead.selected_category = category.lower()
        if not lead.preferred_language and lead.currency:
            lead.preferred_language = _language_for_currency(lead.currency)
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_intent(call_sid: str, intent: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = dict(lead.extra_metadata or {})
        extra["intent"] = intent
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_assist_type(call_sid: str, assist_type: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = dict(lead.extra_metadata or {})
        extra["assist_type"] = assist_type
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_product_id(call_sid: str, product_id: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        lead.product_id = product_id
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_description(call_sid: str, description: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = dict(lead.extra_metadata or {})
        extra["caller_description"] = description
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_caller_name(call_sid: str, caller_name: str) -> Optional[CallLead]:
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = dict(lead.extra_metadata or {})
        extra["caller_name"] = caller_name
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def get_caller_name(call_sid: str) -> Optional[str]:
    lead = get_lead_by_call_sid(call_sid)
    if lead and lead.extra_metadata:
        return lead.extra_metadata.get("caller_name")
    return None


def get_caller_intent(call_sid: str) -> Optional[str]:
    lead = get_lead_by_call_sid(call_sid)
    if lead and lead.extra_metadata:
        return lead.extra_metadata.get("intent")
    return None


def get_caller_description(call_sid: str) -> Optional[str]:
    lead = get_lead_by_call_sid(call_sid)
    if lead and lead.extra_metadata:
        return lead.extra_metadata.get("caller_description")
    return None


def link_lead_to_call(call_sid: str, call_id: Optional[str]) -> None:
    if not call_id:
        return
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead or lead.call_id:
            return
        lead.call_id = call_id
        db.add(lead)
        db.commit()
    finally:
        db.close()


def derive_language_from_lead(lead: Optional[CallLead], fallback_currency: Optional[str] = None) -> str:
    if lead and lead.preferred_language:
        return lead.preferred_language
    currency = None
    if lead and lead.currency:
        currency = lead.currency
    elif fallback_currency:
        currency = fallback_currency
    return _language_for_currency(currency)

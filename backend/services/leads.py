"""Utilities for capturing website context (lead/CRM metadata) per call."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.db import SessionLocal
from backend.models.db_models import Call, CallLead

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
    """Create or update a CallLead row with website-provided context."""
    call_sid = payload["call_sid"]
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        # Attach Call FK if record already exists
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
        lead.extra_metadata = payload.get("metadata", lead.extra_metadata)

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
    """Record the caller's top-level intent (general_inquiry / store / price_request)."""
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = lead.extra_metadata or {}
        extra["intent"] = intent
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_assist_type(call_sid: str, assist_type: str) -> Optional[CallLead]:
    """Record whether the caller wants help with a specific product or a category.

    `assist_type` should be either 'product' or 'category'.
    """
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = lead.extra_metadata or {}
        extra["assist_type"] = assist_type
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_product_id(call_sid: str, product_id: str) -> Optional[CallLead]:
    """Store the provided Product ID on the call lead."""
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
    """Store a short free-text description the caller gave before handoff."""
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = lead.extra_metadata or {}
        extra["caller_description"] = description
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def record_caller_name(call_sid: str, caller_name: str) -> Optional[CallLead]:
    """Store the caller's name (from IVR question)."""
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        extra = lead.extra_metadata or {}
        extra["caller_name"] = caller_name
        lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def get_caller_name(call_sid: str) -> Optional[str]:
    """Retrieve the caller's name from the lead."""
    lead = get_lead_by_call_sid(call_sid)
    if lead and lead.extra_metadata:
        return lead.extra_metadata.get("caller_name")
    return None


def get_caller_intent(call_sid: str) -> Optional[str]:
    """Retrieve the caller's intent from the lead."""
    lead = get_lead_by_call_sid(call_sid)
    if lead and lead.extra_metadata:
        return lead.extra_metadata.get("intent")
    return None


def get_caller_description(call_sid: str) -> Optional[str]:
    """Retrieve the caller's description from the lead."""
    lead = get_lead_by_call_sid(call_sid)
    if lead and lead.extra_metadata:
        return lead.extra_metadata.get("caller_description")
    return None


def record_full_interaction(call_sid: str, *, intent: str | None = None, assist_type: str | None = None, product_id: str | None = None, product_category: str | None = None, description: str | None = None) -> Optional[CallLead]:
    """Convenience helper to record multiple values at once on the CallLead.

    Only non-None values are written.
    """
    db = SessionLocal()
    try:
        lead = db.query(CallLead).filter_by(call_sid=call_sid).one_or_none()
        if not lead:
            lead = CallLead(call_sid=call_sid)

        if intent is not None:
            extra = lead.extra_metadata or {}
            extra["intent"] = intent
            lead.extra_metadata = extra

        if assist_type is not None:
            extra = lead.extra_metadata or {}
            extra["assist_type"] = assist_type
            lead.extra_metadata = extra

        if product_id is not None:
            lead.product_id = product_id

        if product_category is not None:
            lead.selected_category = product_category.lower()

        if description is not None:
            extra = lead.extra_metadata or {}
            extra["caller_description"] = description
            lead.extra_metadata = extra

        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


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

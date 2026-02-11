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

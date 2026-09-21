"""Salesforce CRM integration via Surana Cloud Run Microservice.

Converts caller data from IVR flow into Salesforce Lead records
by delegating to the Cloud Run lead service.
"""

import re
from typing import Optional, Tuple
import requests

from app.core.config import get_settings
from app.core.logger import log_event


def format_crm_phone_and_currency(
    phone: Optional[str],
    default_currency: str = "INR",
) -> Tuple[str, str]:
    """Normalize caller phone number to E.164 (+prefix) and deduce regional currency.
    
    Handles:
      - Indian numbers (starting with 91, +91, or 10-digit mobile) -> +91XXXXXXXXXX, Currency: INR
      - North American numbers (starting with 1, +1, or 11 digits) -> +1XXXXXXXXXX, Currency: USD
      - Venezuela (+58) & other international (e.g. +44, +971) -> +<number>, Currency: USD
    """
    if not phone:
        return ("+910000000000", default_currency)

    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    has_plus = raw.startswith("+")

    if not digits:
        return ("+910000000000", default_currency)

    # 1. Indian Numbers (+91 or 91 with 11-13 digits, or 10-digit Indian mobile)
    if digits.startswith("91") and len(digits) >= 11:
        return (f"+{digits}", "INR")
    if len(digits) == 10 and default_currency == "INR":
        return (f"+91{digits}", "INR")
    if has_plus and raw.startswith("+91"):
        return (f"+{digits}", "INR")

    # 2. USA / Canada (+1 or 1 with 11 digits, or 10 digits when default_currency is USD)
    if digits.startswith("1") and len(digits) == 11:
        return (f"+{digits}", "USD")
    if has_plus and raw.startswith("+1"):
        return (f"+{digits}", "USD")

    # 3. International (e.g., 58 for Venezuela, 2 for Egypt/South Africa/Nigeria, 44 for UK, 971, etc.)
    # All non-India international customers are quoted in USD for global jewelry exports
    if digits.startswith("58"):
        return (f"+{digits}", "USD")

    if digits.startswith("2") and len(digits) >= 10:
        return (f"+{digits}", "USD")

    if has_plus:
        return (f"+{digits}", "USD" if not raw.startswith("+91") else "INR")

    if len(digits) > 10:
        return (f"+{digits}", "USD")

    prefix = "+91" if default_currency == "INR" else "+1"
    return (f"{prefix}{digits}", default_currency)


def is_crm_configured() -> bool:
    """Check if Cloud Run CRM service is configured."""
    settings = get_settings()
    return bool(settings.SURANA_CRM_URL and (settings.SURANA_WORKER_SECRET or settings.SURANA_INGEST_SECRET))


def create_lead_in_crm(
    call_sid: str,
    caller_name: Optional[str],
    mobile_phone: Optional[str],
    intent: Optional[str],
    product_id: Optional[str],
    category: Optional[str],
    description: Optional[str],
    currency: Optional[str] = None,
) -> Optional[str]:
    """Create a Lead record in Salesforce CRM via Cloud Run microservice.
    
    Args:
        call_sid: Call SID / CallUUID for logging
        caller_name: Full name of the caller (from IVR)
        mobile_phone: Caller's phone number
        intent: User's selected option (try_near_you, price_request, general_inquiry, etc.)
        product_id: Product ID / name if provided
        category: Category name if provided
        description: Brief query description from caller
        currency: Explicit currency code (INR / USD), or auto-detected from caller phone
        
    Returns:
        Salesforce Lead ID if created successfully, None otherwise.
    """
    settings = get_settings()
    if not is_crm_configured():
        log_event(call_sid, "CRM_LEAD_SKIPPED", {"reason": "Cloud Run CRM service not configured"})
        return None

    name = (caller_name or "Voice Caller").strip()

    # Format phone number to E.164 with '+' sign and determine currency
    clean_mobile, detected_curr = format_crm_phone_and_currency(mobile_phone, default_currency=currency or "INR")
    final_currency = currency or detected_curr

    # Check for Hot Lead and normalize intent label
    is_hot_lead = False
    intent_label = intent
    if intent in ("store", "try_near_you", "try near you"):
        intent_label = "Try Near You"
        is_hot_lead = True
    elif intent == "price_request":
        intent_label = "Price Request"
    elif intent == "general_inquiry":
        intent_label = "General Inquiry"
    elif intent == "order_status":
        intent_label = "Order Status"

    # Compose structured request / notes
    pieces = []
    if is_hot_lead:
        pieces.append("🔥 [HOT LEAD - STORE VISIT]")
    if category:
        pieces.append(f"Category: {category}")
    if product_id:
        pieces.append(f"Product: {product_id}")
    if intent_label:
        pieces.append(f"Intent: {intent_label}")
    if final_currency:
        pieces.append(f"Currency: {final_currency}")
    if description:
        pieces.append(f"Description: {description}")
    pieces.append("Source: Inbound Call")

    request_text = " | ".join(pieces) if pieces else "General Voice Bot Enquiry"

    payload = {
        "name": name,
        "mobile": clean_mobile,
        "email": None,
        "request": request_text,
    }

    # 1. Synchronous direct creation via worker secret (returns real Salesforce lead_id)
    if settings.SURANA_WORKER_SECRET:
        try:
            headers = {
                "Content-Type": "application/json",
                "x-surana-worker-key": settings.SURANA_WORKER_SECRET,
            }
            log_event(call_sid, "CLOUD_RUN_CRM_CREATING", {"method": "worker_direct", "payload": payload})
            resp = requests.post(settings.SURANA_CRM_URL, json=payload, headers=headers, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                lead_id = data.get("lead_id")
                log_event(call_sid, "CRM_LEAD_CREATED", {"lead_id": lead_id, "provider": "cloud_run_worker", "success": True})
                return lead_id
            else:
                log_event(call_sid, "CLOUD_RUN_WORKER_ERROR", {"status": resp.status_code, "body": resp.text[:300]})
        except Exception as exc:
            log_event(call_sid, "CLOUD_RUN_WORKER_EXCEPTION", {"error": str(exc)})

    # 2. Asynchronous task queue via ingest secret (fallback)
    if settings.SURANA_INGEST_SECRET:
        try:
            headers = {
                "Content-Type": "application/json",
                "x-surana-api-key": settings.SURANA_INGEST_SECRET,
            }
            log_event(call_sid, "CLOUD_RUN_CRM_ENQUEUEING", {"method": "tasks_ingest", "payload": payload})
            resp = requests.post(settings.SURANA_CRM_URL, json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 202):
                data = resp.json()
                task_id = data.get("request_id")
                log_event(call_sid, "CRM_LEAD_ENQUEUED", {"request_id": task_id, "provider": "cloud_run_tasks"})
                return task_id
            else:
                log_event(call_sid, "CLOUD_RUN_INGEST_ERROR", {"status": resp.status_code, "body": resp.text[:300]})
        except Exception as exc:
            log_event(call_sid, "CLOUD_RUN_INGEST_EXCEPTION", {"error": str(exc)})

    return None

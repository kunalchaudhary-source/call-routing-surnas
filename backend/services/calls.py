"""Helpers for creating and updating Call records from Twilio data."""

from datetime import datetime
from typing import Mapping, Optional

from backend.db import SessionLocal
from backend.models.db_models import Call


def ensure_call_from_twilio(form: Mapping[str, str]) -> Optional[Call]:
    """Ensure a Call row exists for this Twilio webhook.

    Uses Twilio form fields like CallSid, From, To, CallerCountry, etc.
    Returns the Call instance or None if CallSid is missing.
    """
    call_sid = form.get("CallSid")
    if not call_sid:
        return None

    db = SessionLocal()
    try:
        call = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
        if call:
            return call

        call = Call(
            twilio_call_sid=call_sid,
            from_number=form.get("From"),
            to_number=form.get("To"),
            caller_country=form.get("CallerCountry"),
            caller_state=form.get("CallerState"),
            caller_city=form.get("CallerCity"),
            call_start=datetime.utcnow(),
            call_status=form.get("CallStatus"),
        )
        db.add(call)
        db.commit()
        db.refresh(call)
        return call
    finally:
        db.close()

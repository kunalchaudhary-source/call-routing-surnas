"""Helpers for creating and updating Call records from Twilio/Plivo webhooks."""

from datetime import datetime
from typing import Any, Mapping, Optional

from app.core.database import SessionLocal
from app.models.db_models import Call


def ensure_call_from_twilio(form: Mapping[str, Any]) -> Optional[Call]:
    """Ensure a Call row exists for this Twilio webhook."""
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
            caller_country=form.get("CallerCountry") or "US",
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


def ensure_call_from_plivo(form: Mapping[str, Any]) -> Optional[Call]:
    """Ensure a Call row exists for this Plivo webhook."""
    call_uuid = (
        form.get("CallUUID")
        or form.get("call_uuid")
        or form.get("CallSid")
        or form.get("call_sid")
    )
    if not call_uuid:
        return None

    db = SessionLocal()
    try:
        call = db.query(Call).filter_by(twilio_call_sid=call_uuid).one_or_none()
        if call:
            return call

        call = Call(
            twilio_call_sid=call_uuid,
            from_number=form.get("From") or form.get("from"),
            to_number=form.get("To") or form.get("to"),
            caller_country=form.get("CallerCountry") or "IN",
            caller_state=form.get("CallerState"),
            caller_city=form.get("CallerCity"),
            call_start=datetime.utcnow(),
            call_status=form.get("CallStatus", "in-progress"),
        )
        db.add(call)
        db.commit()
        db.refresh(call)
        return call
    finally:
        db.close()

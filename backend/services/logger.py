from datetime import datetime
from typing import Any, Dict

from backend.db import SessionLocal
from backend.models.db_models import Call, CallEvent


def log_event(call_sid: str | None, event_type: str, payload: Dict[str, Any]) -> None:
    """Persist a structured event for this call and print to stdout.

    - No audio is logged or stored.
    - All metadata goes into call_events.event_payload (JSONB) plus console.
    """
    timestamp = datetime.utcnow().isoformat()

    # Console log (for quick debugging / Cloud logs)
    print({
        "call_sid": call_sid,
        "event": event_type,
        "payload": payload,
        "timestamp": timestamp,
    })

    # DB log (Postgres) — link to Call row if it exists
    db = SessionLocal()
    try:
        call = None
        if call_sid:
            call = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()

        event = CallEvent(
            call_id=call.id if call else None,
            event_type=event_type,
            event_payload={
                **payload,
                "timestamp": timestamp,
            },
        )
        db.add(event)
        db.commit()
    finally:
        db.close()


def log_system_failure(call_sid: str | None, source: str, error: str) -> None:
    """Record a system failure related to a call for incident analysis."""
    log_event(call_sid, "SYSTEM_FAILURE", {"source": source, "error": error})

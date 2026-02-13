from datetime import datetime
from typing import Any, Dict
import logging

from backend.db import SessionLocal
from backend.models.db_models import Call, CallEvent

# Configure module logger; uvicorn will capture these logs.
logger = logging.getLogger("call_routing")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_event(call_sid: str | None, event_type: str, payload: Dict[str, Any]) -> None:
    """Persist a structured event for this call and log to stdout/logger.

    Uses both print() (quick debug) and the Python logging module so messages
    appear in uvicorn-managed logs and any log collectors.
    """
    timestamp = datetime.utcnow().isoformat()
    now = datetime.utcnow()

    # Prepare a record for console/log output (without DB timestamp)
    record = {
        "call_sid": call_sid,
        "event": event_type,
        "payload": payload,
        "timestamp": timestamp,
    }

    # DB log (Postgres) — avoid near-duplicate events caused by reloaders/processes
    db = SessionLocal()
    try:
        call = None
        if call_sid:
            call = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()

        # Deduplicate: if an event with same type and payload was created in last 5s, skip it
        try:
            from datetime import timedelta

            cutoff = now - timedelta(seconds=5)
            q = db.query(CallEvent).filter(CallEvent.event_type == event_type, CallEvent.created_at >= cutoff)
            if call:
                q = q.filter(CallEvent.call_id == call.id)
            if payload:
                # JSONB contains operator: matches if stored JSON contains the given payload keys/values
                q = q.filter(CallEvent.event_payload.contains(payload))
            dup = q.first()
            if dup:
                return
        except Exception:
            # If dedupe query fails for any reason, continue and log normally
            pass

        # Emit via logging so uvicorn captures it consistently
        try:
            logger.info(record)
        except Exception:
            pass

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

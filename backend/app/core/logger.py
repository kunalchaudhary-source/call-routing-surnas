"""Structured event logging to stdout, python logger, and PostgreSQL database."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

from app.core.database import SessionLocal

logger = logging.getLogger("call_routing")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_event(call_sid: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
    """Persist structured event for this call and log to stdout / python logging."""
    from app.models.db_models import Call, CallEvent

    timestamp = datetime.utcnow().isoformat()
    now = datetime.utcnow()

    record = {
        "call_sid": call_sid,
        "event": event_type,
        "payload": payload,
        "timestamp": timestamp,
    }

    db = SessionLocal()
    try:
        call = None
        if call_sid:
            call = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()

        # Deduplicate: if an event with same type and payload was created in last 5s, skip
        try:
            cutoff = now - timedelta(seconds=5)
            q = db.query(CallEvent).filter(
                CallEvent.event_type == event_type,
                CallEvent.created_at >= cutoff,
            )
            if call:
                q = q.filter(CallEvent.call_id == call.id)
            if payload:
                q = q.filter(CallEvent.event_payload.contains(payload))
            if q.first():
                return
        except Exception:
            pass

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
    except Exception as exc:
        try:
            logger.error(f"Error logging event to DB: {exc}")
        except Exception:
            pass
    finally:
        db.close()


def log_system_failure(call_sid: Optional[str], source: str, error: str) -> None:
    """Record a system failure related to a call for incident analysis."""
    log_event(call_sid, "SYSTEM_FAILURE", {"source": source, "error": error})

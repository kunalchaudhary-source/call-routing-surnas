from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from backend.config import get_settings
from backend.db import SessionLocal
from backend.models.db_models import Call, RoutingDecision
from backend.services.logger import log_event
import json
from typing import Optional


settings = get_settings()

# Configure the Twilio REST client
client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

# US / India agent pool numbers or queues
US_AGENT_POOL = settings.US_AGENT_POOL
INDIA_AGENT_POOL = settings.INDIA_AGENT_POOL


async def route_call(call_sid: str) -> None:
    """Location-based routing (no AI in this layer).

    - Looks up the call on Twilio
    - Uses caller_country to choose US vs India pool
    - Updates the call TwiML to dial the chosen target
    """
    call = client.calls(call_sid).fetch()

    # Twilio Call resource has caller_country for inbound calls
    caller_country = getattr(call, "caller_country", None)

    if caller_country == "US":
        target = US_AGENT_POOL
    else:
        target = INDIA_AGENT_POOL

    log_event(call_sid, "ROUTING_DECISION", {
        "caller_country": caller_country,
        "target": target,
    })

    # Persist deterministic routing decision in routing_decisions table
    db = SessionLocal()
    try:
        call_row = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
        routing = RoutingDecision(
            call_id=call_row.id if call_row else None,
            caller_country=caller_country,
            routing_rule="CALLER_COUNTRY",
            routed_to=target,
        )
        db.add(routing)
        db.commit()
    finally:
        db.close()

    # Update live call to dial the selected target
    client.calls(call_sid).update(
        twiml=f"""
<Response>
    <Dial>{target}</Dial>
</Response>
"""
    )


def enqueue_taskrouter_task(call_sid: str, queue_sid: str) -> Optional[str]:
    """Create a TaskRouter task targeted at `queue_sid`.

    Returns the task SID on success or None on failure.
    """
    if not settings.TASKROUTER_WORKSPACE_SID or not queue_sid:
        log_event(call_sid, "TASKROUTER_NOT_CONFIGURED", {})
        return None

    try:
        attributes = json.dumps({"call_sid": call_sid, "type": "support"})
        task = client.taskrouter.workspaces(settings.TASKROUTER_WORKSPACE_SID).tasks.create(
            task_queue_sid=queue_sid,
            attributes=attributes,
        )
        log_event(call_sid, "TASKROUTER_TASK_CREATED", {"task_sid": task.sid, "queue_sid": queue_sid})
        return getattr(task, "sid", None)
    except Exception as exc:
        log_event(call_sid, "TASKROUTER_TASK_CREATE_FAILED", {"error": str(exc)})
        return None


def route_to_human(call_sid: str) -> None:
    """Route a live call to a human via TaskRouter (preferred) or Dial fallback.

    Chooses queue by caller_country stored in Twilio call or DB.
    """
    # Try DB first for caller country
    db = SessionLocal()
    try:
        call_row = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
        caller_country = call_row.caller_country if call_row else None
    finally:
        db.close()

    # If not in DB, fetch from Twilio
    if not caller_country:
        try:
            tw_call = client.calls(call_sid).fetch()
            caller_country = getattr(tw_call, "caller_country", None)
        except TwilioRestException as tre:
            # Twilio returned an API error (e.g., 20404 resource not found)
            log_event(call_sid, "TWILIO_CALL_FETCH_FAILED", {"status": tre.status, "code": tre.code, "msg": str(tre)})
            caller_country = None
        except Exception as exc:
            log_event(call_sid, "TWILIO_CALL_FETCH_ERROR", {"error": str(exc)})
            caller_country = None

    if caller_country == "US":
        queue_sid = settings.US_SUPPORT_QUEUE_SID
        dial_target = settings.US_AGENT_POOL
    else:
        queue_sid = settings.INDIA_SUPPORT_QUEUE_SID
        dial_target = settings.INDIA_AGENT_POOL

    # Prefer TaskRouter enqueue
    task_sid = None
    if queue_sid and settings.TASKROUTER_WORKSPACE_SID:
        task_sid = enqueue_taskrouter_task(call_sid, queue_sid)

    if task_sid:
        log_event(call_sid, "ROUTED_TO_TASKROUTER", {"task_sid": task_sid, "queue_sid": queue_sid})
        # Persist routing decision
        db = SessionLocal()
        try:
            call_row = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
            routing = RoutingDecision(
                call_id=call_row.id if call_row else None,
                caller_country=caller_country,
                routing_rule="TASKROUTER_QUEUE",
                routed_to=queue_sid,
            )
            db.add(routing)
            db.commit()
        finally:
            db.close()
        return

    # Fallback: update live call to dial a static agent/queue number
    log_event(call_sid, "ROUTING_FALLBACK_DIAL", {"target": dial_target})
    try:
        client.calls(call_sid).update(
            twiml=f"""
<Response>
    <Dial>{dial_target}</Dial>
</Response>
"""
        )
        # persist routing decision
        db = SessionLocal()
        try:
            call_row = db.query(Call).filter_by(twilio_call_sid=call_sid).one_or_none()
            routing = RoutingDecision(
                call_id=call_row.id if call_row else None,
                caller_country=caller_country,
                routing_rule="FALLBACK_DIAL",
                routed_to=dial_target,
            )
            db.add(routing)
            db.commit()
        finally:
            db.close()
    except TwilioRestException as tre:
        # Common case: call resource not found in this Twilio account
        log_event(call_sid, "ROUTING_UPDATE_TWILIO_ERROR", {"status": tre.status, "code": tre.code, "msg": str(tre)})

        # If TaskRouter is available, create a task so agents can follow up
        if settings.TASKROUTER_WORKSPACE_SID and queue_sid:
            try:
                tsid = enqueue_taskrouter_task(call_sid, queue_sid)
                log_event(call_sid, "TASK_CREATED_AFTER_TWILIO_ERROR", {"task_sid": tsid})
            except Exception as exc:
                log_event(call_sid, "TASK_CREATE_AFTER_TWILIO_ERROR_FAILED", {"error": str(exc)})
    except Exception as exc:
        log_event(call_sid, "ROUTING_UPDATE_FAILED", {"error": str(exc)})

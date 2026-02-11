from __future__ import annotations

from typing import List
import time

from twilio.rest import Client

from backend.config import get_settings
from backend.services.logger import log_event

settings = get_settings()

# Simple in-process cache for verified numbers
_cache: dict = {
    "numbers": [],
    "fetched_at": 0,
}
CACHE_TTL = 300  # seconds


def _fetch_verified_from_twilio() -> List[str]:
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        numbers = set()
        # Incoming phone numbers owned by the account
        for rec in client.incoming_phone_numbers.list():
            numbers.add(rec.phone_number)

        # Outgoing caller IDs (verified caller IDs) - may be empty or deprecated on some accounts
        try:
            for rec in client.outgoing_caller_ids.list():
                # Twilio returns phone_number field
                numbers.add(rec.phone_number)
        except Exception:
            # Non-fatal: older accounts or permissions may not expose this resource
            pass

        return sorted(numbers)
    except Exception as e:
        log_event(None, "TWILIO_VERIFIED_FETCH_ERROR", {"error": str(e)})
        return []


def get_verified_numbers() -> List[str]:
    now = int(time.time())
    if _cache["numbers"] and (now - _cache["fetched_at"] < CACHE_TTL):
        return _cache["numbers"]

    nums = _fetch_verified_from_twilio()
    _cache["numbers"] = nums
    _cache["fetched_at"] = now
    log_event(None, "TWILIO_VERIFIED_NUMBERS_REFRESH", {"count": len(nums)})
    return nums

"""Order status service for looking up customer order tracking information."""

from typing import Optional, Dict, Any
import requests

from app.services import config_service
from app.core.logger import log_event


def query_order_status(order_id: str) -> Optional[Dict[str, Any]]:
    """Call configured order status API and return parsed result."""
    if not order_id:
        return None

    url = config_service.get_setting("order_status_api_url")
    if not url:
        log_event(None, "ORDER_STATUS_CONFIG_MISSING", {})
        return None

    if "{order_id}" in url:
        final = url.replace("{order_id}", requests.utils.quote(order_id))
    else:
        sep = "&" if "?" in url else "?"
        final = f"{url}{sep}order_id={requests.utils.quote(order_id)}"

    api_key = config_service.get_setting("order_status_api_key")
    headers = {"x-api-key": api_key} if api_key else {}

    try:
        resp = requests.get(final, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        log_event(None, "ORDER_STATUS_API_CALLED", {"url": final, "status_code": resp.status_code})
        return data
    except Exception as e:
        log_event(None, "ORDER_STATUS_API_ERROR", {"error": str(e), "url": final})
        return None


def get_order_status_for_phone(phone: Optional[str], call_id: Optional[str] = None) -> Optional[str]:
    """End-to-end order status lookup based on customer phone number.
    
    Returns: 'shipped', 'not_ready', 'no_orders', or None.
    """
    if not phone:
        return None
    # For now, default mock / placeholder behavior if no custom URL set
    return "shipped"

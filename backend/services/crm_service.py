"""Salesforce CRM integration for lead creation.

Converts caller data from IVR flow into Salesforce Lead records.
"""
import os
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from backend.services.logger import log_event


# CRM Configuration - loaded from environment
CRM_TOKEN_URL = os.getenv("CRM_TOKEN_URL", "")
CRM_BASE_URL = os.getenv("CRM_BASE_URL", "")
CRM_CLIENT_ID = os.getenv("CRM_CLIENT_ID", "")
CRM_CLIENT_SECRET = os.getenv("CRM_CLIENT_SECRET", "")
CRM_USERNAME = os.getenv("CRM_USERNAME", "")
CRM_PASSWORD = os.getenv("CRM_PASSWORD", "")

# Cached token
_token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0}


def _is_crm_configured() -> bool:
    """Check if CRM credentials are configured."""
    return bool(CRM_TOKEN_URL and CRM_BASE_URL and CRM_CLIENT_ID and CRM_CLIENT_SECRET)


def get_crm_token() -> Optional[str]:
    """Get Salesforce OAuth access token using client credentials flow.
    
    Returns:
        Access token string or None if authentication fails.
    """
    if not _is_crm_configured():
        log_event(None, "CRM_NOT_CONFIGURED", {"message": "CRM credentials not set in environment"})
        return None

    try:
        # Build token request
        params = {
            "grant_type": "client_credentials",
            "client_id": CRM_CLIENT_ID,
            "client_secret": CRM_CLIENT_SECRET,
        }
        
        # Add username/password if configured (for password grant flow)
        if CRM_USERNAME and CRM_PASSWORD:
            params["grant_type"] = "password"
            params["username"] = CRM_USERNAME
            params["password"] = CRM_PASSWORD

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        response = requests.post(
            CRM_TOKEN_URL,
            data=urlencode(params),
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            log_event(None, "CRM_TOKEN_ERROR", {
                "status": response.status_code,
                "response": response.text[:500]
            })
            return None

        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if access_token:
            log_event(None, "CRM_TOKEN_SUCCESS", {"token_type": token_data.get("token_type")})
            _token_cache["access_token"] = access_token
            return access_token
        
        log_event(None, "CRM_TOKEN_MISSING", {"response": token_data})
        return None

    except requests.RequestException as e:
        log_event(None, "CRM_TOKEN_REQUEST_FAILED", {"error": str(e)})
        return None
    except Exception as e:
        log_event(None, "CRM_TOKEN_EXCEPTION", {"error": str(e)})
        return None


def create_lead_in_crm(
    call_sid: str,
    caller_name: Optional[str],
    mobile_phone: Optional[str],
    intent: Optional[str],
    product_id: Optional[str],
    category: Optional[str],
    description: Optional[str],
) -> Optional[str]:
    """Create a Lead record in Salesforce CRM.
    
    Args:
        call_sid: Twilio call SID for logging
        caller_name: Full name of the caller (from IVR question)
        mobile_phone: Caller's phone number
        intent: User's selected option (general_inquiry, store, price_request)
        product_id: Product ID if provided
        category: Category name if provided
        description: Brief query description from caller
        
    Returns:
        Salesforce Lead ID if created successfully, None otherwise.
    """
    if not _is_crm_configured():
        log_event(call_sid, "CRM_LEAD_SKIPPED", {"reason": "CRM not configured"})
        return None

    # Get access token
    access_token = get_crm_token()
    if not access_token:
        log_event(call_sid, "CRM_LEAD_FAILED", {"reason": "Could not get access token"})
        return None

    try:
        # Map intent to title
        title_map = {
            "general_inquiry": "Enquiry",
            "store": "Try Near You",
            "price_request": "Price Request",
            "unknown": "Enquiry",
        }
        title = title_map.get(intent, "Price Request / Enquiry")

        # Build lead data
        # Required fields: LastName, Company
        last_name = caller_name or "Web Lead"
        company = "Individual"

        # NOTE:
        # - We intentionally do NOT send the product value to Salesforce's
        #   Product_Interest_SFCC__c field anymore.
        # - The caller-provided product (now a product *name*) is appended
        #   to Notes__c together with other captured context.

        # Build notes payload
        notes_pieces = []
        if category:
            notes_pieces.append(f"Category: {category}")
        if product_id:
            notes_pieces.append(f"Product: {product_id}")
        if description:
            notes_pieces.append(str(description))
        notes_text = "\n\n".join([p for p in notes_pieces if p]) or None

        lead_body = {
            "LastName": last_name,
            "Company": company,
            "Email": None,  # Not collected in IVR
            "MobilePhone": mobile_phone,
            "Notes__c": notes_text,
            "Title": title,
            # Always send null/omit this SFCC product field; product name goes into Notes__c.
            "Product_Interest_SFCC__c": None,
        }

        # Set hot lead flags for all known intents (store/general_inquiry/price_request/unknown)
        if intent in title_map:
            lead_body["Rating"] = "Hot"
            lead_body["Lead_Temperature__c"] = "Hot"

        # Notes__c is already built above with Category/Product/Description

        # Remove None values (Salesforce doesn't like explicit nulls for some fields)
        lead_body = {k: v for k, v in lead_body.items() if v is not None}

        log_event(call_sid, "CRM_LEAD_CREATING", {"body": lead_body})

        # Make API request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        url = f"{CRM_BASE_URL}/services/data/v62.0/sobjects/Lead"
        
        response = requests.post(
            url,
            json=lead_body,
            headers=headers,
            timeout=30
        )

        if response.status_code in (200, 201):
            result = response.json()
            lead_id = result.get("id")
            log_event(call_sid, "CRM_LEAD_CREATED", {"lead_id": lead_id, "success": result.get("success")})
            return lead_id
        else:
            log_event(call_sid, "CRM_LEAD_ERROR", {
                "status": response.status_code,
                "response": response.text[:500]
            })
            return None

    except requests.RequestException as e:
        log_event(call_sid, "CRM_LEAD_REQUEST_FAILED", {"error": str(e)})
        return None
    except Exception as e:
        log_event(call_sid, "CRM_LEAD_EXCEPTION", {"error": str(e)})
        return None

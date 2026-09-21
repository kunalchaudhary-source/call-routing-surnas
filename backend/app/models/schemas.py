"""Pydantic schemas for request validation, responses, and API payloads."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, validator

ALLOWED_CATEGORIES = {
    "necklace",
    "bangles",
    "bracelets",
    "earrings",
    "rings",
    "curated combination",
    "accessories",
    "men jewellery",
    "vintage diamonds",
}


# ==================== AUTH & DEBUG SCHEMAS ====================

class LoginRequest(BaseModel):
    username: str
    password: str


class DebugModerationRequest(BaseModel):
    text: str


# ==================== AGENT SCHEMAS ====================

class AgentCreate(BaseModel):
    name: str
    phone_number: str
    region: str  # 'US', 'IN', 'GLOBAL'
    is_default: bool = False
    specializations: List[str] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    region: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class SpecializationAdd(BaseModel):
    category: str
    proficiency_level: int = 1


# ==================== PROMPTS & CORRECTIONS SCHEMAS ====================

class CorrectionCreate(BaseModel):
    wrong_word: str
    correct_word: str


class GreetingUpdate(BaseModel):
    message: str


class IVRPromptUpdate(BaseModel):
    message: str


# ==================== CALL CONTEXT SCHEMAS ====================

class CallContextPayload(BaseModel):
    call_sid: str = Field(..., min_length=10)
    page_context: Literal["home", "product"] = "home"
    currency: Literal["INR", "USD", "EUR", "AED"] = "INR"
    user_type: Literal["guest", "identified"] = "guest"
    customer_id: Optional[str] = None
    product_id: Optional[str] = None
    product_category: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator("product_category")
    def _normalize_category(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CATEGORIES:
            raise ValueError("Unsupported category")
        return normalized


class CallContextResponse(BaseModel):
    lead_id: str
    preferred_language: str


# ==================== EVENT SCHEMAS ====================

class LogEvent(BaseModel):
    call_sid: Optional[str]
    event: str
    payload: Dict[str, Any]
    timestamp: str

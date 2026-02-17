"""Gemini AI service for optional text filtering.

This service is optional and returns text unchanged if GEMINI_API_KEY is not set.
"""
import os
from typing import Optional

from backend.config import get_settings
from backend.services.logger import log_event

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def _get_gemini_api_key() -> Optional[str]:
    """Central place to read the Gemini API key from settings/env.

    This ensures we always go through the same configuration path
    (backend/.env loaded by backend.config) instead of scattering
    os.getenv calls across the codebase.
    """
    try:
        settings = get_settings()
        return settings.GEMINI_API_KEY
    except Exception:
        # Fallback to raw environment lookup if settings are unavailable
        return os.getenv("GEMINI_API_KEY")


def filter_text_if_enabled(text: str) -> str:
    """Optionally filter/rewrite text using Gemini for phone-friendly phrasing.
    
    If GEMINI_API_KEY is not set, returns the text unchanged.
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        return text
    
    # For now, just return text unchanged.
    # TODO: Implement actual Gemini filtering if needed
    return text


def is_profane(text: str) -> bool:
    """Return True if `text` contains profanity using Google Gemini SDK.

    Uses gemini-2.5-flash-lite (free tier) with system instruction for profanity detection.
    Falls back to local blacklist if SDK unavailable or API call fails.
    """
    from backend.services.logger import log_system_failure, log_event

    if not text:
        return False

    api_key = _get_gemini_api_key()

    # Try Gemini SDK if available and configured
    if api_key and GENAI_AVAILABLE:
        try:
            genai.configure(api_key=api_key)
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
            
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction="You are a profanity filter. Analyze the user's text. "
                                   "Respond with 'PROFANE' if it contains swear words, hate speech, or harassment. "
                                   "Respond with 'CLEAN' otherwise. Provide no other text."
            )
            
            response = model.generate_content(text)
            result = response.text.strip().upper()
            
            log_event(None, "GEMINI_MODERATION_RESULT", {
                "method": "sdk_model",
                "model": model_name,
                "response": result
            })
            
            return "PROFANE" in result or "YES" in result
            
        except Exception as exc:
            # If blocked by safety filters, it's likely profane
            if "block" in str(exc).lower() or "safety" in str(exc).lower():
                log_event(None, "GEMINI_MODERATION_RESULT", {
                    "method": "sdk_model",
                    "response": "BLOCKED",
                    "profane": True
                })
                return True
            log_system_failure(None, "gemini_sdk", f"error calling SDK: {exc}")

    # Fallback to local blacklist
    lower = text.lower()
    tokens = lower.split()

    blacklist = {
        "fuck", "shit", "bitch", "asshole", "bastard", "damn",
        "cunt", "dick", "piss", "cock", "pussy"
    }

    matched = None

    # 1) Exact/substring match
    for w in blacklist:
        if w in lower:
            matched = w
            break

    # 2) Censored tokens with asterisks
    if not matched:
        for token in tokens:
            if "*" in token and len(token) >= 3:
                matched = token
                break

    profane_local = bool(matched)
    log_event(None, "GEMINI_MODERATION_RESULT", {
        "method": "local",
        "profane": profane_local,
        "matched": matched
    })
    return profane_local


def debug_moderation(text: str) -> dict:
    """Run the same moderation flow but return detailed diagnostics for debugging.

    Returns a dict with keys: profane (bool), method ("sdk_model"|"local"),
    matched, model_response, sdk_available, error
    """
    from backend.services.logger import log_system_failure

    result = {
        "profane": False,
        "method": None,
        "matched": None,
        "model_response": None,
        "sdk_available": GENAI_AVAILABLE,
        "error": None,
    }

    if not text:
        return result

    api_key = _get_gemini_api_key()

    # Try Gemini SDK if available and configured
    if api_key and GENAI_AVAILABLE:
        try:
            genai.configure(api_key=api_key)
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
            
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction="You are a profanity filter. Analyze the user's text. "
                                   "Respond with 'PROFANE' if it contains swear words, hate speech, or harassment. "
                                   "Respond with 'CLEAN' otherwise. Provide no other text."
            )
            
            response = model.generate_content(text)
            response_text = response.text.strip().upper()
            
            result["model_response"] = response_text
            result["method"] = "sdk_model"
            result["profane"] = "PROFANE" in response_text or "YES" in response_text
            return result
            
        except Exception as exc:
            # If blocked by safety filters, it's likely profane
            if "block" in str(exc).lower() or "safety" in str(exc).lower():
                result["method"] = "sdk_model"
                result["model_response"] = "BLOCKED_BY_SAFETY_FILTER"
                result["profane"] = True
                result["error"] = str(exc)
                return result
            result["error"] = str(exc)
            log_system_failure(None, "gemini_sdk", f"error calling SDK: {exc}")

    # Fallback to local blacklist
    lower = text.lower()
    tokens = lower.split()
    blacklist = {"fuck", "shit", "bitch", "asshole", "bastard", "damn", "cunt", "dick", "piss", "cock", "pussy"}
    matched = None
    for w in blacklist:
        if w in lower:
            matched = w
            break
    if not matched:
        for token in tokens:
            if "*" in token and len(token) >= 3:
                matched = token
                break

    result["method"] = "local"
    result["matched"] = matched
    result["profane"] = bool(matched)
    return result


def infer_category_from_product(product_name: str, allowed_categories: list[str]) -> str | None:
    """Use Gemini to infer a single category from a product name.

    Returns one of the `allowed_categories` (exact string) or None if no confident match.
    Falls back to None if SDK not available or the model response can't be mapped.
    """
    if not product_name:
        return None

    api_key = _get_gemini_api_key()
    if not api_key or not GENAI_AVAILABLE:
        return None

    try:
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

        system_instruction = (
            "You are a helpful classifier. Choose the single best category for the given product name. "
            "Only respond with exactly one of the following category names (case-sensitive): "
            f"{', '.join(allowed_categories)}. "
            "If none apply, respond with NONE. Provide NO other text or explanation."
        )

        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
        )

        response = model.generate_content(product_name)
        text = (response.text or "").strip()
        # Normalize and try to match exactly or case-insensitively
        if not text:
            return None
        # Some models may include newline or punctuation — strip to first token/line
        candidate = text.splitlines()[0].strip()
        # Exact match
        if candidate in allowed_categories:
            log_event(None, "GEMINI_CATEGORY_INFERRED", {"model": model_name, "category": candidate, "product_name": product_name})
            return candidate
        # Case-insensitive match
        lowered = {c.lower(): c for c in allowed_categories}
        if candidate.lower() in lowered:
            resolved = lowered[candidate.lower()]
            log_event(None, "GEMINI_CATEGORY_INFERRED", {"model": model_name, "category": resolved, "product_name": product_name})
            return resolved

        # If model returned 'NONE' or couldn't be mapped, return None
        return None
    except Exception as exc:
        log_event(None, "GEMINI_CATEGORY_ERROR", {"error": str(exc), "product_name": product_name})
        return None

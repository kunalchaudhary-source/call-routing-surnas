"""Gemini AI service for text filtering and profanity moderation."""

from typing import Optional
from app.core.config import get_settings
from app.core.logger import log_event, log_system_failure

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def _get_gemini_api_key() -> Optional[str]:
    try:
        return get_settings().GEMINI_API_KEY
    except Exception:
        return None


def filter_text_if_enabled(text: str) -> str:
    """Optionally filter/rewrite text using Gemini. Returns unchanged if key not set."""
    api_key = _get_gemini_api_key()
    if not api_key:
        return text
    return text


def is_profane(text: str) -> bool:
    """Return True if `text` contains profanity using Google Gemini SDK or local fallback."""
    if not text:
        return False

    api_key = _get_gemini_api_key()

    if GENAI_AVAILABLE and api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-lite",
                system_instruction=(
                    "You are a strict profanity and safety filter for a jewelry store phone system. "
                    "Analyze the given caller name or text. If it contains profanity, vulgarity, "
                    "explicit slurs, sexual references, or offensive abuse, answer EXACTLY 'UNSAFE'. "
                    "Otherwise, if it is a plausible, harmless, or common personal name or benign text, "
                    "answer EXACTLY 'SAFE'. Do not output any other words."
                ),
            )
            response = model.generate_content(
                f"Text to evaluate: {text}",
                generation_config={"temperature": 0.0, "max_output_tokens": 5},
            )
            result_text = (response.text or "").strip().upper()
            if "UNSAFE" in result_text:
                log_event(None, "GEMINI_PROFANITY_DETECTED", {"text": text})
                return True
            return False
        except Exception as exc:
            log_system_failure(None, "gemini_profanity_check", str(exc))

    # Local fallback blacklist
    lowered = text.lower()
    local_blacklist = {
        "asshole", "bitch", "bastard", "fuck", "shit", "cunt", "dick", "pussy",
        "motherfucker", "madarchod", "bhenchod", "chutiya", "gandu", "harami",
        "kamina", "bhosdike", "saala", "kutta",
    }
    words = lowered.split()
    for w in words:
        if w in local_blacklist:
            return True
    for b in local_blacklist:
        if f" {b} " in f" {lowered} ":
            return True

    return False


def debug_moderation(text: str) -> dict:
    """Diagnostic tool for moderation."""
    api_key = _get_gemini_api_key()
    return {
        "input": text,
        "genai_available": GENAI_AVAILABLE,
        "has_api_key": bool(api_key),
        "is_profane": is_profane(text),
    }

"""Gemini AI service for optional text filtering.

This service is optional and returns text unchanged if GEMINI_API_KEY is not set.
"""
import os
from typing import Optional


def filter_text_if_enabled(text: str) -> str:
    """Optionally filter/rewrite text using Gemini for phone-friendly phrasing.
    
    If GEMINI_API_KEY is not set, returns the text unchanged.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return text
    
    # For now, just return text unchanged.
    # TODO: Implement actual Gemini filtering if needed
    return text
